"""Configuration + filesystem anchors for the brain.

The repo root is the folder that holds `config/` and (once written) `CLAUDE.md`.
Everything else is resolved from there so the brain behaves identically whether
it's launched by start.ps1, by backtalk, or from a test.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    """Raised when models.yaml is missing or unusable — the wizard should run."""


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` (or this file) until we find the repo markers.

    Markers: a `config/` dir AND a `docs/` or `vendor/` dir, or a `.git`.
    Falls back to two levels up from this file (brain/jarvis_brain/config.py
    -> brain/ -> repo/).
    """
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "config").is_dir() and (
            (parent / ".git").exists()
            or (parent / "docs").is_dir()
            or (parent / "vendor").is_dir()
        ):
            return parent
    return Path(__file__).resolve().parents[2]


REPO_ROOT = find_repo_root()
CONFIG_DIR = REPO_ROOT / "config"
MODELS_YAML = CONFIG_DIR / "models.yaml"
JARVIS_JSON = CONFIG_DIR / "jarvis.json"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def _expand(p: str | None) -> str:
    return os.path.expanduser(p) if p else (p or "")


# --------------------------------------------------------------------------- #
# .env — API keys live here (git-ignored), not in models.yaml
# --------------------------------------------------------------------------- #
ENV_FILE = REPO_ROOT / ".env"
_ENV_CACHE: dict[str, str] | None = None


def _parse_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def load_env_file() -> None:
    """Merge repo `.env` into os.environ (real environment wins). Idempotent."""
    global _ENV_CACHE
    _ENV_CACHE = _parse_env_file()
    for k, v in _ENV_CACHE.items():
        os.environ.setdefault(k, v)


def env_value(name: str) -> str:
    """A secret by env-var name: real environment first, then repo `.env`."""
    if not name:
        return ""
    if name in os.environ:
        return os.environ[name]
    global _ENV_CACHE
    if _ENV_CACHE is None:
        _ENV_CACHE = _parse_env_file()
    return _ENV_CACHE.get(name, "")


# --------------------------------------------------------------------------- #
# vault + device — the one place these are resolved (Phase 3)
# --------------------------------------------------------------------------- #
def _slug(s: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in s.strip().lower())
    return "-".join(filter(None, out.split("-"))) or "device"


def vault_dir() -> Path:
    """The Obsidian memory vault. `vault_path` in config/jarvis.json when set
    (Phase 3 points it at a Google-Drive-synced folder); otherwise a repo-local
    `Vault/` that is git-ignored."""
    v = (load_jarvis_json().get("vault_path") or "").strip()
    return Path(os.path.expanduser(v)) if v else REPO_ROOT / "Vault"


def device_name() -> str:
    """Short slug identifying this machine — used for per-device daily-note
    shards so two devices never write the same file the same minute."""
    import socket

    name = (load_jarvis_json().get("device_name") or "").strip()
    if not name:
        try:
            name = socket.gethostname()
        except OSError:
            name = "device"
    return _slug(name)


def dated_shard(subdir: str) -> Path:
    """Today's per-device file, e.g. `<vault>/01 - Daily Notes/2026-09-04.laptop.md`.
    The nightly consolidation job (scripts/vault_consolidate.py) merges these
    into the plain `<date>.md`."""
    from datetime import date

    return vault_dir() / subdir / f"{date.today():%Y-%m-%d}.{device_name()}.md"


def dated_note(subdir: str) -> Path:
    """Today's consolidated file, `<vault>/<subdir>/<date>.md`."""
    from datetime import date

    return vault_dir() / subdir / f"{date.today():%Y-%m-%d}.md"


# --------------------------------------------------------------------------- #
# models.yaml
# --------------------------------------------------------------------------- #
@dataclass
class LocalModelCfg:
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = ""
    keep_alive: Any = -1
    context: int = 8192  # voice turns are short; keeps the KV cache light
    temperature: float = 0.7
    languages: list[str] = field(default_factory=lambda: ["en"])


@dataclass
class BigProviderCfg:
    """One "big brain" option. Two kinds:

    kind="cli" — shell out to a coding-agent CLI you're already signed into
                 (`claude`, `codex`, `gemini`). No API key, cost is your
                 existing subscription.
    kind="api" — call a hosted API with a key from `api_key_env` (in .env):
                 OpenRouter, OpenAI, Anthropic, Groq, or any OpenAI-compatible
                 endpoint via `base_url`.
    """
    kind: str = "api"              # "cli" | "api"
    cli: str = ""                  # kind=cli: claude | codex | gemini
    provider: str = ""            # kind=api: openrouter | openai | anthropic | groq | ...
    model: str = ""
    api_key_env: str = ""
    base_url: str = ""

    @property
    def label(self) -> str:
        if self.kind == "cli":
            return f"{self.cli} (subscription CLI)"
        return f"{self.provider}:{self.model or '?'}"


@dataclass
class SpecializedProviderCfg:
    """A key for non-chat work — image/video/music generation, OCR, embeddings,
    anything. Keyed by a capability name you choose. The secret lives in .env
    under `api_key_env`; only its name is stored here."""
    capability: str
    provider: str = ""
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    notes: str = ""

    @property
    def key(self) -> str:
        return env_value(self.api_key_env) if self.api_key_env else ""

    @property
    def configured(self) -> bool:
        return bool(self.key)


@dataclass
class BrainCfg:
    mode: str = "local"
    local: LocalModelCfg = field(default_factory=LocalModelCfg)
    big: list[BigProviderCfg] = field(default_factory=list)
    specialized: dict[str, SpecializedProviderCfg] = field(default_factory=dict)
    monthly_cloud_cap_inr: int = 1000
    never_escalate_tags: list[str] = field(
        default_factory=lambda: ["private", "health", "finance_personal", "family"]
    )
    _raw: dict = field(default_factory=dict, repr=False)

    # -- convenience ------------------------------------------------------- #
    @property
    def is_configured(self) -> bool:
        return bool(self.local.model)

    @property
    def has_big(self) -> bool:
        return bool(self.big)

    def specialized_for(self, capability: str) -> SpecializedProviderCfg | None:
        return self.specialized.get(capability)


def load_brain_cfg(*, required: bool = True) -> BrainCfg:
    """Read config/models.yaml into a BrainCfg.

    `required=True` (the default) raises ConfigError when the file is absent
    or has no local model set — the signal for start.* to run the wizard.
    `required=False` returns best-effort defaults instead (used by the wizard).
    """
    if not MODELS_YAML.exists():
        if required:
            raise ConfigError(
                f"{MODELS_YAML} not found. Run:  python -m jarvis_brain configure"
            )
        return BrainCfg()

    try:
        raw = yaml.safe_load(MODELS_YAML.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{MODELS_YAML} is not valid YAML: {e}") from e

    b = raw.get("brain", raw) if isinstance(raw, dict) else {}
    lraw = (b.get("local") or {}) if isinstance(b, dict) else {}
    local = LocalModelCfg(
        provider=lraw.get("provider", "ollama"),
        base_url=str(lraw.get("base_url", "http://localhost:11434")).rstrip("/"),
        model=lraw.get("model", "") or "",
        keep_alive=lraw.get("keep_alive", -1),
        context=int(lraw.get("context", 8192)),
        temperature=float(lraw.get("temperature", 0.7)),
        languages=list(lraw.get("languages", ["en"])),
    )
    big: list[BigProviderCfg] = []
    for p in (b.get("big") or []):
        if not isinstance(p, dict):
            continue
        kind = str(p.get("kind", "") or ("cli" if p.get("cli") else "api")).lower()
        if kind == "cli" and p.get("cli"):
            big.append(BigProviderCfg(kind="cli", cli=str(p["cli"]),
                                      model=str(p.get("model", ""))))
        elif kind == "api" and p.get("provider"):
            big.append(BigProviderCfg(
                kind="api",
                provider=str(p["provider"]),
                model=str(p.get("model", "")),
                api_key_env=str(p.get("api_key_env", "")),
                base_url=str(p.get("base_url", "")),
            ))

    specialized: dict[str, SpecializedProviderCfg] = {}
    for cap, s in (raw.get("specialized") or {}).items():
        if not isinstance(s, dict):
            continue
        specialized[str(cap)] = SpecializedProviderCfg(
            capability=str(cap),
            provider=str(s.get("provider", "")),
            base_url=str(s.get("base_url", "")),
            api_key_env=str(s.get("api_key_env", "")),
            model=str(s.get("model", "")),
            notes=str(s.get("notes", "")),
        )

    cfg = BrainCfg(
        mode=b.get("mode", "local"),
        local=local,
        big=big,
        specialized=specialized,
        monthly_cloud_cap_inr=int(b.get("monthly_cloud_cap_inr", 1000)),
        never_escalate_tags=list(
            b.get("never_escalate_tags",
                  ["private", "health", "finance_personal", "family"])
        ),
        _raw=raw if isinstance(raw, dict) else {},
    )
    if required and not cfg.is_configured:
        raise ConfigError(
            f"{MODELS_YAML} has no brain.local.model set. "
            f"Run:  python -m jarvis_brain configure"
        )
    load_env_file()  # make API keys from .env visible to the providers
    return cfg


def _big_to_dict(p: BigProviderCfg) -> dict:
    if p.kind == "cli":
        d = {"kind": "cli", "cli": p.cli}
        if p.model:
            d["model"] = p.model
        return d
    d = {"kind": "api", "provider": p.provider, "model": p.model}
    if p.api_key_env:
        d["api_key_env"] = p.api_key_env
    if p.base_url:
        d["base_url"] = p.base_url
    return d


def save_brain_cfg(cfg: BrainCfg) -> None:
    """Write config/models.yaml, preserving any unknown keys already present."""
    raw = dict(cfg._raw) if cfg._raw else {}
    raw["brain"] = {
        "mode": cfg.mode,
        "local": {
            "provider": cfg.local.provider,
            "base_url": cfg.local.base_url,
            "model": cfg.local.model,
            "keep_alive": cfg.local.keep_alive,
            "context": cfg.local.context,
            "temperature": cfg.local.temperature,
            "languages": cfg.local.languages,
        },
        "big": [_big_to_dict(p) for p in cfg.big],
        "monthly_cloud_cap_inr": cfg.monthly_cloud_cap_inr,
        "never_escalate_tags": cfg.never_escalate_tags,
    }
    if cfg.specialized:
        raw["specialized"] = {
            cap: {k: v for k, v in {
                "provider": s.provider,
                "base_url": s.base_url,
                "api_key_env": s.api_key_env,
                "model": s.model,
                "notes": s.notes,
            }.items() if v}
            for cap, s in cfg.specialized.items()
        }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    header = (
        "# config/models.yaml — the brain registry. Written by "
        "`python -m jarvis_brain configure`.\n"
        "# Edit freely; it hot-reloads next turn. Git-ignored — it's yours.\n\n"
    )
    MODELS_YAML.write_text(
        header + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# jarvis.json (identity) + CLAUDE.md (persona)
# --------------------------------------------------------------------------- #
def load_jarvis_json() -> dict:
    try:
        return json.loads(JARVIS_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save_jarvis_json(data: dict) -> None:
    """Write config/jarvis.json, keeping keys sorted-ish by preserving order of
    what's passed in."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    JARVIS_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


_PERSONA_START = "<!-- PERSONA:START -->"
_PERSONA_END = "<!-- PERSONA:END -->"


def _bare_persona() -> str:
    ident = load_jarvis_json()
    name = ident.get("name", "Assistant")
    if ident.get("persona"):
        return str(ident["persona"]).replace("{name}", name).strip()
    return (
        f"You are {name}, a calm, concise personal assistant. "
        f"You reply in the same language the user used. You never pad answers. "
        f"Your replies are spoken aloud, so keep them short and plain — no markdown."
    )


def persona_from_text(text: str) -> str | None:
    """Pull the <!-- PERSONA:START -->…<!-- PERSONA:END --> block out of a
    CLAUDE.md and substitute {name}. None if the markers aren't both present —
    the WHOLE file is a dev/architecture doc and feeding all of it to a small
    local model makes it answer *about* the file."""
    if not text or _PERSONA_START not in text or _PERSONA_END not in text:
        return None
    block = text.split(_PERSONA_START, 1)[1].split(_PERSONA_END, 1)[0].strip()
    if not block:
        return None
    name = load_jarvis_json().get("name", "Assistant")
    return block.replace("{name}", name)


def load_persona() -> str:
    """The agent's spoken identity.

    Precedence:
      1. the PERSONA block in CLAUDE.md
      2. a `persona` string in config/jarvis.json
      3. a bare generated line

    (Phase 3 folds in the vault's VAULT-INDEX.md here too.)
    """
    try:
        text = CLAUDE_MD.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _bare_persona()
    return persona_from_text(text) or _bare_persona()
