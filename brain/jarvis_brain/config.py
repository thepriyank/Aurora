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
    provider: str
    model: str
    api_key_env: str = ""


@dataclass
class BrainCfg:
    mode: str = "local"
    local: LocalModelCfg = field(default_factory=LocalModelCfg)
    big: list[BigProviderCfg] = field(default_factory=list)
    monthly_cloud_cap_inr: int = 1000
    never_escalate_tags: list[str] = field(
        default_factory=lambda: ["private", "health", "finance_personal", "family"]
    )
    _raw: dict = field(default_factory=dict, repr=False)

    # -- convenience ------------------------------------------------------- #
    @property
    def is_configured(self) -> bool:
        return bool(self.local.model)


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
    big = [
        BigProviderCfg(
            provider=p.get("provider", ""),
            model=p.get("model", ""),
            api_key_env=p.get("api_key_env", ""),
        )
        for p in (b.get("big") or [])
        if isinstance(p, dict) and p.get("provider") and p.get("model")
    ]
    cfg = BrainCfg(
        mode=b.get("mode", "local"),
        local=local,
        big=big,
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
    return cfg


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
        "big": [
            {"provider": p.provider, "model": p.model, "api_key_env": p.api_key_env}
            for p in cfg.big
        ],
        "monthly_cloud_cap_inr": cfg.monthly_cloud_cap_inr,
        "never_escalate_tags": cfg.never_escalate_tags,
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


def load_persona() -> str:
    """The agent's spoken identity.

    Precedence:
      1. the block between <!-- PERSONA:START --> / <!-- PERSONA:END --> in CLAUDE.md
      2. a `persona` string in config/jarvis.json
      3. a bare generated line

    The WHOLE CLAUDE.md is a dev/architecture document — feeding all of it to a
    small local model makes it answer *about* the file. The marked block is the
    part that actually is the character. (Phase 3 folds in the vault's
    VAULT-INDEX.md here too.)
    """
    try:
        text = CLAUDE_MD.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _bare_persona()

    if _PERSONA_START in text and _PERSONA_END in text:
        block = text.split(_PERSONA_START, 1)[1].split(_PERSONA_END, 1)[0].strip()
        if block:
            name = load_jarvis_json().get("name", "Assistant")
            return block.replace("{name}", name)
    return _bare_persona()
