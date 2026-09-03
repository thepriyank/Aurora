# REPO REUSE MAP — what we take from `jaredrhod/*`, and what we change

Source: `https://github.com/jaredrhod/fullstack-agent` and its four sibling repos.
License on all of them: **AGPL-3.0** (see plan §5 note 6).

**Golden rule:** everything upstream goes in `vendor/` as a **git subtree**. Patches stay surgical and visible as commits so `update.sh` can pull upstream fixes.

```bash
# Phase 0 — import (run once each)
git subtree add --prefix vendor/backtalk        https://github.com/jaredrhod/backtalk        main --squash
git subtree add --prefix vendor/ai-memory-vault https://github.com/jaredrhod/ai-memory-vault main --squash
git subtree add --prefix vendor/barehands       https://github.com/jaredrhod/barehands       main --squash
git subtree add --prefix vendor/ai-visualizer   https://github.com/jaredrhod/ai-visualizer   main --squash

# later — pull upstream fixes
git subtree pull --prefix vendor/backtalk https://github.com/jaredrhod/backtalk main --squash
```

---

## 1. `backtalk` — voice front-end  → **PATCH (one file)**

| Upstream piece | Verdict | Notes |
|---|---|---|
| `backtalk/ptt.py` (global push-to-talk key listener) | **KEEP as-is** | Our interrupt key, unchanged |
| `faster-whisper` STT path | **KEEP as-is** | Phase 7 only *adds* a detected-language field |
| Kokoro TTS + `espeak-ng` phonemisation, `bm_lewis` voice | **KEEP as-is** | Phase 7 adds a Hindi voice path alongside |
| Sentence-by-sentence streaming to TTS | **KEEP as-is** | Our `brain/core.py` yields text the same shape |
| Signal-bus writer (`.voice_state`, `.voice_waveform`, `.voice_loading_pid`, `state/state`) | **KEEP as-is** | The overlay and Android glow read exactly these |
| `backtalk.json` config keys (`agent_dir`, `ptt_key`, `voice`, `speed`, `mic_device`, `signals_dir`, `barehands_state_dir`, `resume_last_session`, `thinking_sound`, permission mode) | **KEEP**, **ADD** one key: `"brain": "local" \| "claude"` | Default `local` |
| **Claude Agent SDK session construction** (the brain — in `backtalk/main.py` per upstream docs) | **PATCH** | Branch: `brain=="local"` → stream from `brain.core.run_turn(text, history)`; `brain=="claude"` → original path untouched |
| `install.sh` / `run.sh` / Windows `uv run python -m backtalk.main` | **KEEP**, call from our forked `start.sh` | |
| `TROUBLESHOOTING.md` | **KEEP** | Feeds the "you are the mechanic" self-repair pattern |

**The entire brain swap is one guarded branch in one file.** If you're touching anything else in `backtalk`, stop and reconsider.

---

## 2. `ai-memory-vault` — memory  → **KEEP (almost untouched)**

| Upstream piece | Verdict | Notes |
|---|---|---|
| Obsidian install + vault creation wizard | **KEEP** | Runs in Phase 0 |
| `VAULT-INDEX.md` (profile, projects, rules, "read these notes first" sets) | **KEEP + EXTEND** | Becomes our tool/priming manifest in Phase 2 (`read_note_set`) |
| `CLAUDE.md` in the home folder (identity, startup rules) | **KEEP + EXTEND** | See `03_CLAUDE_MD_TEMPLATE.md` — we add tool allowlist, trigger phrases, vault path |
| `01 - Daily Notes/Daily Note Template.md` | **KEEP** | Phase 3 changes only the *filename pattern* to per-device shards |
| `MEMORY.md` pointer in `~/.claude/projects/...` | **KEEP** | Only used in hybrid Claude Code mode; harmless otherwise |
| Plain-markdown, no-vector-DB, no-lock design | **KEEP — this is the whole point** | It's what makes Google Drive sync + git history feasible |
| Non-destructive updater (vault never in the repo) | **KEEP** | Our vault lives in Google Drive, outside `jarvis/` |

**New, built by us (not a fork):** `scripts/vault_commit` (git snapshots), the nightly per-device shard consolidation job, `docs/SYNC.md`.

---

## 3. `ai-visualizer` — the "face"  → **DROP as a runtime, KEEP the contract**

| Upstream piece | Verdict | Notes |
|---|---|---|
| The four faces (circuit board, radial, rain, neural) | **DROP** | You don't want a full-screen face |
| The stdlib Python server on `127.0.0.1:8790` | **DROP** | Our overlay reads the bus files directly |
| **Signal-bus contract**: `.voice_state` = `idle\|listening\|thinking\|speaking`; `.voice_waveform` = `{ts, samples:[64 floats]}`; `.voice_loading_pid` presence = thinking | **KEEP — copy into `docs/SIGNAL_BUS.md`** | Our `overlay/` and Android glow implement a consumer of this exact contract |
| "faces drop into `faces/` with `index.html`, call `AV.init()`, read `AV.state`/`AV.env`/`AV.samples` in a draw loop" | **KEEP as a pattern** | Our `overlay/renderer/` is shaped the same way, just with a VRM instead of a face |
| OBS browser-source / fullscreen `F` / `?demo=1` mock mode | **OPTIONAL KEEP** | `?demo=1`-style mock is useful for building the overlay without the voice running |

**Replaced by (built by us):** `overlay/` — Electron + `three.js` + `@pixiv/three-vrm` floating avatar (Phase 5), and the Android edge-glow service (Phase 8).

---

## 4. `barehands` — hands / hologram  → **REUSE HEAVILY, re-host on-device**

| Upstream piece | Verdict | Notes |
|---|---|---|
| `stage.html` — three.js board + hologram render | **REUSE** | Mounted inside `overlay/` in Phase 6; ported to a GL surface on Android in Phase 10 |
| Google **MediaPipe Hands** integration (CDN-loaded) | **REUSE** | Desktop: keep CDN/`getUserMedia`. Android: swap to **MediaPipe Tasks Hand Landmarker** |
| Ratio-based gesture classifier — tap, pinch-drag, hold-still-rotate, two-hand-scale, flick, clap, claw, empty-pinch-sideways-explode | **REUSE — do NOT re-tune the thresholds** | Upstream note: "tuned on a real hand across weeks of live use" |
| `state/state` file (`thinking\|idle\|listening\|speaking` → ring feedback) | **KEEP** | `backtalk` already can write `barehands_state_dir`; brain sets it on "see me" |
| `bin/board.sh` verbs: `present`, `add_card`, `add_img`, `hand`, `explode`, `yank`, `hover` | **PORT** to a localhost endpoint the brain calls | So the assistant can stage a note/image/model mid-conversation |
| `bin/board-state.sh` (returns board JSON) | **PORT** | Gives the brain "board awareness" |
| `server.py` (stdlib) on `127.0.0.1:8794`, `stage.html?role=render` transparent mode, `?portrait=1`, `?ss=2` | **REUSE selectively** | Desktop overlay can embed `?role=render`; `?portrait=1` maps to the phone |
| `media/` jail — only `media/misc|fx|models|holo/` render; `media/holo/*` → blue hologram wireframe | **KEEP** | This is also our filesystem-safety model for the board |
| `barehands.json` (`name`, `orbs:[{title,path,kind}]`) | **KEEP + point `orbs` at the vault** | e.g. `{title:"Notes", path:"<vault>", kind:"notes"}` |
| `run.bat` Python-finder (Windows 11) | **KEEP** | Reused by our `start.ps1` |

**New, built by us:** the "see me" trigger + `overlay.see_me()` tool (Phase 6), the Android `HandsActivity` (Phase 10), the board-command HTTP endpoint.

---

## 5. `fullstack-agent` — the installer itself  → **FORK the launcher, replace the wizard**

| Upstream piece | Verdict | Notes |
|---|---|---|
| `start.sh` / `start.bat` (`voice` / `hands` / `chat` modes) | **FORK** into repo-root `start.sh` / `start.ps1` | Repoint paths at `vendor/*` and start our `brain/` + `overlay/` |
| `update.sh` / `update.bat` | **FORK** | Becomes `git subtree pull` for each `vendor/*` + config re-wire |
| The interview wizard (single Q&A, writes all the `*.json` + home `CLAUDE.md`) | **REPLACE** with our `install.ps1`/`install.sh` (Phase 12) | Same idea, our config set |
| The file signal-bus wiring (`bus_dir` in visualizer config → backtalk folder) | **KEEP the concept** | Our configs wire `overlay.bus_dir` → `backtalk.signals_dir` |
| "never delete/overwrite/move what the user built" principle | **KEEP** | Applies doubly to the Drive-synced vault |
| Desktop shortcuts (Chat / Talk / Barehands / Update) | **KEEP**, regenerate for our modes | "Talk" starts brain+backtalk+overlay; "See me" is now a voice command, not a separate shortcut |

---

## 6. Quick contributor checklist

- [ ] Never edit `vendor/` except the single documented `backtalk` brain branch and the ported `barehands` `bin/` verbs — everything else is additive in `brain/`, `overlay/`, `android/`.
- [ ] Every `vendor/` change is its own commit prefixed `patch(vendor):` with a one-line why.
- [ ] `docs/SIGNAL_BUS.md` and `docs/BASELINE.md` are copied out of upstream in Phase 0 and are the source of truth for the bus contract and the known-good setup.
- [ ] Keep `brain=="claude"` working forever — it's the fastest way to bisect "is this the model or my code?".
