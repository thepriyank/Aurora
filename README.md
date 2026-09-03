# Jarvis

A personal, local-first voice assistant. Built by **forking and re-wiring**
[`jaredrhod/fullstack-agent`](https://github.com/jaredrhod/fullstack-agent) rather than from
scratch: keep `backtalk` (voice) and `ai-memory-vault` (Obsidian memory), swap the brain to
a **local LLM** (Ollama), drop the browser visualizer for a floating 3D overlay, and move
`barehands` (hand-gesture hologram) on-device behind a spoken **"see me"**. Runs on Windows,
macOS, and Android.

Full plan: [`docs/00_MASTER_BUILD_PLAN.md`](docs/00_MASTER_BUILD_PLAN.md) ·
reuse map: [`docs/05_REPO_REUSE_MAP.md`](docs/05_REPO_REUSE_MAP.md).

## Status

**Phase 1 — local brain.** `jarvis_brain` (the Ollama agent core + first-run setup wizard)
is in place; the `backtalk` brain-swap patch and the end-to-end voice test come next.

## Quick start

```
# Windows
.\start.ps1            # runs the LLM setup wizard on first launch, then the voice line
.\start.ps1 chat       # text-only REPL against the local brain (no mic)
.\start.ps1 configure  # re-run the setup wizard

# macOS / Linux
./start.sh   |   ./start.sh chat   |   ./start.sh configure
```

Prerequisites: [`uv`](https://github.com/astral-sh/uv), [Ollama](https://ollama.com/download),
Python 3.12. See [`docs/01_YOUR_SETUP_CHECKLIST.md`](docs/01_YOUR_SETUP_CHECKLIST.md).

## Layout

| Path | What |
|---|---|
| `brain/` | `jarvis_brain` — local LLM agent core, providers, first-run wizard |
| `vendor/backtalk/` | fork of `jaredrhod/backtalk`; one guarded patch swaps the brain |
| `config/jarvis.json` | identity: name, wake words, trigger phrases |
| `config/models.yaml` | brain registry (written by the wizard; git-ignored) |
| `CLAUDE.md` | agent persona — read by `jarvis_brain` and by Claude Code |
| `docs/` | the build plan |

## License

The vendored `jaredrhod/*` components are **AGPL-3.0**; changes under `vendor/` inherit it.
