"""First-run wizard: pick (and pull) the local model, optionally wire a
cloud "big brain", write config/models.yaml.

start.ps1 / start.sh call `python -m jarvis_brain check` before launching the
voice line; a non-zero exit sends them here.

    python -m jarvis_brain configure           # interactive
    python -m jarvis_brain configure --defaults # no prompts (qwen3:8b, no cloud)
    python -m jarvis_brain check                # exit 0 iff ready to run
"""
from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import sys
import time
from getpass import getpass

from pathlib import Path

from .config import (
    REPO_ROOT,
    BigProviderCfg,
    BrainCfg,
    ConfigError,
    LocalModelCfg,
    MODELS_YAML,
    SpecializedProviderCfg,
    device_name,
    load_brain_cfg,
    load_jarvis_json,
    save_brain_cfg,
    save_jarvis_json,
    vault_dir,
)
from .providers.ollama import OllamaClient, OllamaDown

RECOMMENDED = [
    ("qwen3:8b", "recommended — strong tool-calling, bilingual, ~5 GB"),
    ("qwen3:4b", "lighter — 8 GB RAM machines, ~2.6 GB"),
    ("llama3.1:8b", "alternative — solid tool-calling, ~4.9 GB"),
    ("qwen3:14b", "bigger — needs ~12 GB RAM / VRAM, ~9 GB"),
    ("gemma3:4b", "small + multilingual + vision, ~3.3 GB"),
]
DEFAULT_MODEL = "qwen3:8b"


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
for _stream in (sys.stdout, sys.stderr):
    try:  # Windows consoles / piped output default to a legacy codepage
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _run(coro):
    return asyncio.run(coro)


def _ollama_install_hint() -> str:
    sysname = platform.system()
    if sysname == "Windows":
        return "Install Ollama: https://ollama.com/download/windows  (then reopen the terminal)"
    if sysname == "Darwin":
        return "Install Ollama: https://ollama.com/download/mac   (or: brew install ollama)"
    return "Install Ollama: curl -fsSL https://ollama.com/install.sh | sh"


def _ensure_ollama_binary() -> str:
    exe = shutil.which("ollama")
    if not exe:
        _p("✗ Ollama is not installed (or not on PATH).")
        _p("  " + _ollama_install_hint())
        raise SystemExit(1)
    return exe


def _ensure_ollama_running(client: OllamaClient, *, try_start: bool = True) -> None:
    if _run(client.is_up()):
        return
    if not try_start:
        _p(f"✗ Ollama server not answering at {client.base_url}.")
        _p("  Start it with:  ollama serve   (or launch the Ollama app)")
        raise SystemExit(1)
    _p("… Ollama server isn't running — starting it")
    creationflags = 0
    kwargs: dict = {}
    if platform.system() == "Windows":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            **kwargs,
        )
    except OSError as e:
        _p(f"✗ couldn't start `ollama serve`: {e}")
        raise SystemExit(1) from e
    for _ in range(20):
        time.sleep(0.5)
        if _run(client.is_up()):
            _p("✓ Ollama server is up")
            return
    _p("✗ started `ollama serve` but it never came up. Start it manually and retry.")
    raise SystemExit(1)


def _write_env_var(key: str, value: str) -> None:
    """Append KEY=value to the repo .env if that key isn't already set there."""
    env_path = REPO_ROOT / ".env"
    existing = ""
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8")
        for line in existing.splitlines():
            if line.strip().startswith(f"{key}="):
                _p(f"  ({key} already in .env — leaving it)")
                return
    sep = "" if (not existing or existing.endswith("\n")) else "\n"
    with env_path.open("a", encoding="utf-8") as f:
        f.write(f"{sep}{key}={value}\n")
    _p(f"  wrote {key} to .env")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        ans = ""
    return ans or default


# --------------------------------------------------------------------------- #
# vault (Phase 3) — chosen on first run
# --------------------------------------------------------------------------- #
_VAULT_SUBDIRS = ["01 - Daily Notes", "04 - Sessions", "People", "Projects"]

_VAULT_INDEX_STUB = """\
# VAULT-INDEX

The assistant reads this file to know the shape of your memory. Edit freely.

## Profile
- (a line or two about you — the assistant primes on this)

## Note sets
Named lists of notes the assistant reads before a task. Format: `name: A.md, B.md`

- coding: Projects/Notes.md, People/Me.md
- personal: People/Me.md
"""

_VAULT_README = """\
# Memory vault

Plain-markdown memory for the assistant. Put this folder inside your
Google Drive (or iCloud / Dropbox) sync root so every device shares it.
`scripts/vault_commit.py` snapshots it with git every 30 minutes.
See `docs/SYNC.md` in the Jarvis repo.
"""


def _guess_vault_path() -> str:
    home = Path.home()
    sysname = platform.system()
    candidates: list[Path] = []
    if sysname == "Windows":
        candidates += [home / "My Drive", home / "Google Drive" / "My Drive",
                       home / "Google Drive", home / "OneDrive"]
    elif sysname == "Darwin":
        cs = home / "Library" / "CloudStorage"
        if cs.is_dir():
            candidates += sorted(cs.glob("GoogleDrive-*/My Drive"))
        candidates += [home / "Google Drive" / "My Drive", home / "Google Drive"]
    for base in candidates:
        if base.is_dir():
            return str(base / "Jarvis Vault")
    return str(home / "Jarvis Vault")


def _scaffold_vault(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for sub in _VAULT_SUBDIRS:
        (path / sub).mkdir(exist_ok=True)
    idx = path / "VAULT-INDEX.md"
    if not idx.exists():
        idx.write_text(_VAULT_INDEX_STUB, encoding="utf-8")
    rd = path / "README.md"
    if not rd.exists():
        rd.write_text(_VAULT_README, encoding="utf-8")


def _choose_vault(existing_path: str) -> tuple[str, str]:
    """Returns (vault_path, device_name). Creates the folder + skeleton."""
    _p()
    _p("Memory vault")
    _p("───────────")
    _p("A folder of plain markdown the assistant remembers you in. Put it inside")
    _p("your Google Drive sync root and every device shares one memory.")
    default = existing_path or _guess_vault_path()
    raw = _ask("Vault folder", default=default)
    path = Path(os.path.expanduser(raw)).resolve()
    try:
        _scaffold_vault(path)
        _p(f"✓ vault ready at {path}")
    except OSError as e:
        _p(f"⚠  could not create {path}: {e}  (set vault_path by hand later)")
    dev = _ask("Short name for THIS device (for per-device note files)",
               default=device_name())
    return str(path), dev


# --------------------------------------------------------------------------- #
# the wizard
# --------------------------------------------------------------------------- #
def _choose_local_model(client: OllamaClient) -> str:
    try:
        installed = _run(client.list_models())
    except OllamaDown:
        installed = []

    _p()
    _p("Local model")
    _p("───────────")
    if installed:
        _p("Already pulled on this machine:")
        for i, name in enumerate(installed, 1):
            _p(f"  {i:>2}. {name}")
    else:
        _p("(nothing pulled yet)")
    _p()
    _p("Recommended to pull:")
    for name, note in RECOMMENDED:
        marker = " ✓ installed" if name in installed else ""
        _p(f"      {name:<14} {note}{marker}")
    _p()

    choice = _ask(
        "Pick a number from the installed list, or type a model name to use/pull",
        default=DEFAULT_MODEL if not installed else installed[0],
    )
    if choice.isdigit() and installed and 1 <= int(choice) <= len(installed):
        return installed[int(choice) - 1]
    return choice


def _pull_if_needed(client: OllamaClient, model: str) -> None:
    if _run(client.has_model(model)):
        _p(f"✓ {model} is available")
        return
    _p(f"… pulling {model}  (this can take a few minutes)")
    try:
        _run(client.pull(model, on_progress=lambda s: _p(f"    {s}")))
    except (OllamaDown, RuntimeError) as e:
        _p(f"✗ pull failed: {e}")
        _p("  Check the model name against https://ollama.com/library and retry.")
        raise SystemExit(1) from e
    _p(f"✓ pulled {model}")


_API_PRESETS = {
    "o": ("openrouter", "OPENROUTER_API_KEY", "deepseek/deepseek-chat", ""),
    "a": ("anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-5", ""),
    "x": ("openai", "OPENAI_API_KEY", "gpt-4o", ""),
    "g": ("groq", "GROQ_API_KEY", "llama-3.3-70b-versatile", ""),
}
_SPECIAL_PRESETS = {
    "kie.ai": ("https://api.kie.ai", "KIE_API_KEY"),
    "higgsfield": ("https://platform.higgsfield.ai/api", "HIGGSFIELD_API_KEY"),
    "fal": ("https://fal.run", "FAL_KEY"),
    "replicate": ("https://api.replicate.com/v1", "REPLICATE_API_TOKEN"),
    "elevenlabs": ("https://api.elevenlabs.io/v1", "ELEVENLABS_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}


def _describe_big(b: BigProviderCfg) -> str:
    return b.label


def _ask_api_provider() -> BigProviderCfg:
    _p("    o) OpenRouter   a) Anthropic   x) OpenAI   g) Groq   c) other (OpenAI-compatible)")
    p = _ask("  which API", default="o").lower()[:1]
    if p == "c":
        provider = _ask("  provider label", default="custom") or "custom"
        env = _ask("  env var name for the key", default=f"{provider.upper()}_API_KEY")
        base = _ask("  base_url (ends in /v1)", default="")
        model = _ask("  model id", default="")
    else:
        provider, env, model_default, base = _API_PRESETS.get(p, _API_PRESETS["o"])
        model = _ask("  model id", default=model_default)
    key = getpass(f"  {env} (hidden, Enter to set later in .env): ").strip()
    if key:
        _write_env_var(env, key)
    if provider == "anthropic":
        _p("  ⚠  also set a hard spend limit in the Anthropic billing console.")
    return BigProviderCfg(kind="api", provider=provider, model=model,
                          api_key_env=env, base_url=base)


def _configure_big_brain(current: list[BigProviderCfg]) -> list[BigProviderCfg]:
    from .providers.cli_bridge import which_supported

    _p()
    _p('"Big brain" — a stronger model for the occasional hard turn')
    _p('(used ONLY when you say "use the big brain")')
    _p("──────────────────────────────────────────────────────────")
    found = which_supported()
    opts: list[tuple[str, str]] = []
    if found:
        _p("Subscriptions detected on this machine (no API key needed):")
        for c in found:
            opts.append(("cli", c))
            _p(f"  {len(opts)}) {c}   — your existing {c} plan")
    else:
        _p("(no claude / codex / gemini CLI found on PATH)")
    opts.append(("api", ""))
    _p(f"  {len(opts)}) API key  (OpenRouter / OpenAI / Anthropic / Groq / other)")
    _p("  s) skip — stay fully local")
    if current:
        _p(f"  Enter) keep current: {', '.join(_describe_big(b) for b in current)}")

    pick = _ask("Choose (comma-separate for fallbacks, e.g. 1,3)", default="")
    if pick == "" and current:
        return current
    if pick.strip().lower() in ("s", "skip"):
        _p("  skipped — escalation is off.")
        return []

    chosen: list[BigProviderCfg] = []
    for tok in pick.split(","):
        tok = tok.strip()
        if not tok.isdigit():
            continue
        n = int(tok)
        if 1 <= n <= len(opts):
            kind, cli = opts[n - 1]
            if kind == "cli":
                model = _ask(f"  {cli} model id (Enter = its default)", default="")
                chosen.append(BigProviderCfg(kind="cli", cli=cli, model=model))
            else:
                chosen.append(_ask_api_provider())
    if not chosen:
        _p("  nothing valid picked — leaving escalation off.")
    return chosen


def _configure_specialized(
    current: dict[str, SpecializedProviderCfg]
) -> dict[str, SpecializedProviderCfg]:
    out = dict(current)
    _p()
    _p("Specialized providers — keys for image / video / audio generation and")
    _p("any other non-chat task. Add as many as you want; Enter to finish.")
    _p("──────────────────────────────────────────────────────────────────")
    if out:
        for cap, s in out.items():
            state = "key set" if s.configured else f"key MISSING ({s.api_key_env})"
            _p(f"  have: {cap} -> {s.provider}  [{state}]")
    while True:
        cap = _ask("Capability (e.g. image, video, music, ocr) — Enter to finish",
                   default="")
        if not cap:
            break
        _p(f"  known providers: {', '.join(_SPECIAL_PRESETS)}  (or type your own)")
        prov = _ask("  provider", default="kie.ai")
        base_d, env_d = _SPECIAL_PRESETS.get(prov, ("", f"{cap.upper()}_API_KEY"))
        base = _ask("  base_url", default=base_d)
        env = _ask("  env var name for the key", default=env_d)
        model = _ask("  default model / endpoint (optional)", default="")
        key = getpass(f"  {env} (hidden, Enter to set later in .env): ").strip()
        if key:
            _write_env_var(env, key)
        out[cap] = SpecializedProviderCfg(
            capability=cap, provider=prov, base_url=base,
            api_key_env=env, model=model,
        )
        _p(f"  ✓ {cap} -> {prov}")
    return out


def run_keys() -> int:
    """`python -m jarvis_brain keys` — manage big-brain + specialized providers
    without the full wizard."""
    if not sys.stdin.isatty():
        _p("✗ `keys` needs an interactive terminal.")
        _p("  Run it in a real shell:  python -m jarvis_brain keys")
        return 2
    try:
        cfg = load_brain_cfg(required=False)
    except ConfigError:
        cfg = BrainCfg()
    _p("Current big-brain providers:")
    for b in cfg.big:
        _p(f"  - {_describe_big(b)}")
    if not cfg.big:
        _p("  (none)")
    picked = _configure_big_brain(cfg.big)
    if picked:
        cfg.big = picked
    cfg.specialized = _configure_specialized(cfg.specialized)
    save_brain_cfg(cfg)
    _p()
    _p(f"✓ wrote {MODELS_YAML.name}  (secrets went to .env)")
    return 0


def _smoke_test(cfg: BrainCfg) -> None:
    _p()
    _p(f"… quick check: asking {cfg.local.model} to say hello")
    from . import core

    async def go() -> str:
        out = []
        async for s in core.run_turn(
            "Reply with exactly one short friendly sentence.",
            [],
            brain_cfg=cfg,
            persona="You are a terse assistant.",
            discipline="One sentence. No markdown.",
        ):
            out.append(s)
        return " ".join(out)

    try:
        reply = asyncio.run(asyncio.wait_for(go(), 120))
    except Exception as e:  # noqa: BLE001 - wizard: report and move on
        _p(f"  ⚠  the test call failed: {e}")
        _p("     The config is saved anyway; debug with `python -m jarvis_brain chat`.")
        return
    _p(f"  ✓ {reply.strip()[:200] or '(empty reply)'}")


def run_wizard(*, use_defaults: bool = False) -> int:
    _p("┌─────────────────────────────────────────────┐")
    _p("│  Jarvis — local LLM setup                    │")
    _p("└─────────────────────────────────────────────┘")

    try:
        existing = load_brain_cfg(required=False)
    except ConfigError:
        existing = BrainCfg()

    if existing.is_configured and not use_defaults:
        big_s = ", ".join(_describe_big(b) for b in existing.big) or "off"
        spec_s = ", ".join(existing.specialized) or "none"
        _p(f"Already configured: local = {existing.local.model} | "
           f"big brain = {big_s} | specialized = {spec_s}")
        if _ask("Reconfigure?", default="n").lower()[:1] != "y":
            _p("Keeping the current config.")
            return 0

    if not use_defaults and not sys.stdin.isatty():
        _p("✗ This wizard needs an interactive terminal.")
        _p("  Run it yourself:  cd " + str(REPO_ROOT))
        _p("                    python -m jarvis_brain configure")
        _p("  Or accept defaults:  python -m jarvis_brain configure --defaults")
        return 2

    ident = load_jarvis_json()

    # --- Phase 3: pick the memory vault --------------------------------------
    if use_defaults:
        if not ident.get("vault_path"):
            v = _guess_vault_path()
            try:
                _scaffold_vault(Path(os.path.expanduser(v)))
            except OSError:
                pass
            ident["vault_path"] = v
            ident.setdefault("device_name", device_name())
            save_jarvis_json(ident)
    else:
        vpath, dev = _choose_vault(ident.get("vault_path", ""))
        ident["vault_path"] = vpath
        ident["device_name"] = dev
        save_jarvis_json(ident)

    _ensure_ollama_binary()
    base_url = existing.local.base_url or "http://localhost:11434"
    client = OllamaClient(base_url=base_url)
    _ensure_ollama_running(client)

    if use_defaults:
        model = existing.local.model or DEFAULT_MODEL
        big = existing.big
        specialized = existing.specialized
        cap = existing.monthly_cloud_cap_inr
    else:
        model = _choose_local_model(client) or DEFAULT_MODEL
        _pull_if_needed(client, model)
        big = _configure_big_brain(existing.big)
        cap = int(_ask("Monthly cloud budget cap in INR (API calls only; "
                       "subscriptions don't count)",
                       default=str(existing.monthly_cloud_cap_inr)) or 1000)
        specialized = _configure_specialized(existing.specialized)

    if use_defaults:
        _pull_if_needed(client, model)

    cfg = BrainCfg(
        mode="local",
        local=LocalModelCfg(
            provider="ollama",
            base_url=base_url,
            model=model,
            keep_alive=existing.local.keep_alive if existing.is_configured else -1,
            context=existing.local.context if existing.is_configured else 8192,
            temperature=existing.local.temperature,
            languages=existing.local.languages or ["en", "hi"],
        ),
        big=big,
        specialized=specialized,
        monthly_cloud_cap_inr=cap,
        never_escalate_tags=existing.never_escalate_tags,
        _raw=existing._raw,
    )
    save_brain_cfg(cfg)
    _p()
    _p(f"✓ wrote {MODELS_YAML.relative_to(REPO_ROOT)}")

    if not use_defaults:
        _smoke_test(cfg)

    _p()
    _p("Done. Launch the voice line with:")
    _p("  Windows :  .\\start.ps1")
    _p("  mac/Lin :  ./start.sh")
    return 0


def check() -> int:
    """Exit 0 iff the brain is ready: models.yaml valid, Ollama up, model pulled."""
    try:
        cfg = load_brain_cfg(required=True)
    except ConfigError as e:
        _p(f"not configured: {e}")
        return 1
    client = OllamaClient(base_url=cfg.local.base_url)
    if not _run(client.is_up()):
        _p(f"Ollama not running at {cfg.local.base_url} (start it with `ollama serve`)")
        return 3
    if not _run(client.has_model(cfg.local.model)):
        _p(f"model {cfg.local.model} not pulled")
        return 4
    v = vault_dir()
    vtag = str(v) if load_jarvis_json().get("vault_path") else f"{v} (repo-local, not synced)"
    _p(f"ready: {cfg.local.model} @ {cfg.local.base_url}")
    _p(f"vault: {vtag}")
    if cfg.big:
        _p("big brain: " + ", ".join(_describe_big(b) for b in cfg.big))
    for cap, s in cfg.specialized.items():
        state = "ok" if s.configured else f"MISSING key ({s.api_key_env})"
        _p(f"specialized[{cap}]: {s.provider} — {state}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    use_defaults = "--defaults" in argv
    return run_wizard(use_defaults=use_defaults)


if __name__ == "__main__":
    raise SystemExit(main())
