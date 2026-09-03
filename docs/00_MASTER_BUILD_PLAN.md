# MASTER BUILD PLAN — Personal AI Assistant ("Jarvis-class"), built on the jaredrhod stack

**Codename in this doc:** `ASSISTANT` (real name + wake word live in config, changeable any time)
**Target platforms:** Windows, macOS, Android
**Languages:** English + Hindi (including Hinglish code-switching)
**Brain policy:** **local LLM first** (Ollama). Cloud only on an explicit spoken command, with a hard monthly cap.
**Build strategy:** **fork and re-wire the `jaredrhod/fullstack-agent` stack** — do not rebuild from scratch.
**Build tool:** Claude Code, phase by phase.

---

## 0. HOW TO USE THIS DOCUMENT

- Each phase has: **Goal → What gets built → What we reuse → Definition of Done → a copy-paste Claude Code prompt.**
- Build phases **in order**. Later phases assume earlier contracts exist.
- Before starting, put `03_CLAUDE_MD_TEMPLATE.md` in your **agent home folder** as `CLAUDE.md`. Both the local brain and (in hybrid mode) Claude Code read it every session.
- `05_REPO_REUSE_MAP.md` is the file-by-file "keep / patch / replace / drop" map for the four upstream repos. Consult it every phase.
- Anything requiring you to sign up somewhere is in `01_YOUR_SETUP_CHECKLIST.md`. Hosting/sync decisions are in `02_DEPLOYMENT_OPTIONS.md`.
- **Rule of thumb:** finish a phase, run its check, commit, tag it (`git tag phase-3-done`), then start the next.

---

## 1. WHAT YOU ARE ACTUALLY BUILDING (plain English)

You are taking four small, working open-source projects and changing three things about them:

| Upstream piece | What it does now | What we change |
|---|---|---|
| **`ai-memory-vault`** | Obsidian vault of plain markdown = the agent's memory. No vector DB. | **Keep almost as-is.** Add Google-Drive sync across all 3 devices + a nightly `git commit` for history. |
| **`backtalk`** | Push-to-talk voice: `faster-whisper` STT + Kokoro TTS. Brain = **Claude Agent SDK**. Has its own personality + tool loop. | **Swap the brain** to a local LLM (Ollama) via a new `brain/` agent core. Keep the STT, TTS, PTT, and signal-bus code untouched. |
| **`ai-visualizer`** | Full-screen browser "face" (circuit board, rain, etc.). | **Drop it.** Replace with a **floating 3D avatar overlay** on desktop and a **screen-edge glow** on Android. Reuse only its signal-bus contract. |
| **`barehands`** | Browser page (`stage.html`) with a three.js board + MediaPipe hand tracking + blue "hologram" models. | **Keep the code**, move it **on-device**: it runs inside the desktop overlay shell and (later) a native Android surface, triggered by the spoken command **"see me"**. |

Everything is glued by the same trick the upstream stack already uses: **the voice process writes tiny state files; the visuals read them. That is the whole connection.**

### 1.1 Architecture at a glance

```
┌───────────────────────────────────────────────────────────────────────┐
│ DESKTOP (Windows / macOS)  — native processes, started by start.sh    │
│                                                                       │
│  backtalk (PTT + STT + TTS)  ──writes──▶  signal bus (.voice_state,   │
│      │  transcript                        .voice_waveform, state/)     │
│      ▼                                          │                      │
│  brain/  (NEW local agent core)                 ▼                      │
│   • Ollama chat loop (OpenAI-compatible)   overlay/ (NEW, Electron)   │
│   • MCP tool client (fs, shell, web, git)   • transparent, click-thru │
│   • Obsidian vault read/write               • three-vrm 3D avatar     │
│   • "use the big brain" → cloud (capped)    • lip-sync from waveform  │
│   • "see me" → tells overlay to open stage  • "see me": mounts        │
│      │                                         barehands board +      │
│      ▼                                          MediaPipe Hands       │
│  Obsidian vault  ◀── Google Drive Desktop ──▶  (cloud) ──▶ phone     │
└───────────────────────────────────────────────────────────────────────┘
                              ▲  Tailscale
                              │  (phone ↔ desktop brain: POST /turn, /state)
┌───────────────────────────────────────────────────────────────────────┐
│ ANDROID (Flutter)                                                      │
│  • PTT + on-device STT/TTS                                            │
│  • screen-edge GLOW overlay (SYSTEM_ALERT_WINDOW + foreground svc),   │
│    colour/pulse driven by voice state                                 │
│  • brain toggle:  [Desktop Hub over Tailscale]  ◀or▶  [on-device      │
│    small model + local vault copy]                                    │
│  • "see me" (later phase): full-screen camera + MediaPipe Tasks Hands │
│  • vault = Drive-synced folder on the phone                           │
└───────────────────────────────────────────────────────────────────────┘
```

### 1.2 Tech stack decisions (locked, so Claude Code doesn't drift)

| Layer | Choice | Why |
|---|---|---|
| Voice front-end | **`backtalk`, forked** (`faster-whisper` STT, Kokoro TTS, `ptt.py`) | Already works on Win/Mac/Linux; do not reinvent |
| Brain runtime | **New `brain/` core**: Python + `httpx`/`ollama`, OpenAI-compatible loop | Minimal, debuggable, matches the upstream "tiny Python" philosophy |
| Local inference | **Ollama** (native on host) | Zero-friction, keeps the model warm across restarts |
| Model API shape | OpenAI-compatible everywhere | One adapter covers Ollama, OpenRouter, Groq, Anthropic-compat |
| Tools protocol | **MCP (Model Context Protocol)** | Standard tool interface; reuse existing servers (filesystem, git, brave-search) |
| Memory | **`ai-memory-vault`** — Obsidian + plain markdown, **no vector DB** | You said you like it; retrieval is "read this note set first", not embeddings |
| Memory sync | **Obsidian vault inside a Google Drive folder** + nightly `git commit` | Same memory on every device; git = free history/restore |
| Desktop body | **New `overlay/`**: Electron (transparent, always-on-top, click-through) + `three.js` + `@pixiv/three-vrm` | 3D `.vrm` avatar; same window later hosts the barehands stage |
| Hands / hologram | **`barehands`, reused** (three.js board + Google MediaPipe Hands) inside the overlay shell | Its gesture engine is tuned already; don't retune thresholds |
| Android client | **Flutter** (Kotlin platform channels for overlay + MediaPipe Tasks) | Best background-service + audio story for a solo dev |
| Android body | Screen-edge **glow** via `SYSTEM_ALERT_WINDOW` + foreground service | You asked for "a simple overlay border effect" on the phone |
| Networking | **Tailscale** | Phone reaches the desktop brain with no port-forwarding |
| Cloud escalation | OpenRouter (free open-weight) → one paid key, **opt-in per turn**, hard-capped | "use the big brain" only; never automatic |

**Dropped from the earlier draft of this plan:** Postgres, Qdrant, Redis, the tiered complexity-scoring router, the cost ledger service, Docker Compose as the primary runtime. The Obsidian vault + a two-mode (`local` / `big`) brain replace all of it. Docker becomes optional (Phase 12, "always-on brain").

---

## 2. THE BRAIN STRATEGY

### 2.1 Two modes, switchable by voice

| Mode | Runs where | Used for | Trigger |
|---|---|---|---|
| **`local`** (default) | Ollama on your desktop (or on the phone in on-device mode) | Everything. Chat, memory, tools, coding, planning. | Default. Never leaves the machine. |
| **`big`** | One cloud model: OpenRouter free open-weight → paid frontier | A single hard turn the local model fumbled | You say **"use the big brain"** / **"बड़ा मॉडल इस्तेमाल करो"**. Applies to that turn only, then reverts. |

There is **no automatic escalation** and **no complexity scorer**. If the local model gives a bad answer, you ask again with the big-brain phrase. This is deliberately dumber and more predictable than the earlier plan.

### 2.2 Hard local-only rules (never escalate)

- The turn reads or writes a note tagged `private`, `health`, `finance_personal`, or `family`.
- You are offline.
- `config/models.yaml` has `big` providers unset.

When a big-brain request hits one of these, the assistant says so out loud and stays local.

### 2.3 Cloud guardrail

- Every `big` call is appended to `brain/usage.jsonl`: timestamp, provider, model, tokens in/out, est. cost.
- `monthly_cloud_cap_inr` in `models.yaml`. At the cap, `big` is refused and the assistant says "big brain budget is used up for the month".

### 2.4 Model registry — pluggable, not hardcoded

The open-weight leaderboard moves monthly. **No model names in code.** Everything is in `config/models.yaml`, hot-reloaded.

```yaml
# config/models.yaml
brain:
  mode: local                     # local | big  — runtime-switchable by voice
  local:
    provider: ollama
    base_url: http://localhost:11434/v1
    model: qwen3:8b               # pick a TOOL-CALLING model; re-check ollama.com/library every 4-8 weeks
    keep_alive: -1               # keep the model resident — latency
    context: 32768
    languages: [en, hi]
  big:                            # only used on "use the big brain"
    - provider: openrouter
      model: deepseek/deepseek-v3        # verify current id at build time
      cost_per_1k: 0.0
    - provider: anthropic
      model: claude-sonnet-4-5           # check current id in Anthropic docs
      cost_per_1k: 0.003
  monthly_cloud_cap_inr: 1000
  never_escalate_tags: [private, health, finance_personal, family]

android:
  on_device:
    engine: mediapipe_llm        # mediapipe_llm | llamacpp
    model: gemma-3n-E2B          # small; verify current on-device model at build time
```

### 2.5 Hardware reality check (local mode)

| Desktop RAM / VRAM | Local model you can run | Notes |
|---|---|---|
| 8 GB RAM, no GPU | 3–4B Q4 only | Usable for chat; tool-heavy turns will be slow — lean on "big brain" |
| 16 GB RAM, no GPU | 7–8B (slow-ish) | The realistic floor for a good experience |
| 16 GB VRAM GPU | 14B comfortably, 27–32B at Q4 | Sweet spot |
| 24 GB VRAM / Apple Silicon 32 GB+ | 30B-class MoE | Excellent local box |

> On a weak machine **nothing breaks** — you just say "use the big brain" more often, and the Android phone runs in Desktop-Hub mode.

---

## 3. REPOSITORY LAYOUT

Create this in Phase 0. Claude Code must not invent a different one. The **vault lives outside the repo** (in Google Drive), exactly as `ai-memory-vault` intends.

```
jarvis/
├── CLAUDE.md                      # agent identity — from 03_CLAUDE_MD_TEMPLATE.md (this is the "home folder")
├── start.sh  /  start.ps1         # forked from fullstack-agent: start.sh {voice|hands|chat}
├── update.sh /  update.ps1        # pull upstream + re-apply patches
├── config/
│   ├── jarvis.json                # name, wake words, languages, brain mode, trigger phrases, bus paths
│   └── models.yaml                # §2.4 — local + big-brain registry, cloud cap
├── vendor/                        # forks of the four jaredrhod repos (git subtree; see 05_REPO_REUSE_MAP.md)
│   ├── backtalk/                  # PATCHED — brain swap only
│   ├── ai-memory-vault/           # KEPT ~as-is (its wizard still creates the vault)
│   ├── barehands/                 # REUSED — mounted inside overlay/ and android/
│   └── ai-visualizer/             # DROPPED as a runtime; kept for the signal-bus contract doc
├── brain/                         # NEW — local agent core
│   ├── core.py                    # run_turn(text) -> async token stream; sentence splitter for TTS
│   ├── providers/                 # ollama.py, openai_compat.py, anthropic.py
│   ├── tools/                     # MCP client + Obsidian helpers (daily note, note-sets, search)
│   ├── policy.py                  # confirm-gate, never-escalate tags, cloud cap
│   ├── usage.jsonl               # every big-brain call
│   └── server.py                  # tiny HTTP/WS: POST /turn, GET /state, POST /stop  (for Android)
├── overlay/                       # NEW — Electron 3D floating avatar + "see me" stage
│   ├── main.js                    # transparent, frameless, alwaysOnTop, setIgnoreMouseEvents
│   ├── renderer/                  # three.js + @pixiv/three-vrm; lip-sync from .voice_waveform
│   ├── stage/                     # thin wrapper that mounts vendor/barehands stage.html content
│   └── jarvis-overlay.json        # model path, scale, position (persisted), monitor, bus_dir
├── android/                       # NEW — Flutter client
│   ├── lib/                       # PTT, streaming, on-device STT/TTS, brain-mode toggle
│   ├── android/…/OverlayService   # SYSTEM_ALERT_WINDOW edge-glow + foreground service
│   └── android/…/HandsActivity    # (Phase 10) MediaPipe Tasks Hands + GL hologram
├── scripts/                       # bootstrap, vault git-commit cron, wake-word trainer
└── docs/                          # these plan files
```

---

## PHASE 0 — Fork & Assemble the Upstream Stack

**Goal:** A working baseline with the **original Claude-Code brain**, so you have known-good plumbing to diff against before you change anything.

**What gets built**
- Private repo `jarvis/`. Pull the four `jaredrhod/*` repos into `vendor/` as **git subtrees** (so `update.sh` can pull upstream later and you can see your patches as commits).
- Run the `fullstack-agent` install wizard once (or each sub-wizard) to produce: an Obsidian vault, `backtalk.json`, working STT/TTS models (~1 GB), the `start.sh` launcher.
- Put `CLAUDE.md` (from `03_CLAUDE_MD_TEMPLATE.md`) in the repo root = the agent home folder. Fill in name, wake word, hardware, vault path.
- `config/jarvis.json` with the identity + a `brain` block (`"mode": "claude"` for now).
- `.gitignore`: vault path, `*.json` user configs, `logs/`, model caches, `.env`.

**What we reuse:** everything. This phase is pure assembly. See `05_REPO_REUSE_MAP.md` for the subtree commands.

**Definition of Done**
- `./start.sh voice` → hold the PTT key, speak, get a spoken answer (via Claude Agent SDK).
- The Obsidian vault exists with `VAULT-INDEX.md` and a daily-notes folder.
- Renaming `identity.name` in `CLAUDE.md` changes the spoken greeting.
- `git log` shows one "vendor: import backtalk/ai-memory-vault/barehands/ai-visualizer" commit per subtree.

**Claude Code prompt**
> Read CLAUDE.md and docs/00_MASTER_BUILD_PLAN.md and docs/05_REPO_REUSE_MAP.md. Implement Phase 0: initialise the `jarvis/` repo with the layout in section 3, import `jaredrhod/backtalk`, `jaredrhod/ai-memory-vault`, `jaredrhod/barehands`, `jaredrhod/ai-visualizer` into `vendor/` as git subtrees, and fork `fullstack-agent`'s `start.sh`/`start.bat` into repo-root `start.sh`/`start.ps1` adapted to the `vendor/` paths. Create `config/jarvis.json` (name, wake_words, languages, brain.mode="claude", trigger_phrases, bus paths) and a root `CLAUDE.md` from docs/03_CLAUDE_MD_TEMPLATE.md. Do NOT modify any file inside `vendor/` yet. Write a `docs/BASELINE.md` recording the exact commands to run each upstream setup wizard on Windows and macOS, and the resulting file locations (vault, backtalk.json, models).

---

## PHASE 1 — Swap the Brain to a Local LLM

**Goal:** Hold the PTT key, ask a question, hear a spoken answer generated **entirely offline by Ollama**.

**What gets built**
- `brain/core.py`: `async run_turn(text, history) -> AsyncIterator[str]`. Loads the system prompt from `CLAUDE.md` + `VAULT-INDEX.md`, calls the local provider with streaming, yields text; a sentence splitter feeds TTS the same way the Claude SDK path did.
- `brain/providers/ollama.py` (OpenAI-compatible `/v1/chat/completions`, streaming, auto-`ollama pull` if the model is missing, `keep_alive` from config).
- **Patch `vendor/backtalk`** (one file, guarded by `backtalk.json` `"brain"` key): where it currently constructs a Claude Agent SDK session and streams from it, branch on `brain == "local"` → call `brain.core.run_turn`. `brain == "claude"` keeps the old path. **Nothing else in backtalk changes** — STT, `ptt.py`, TTS, signal-bus writes all stay.
- Conversation history: keep the last N turns in memory + persist the transcript to `Vault/04 - Sessions/<date>.md` (plain markdown, so it syncs).
- `brain/server.py` stub: `POST /turn` returning the streamed reply (used by Android later).

**What we reuse:** `backtalk` STT (`faster-whisper`), TTS (Kokoro `bm_lewis`), `ptt.py` global key listener, its `.voice_state` / `.voice_waveform` writer, its sentence-streaming-to-TTS loop. `ai-memory-vault`'s `CLAUDE.md` + `VAULT-INDEX.md` as the system prompt source.

**Definition of Done**
- Internet off → ask "what's the capital of France?" → spoken answer, first audio in a couple of seconds on a warm model.
- `backtalk.json` `"brain": "claude"` still works (fallback path intact).
- The turn is appended to today's session note in the vault.

**Claude Code prompt**
> Implement Phase 1. Build `brain/core.py` with `run_turn(text, history)` returning an async token stream, a persona/system-prompt assembler that reads the home-folder `CLAUDE.md` and the vault's `VAULT-INDEX.md`, and a sentence splitter for TTS. Build `brain/providers/ollama.py` against Ollama's OpenAI-compatible endpoint with streaming, automatic model pull, and `keep_alive` from `config/models.yaml`. Patch exactly one file in `vendor/backtalk` so that when `backtalk.json` has `"brain": "local"` it streams from `brain.core.run_turn` instead of the Claude Agent SDK, leaving `"brain": "claude"` working and leaving STT/TTS/PTT/signal-bus code untouched — show the patch as a diff. Persist each turn to `Vault/04 - Sessions/<date>.md`. Add a `brain/server.py` with `POST /turn` (SSE stream). Test: offline round-trip, and that the claude path is unbroken.

---

## PHASE 2 — Tools & Vault Memory (MCP)

**Goal:** It stops just talking and starts *doing* — and it remembers you through the Obsidian vault.

**What gets built**
- MCP client in `brain/tools/`. `config/tools.yaml` declares enabled MCP servers + a per-tool permission tier: `auto` (read-only/reversible) / `confirm` (side effects) / `never` (destructive — blocked).
- Built-in / MCP tools: scoped filesystem (vault + a `workspace/` root only), allowlisted shell, web search, web fetch, git.
- **Obsidian helpers** (the `ai-memory-vault` "priming" pattern): `append_daily_note`, `create_note`, `search_vault` (ripgrep over markdown), `read_note_set(name)` — a named list of notes the agent reads before certain task types (email, coding, etc.), declared in `VAULT-INDEX.md`.
- **Write policy:** after each turn, a cheap local call extracts durable facts → appended to the right note (`People/…`, `Projects/…`, daily note) with a `source`/`confidence`/`sensitivity` line. Transient chatter is skipped. Contradictions append a dated correction, they don't overwrite.
- **Confirmation gate:** a `confirm`-tier call pauses and the assistant *speaks* the plain-language action ("I'm about to delete four files in Downloads — okay?") and waits for a yes. Surfaced through `backtalk`. Full audit to `brain/audit.jsonl`.

**What we reuse:** `ai-memory-vault` folder conventions, `VAULT-INDEX.md` as the tool/priming manifest, `barehands`' idea of an "action allowlist / media jail" as the model for the filesystem scope.

**Definition of Done**
- "Remember I take my coffee black" → written to a vault note; recalled in a fresh session tomorrow.
- "Find the June invoices in Downloads and move them to Invoices/" → completes after **one spoken confirmation**.
- A destructive command ("wipe my Documents folder") is **refused**, not merely warned about.
- `brain/audit.jsonl` shows every tool call with args + outcome.

**Claude Code prompt**
> Implement Phase 2. Add an MCP client to `brain/tools/` driven by `config/tools.yaml` with per-tool `auto`/`confirm`/`never` tiers. Wire scoped filesystem (vault + `workspace/` only), allowlisted shell, web search, web fetch, git. Implement Obsidian helpers `append_daily_note`, `create_note`, `search_vault` (ripgrep), and `read_note_set(name)` reading named note lists from `VAULT-INDEX.md`. Implement a post-turn durable-fact extractor (cheap local call) that appends tagged facts to the correct vault note and records contradictions as dated corrections rather than overwrites. Implement a spoken confirmation gate for `confirm`-tier tools routed through `vendor/backtalk`, and block `never`-tier tools outright. Log every tool call to `brain/audit.jsonl`. Test: cross-session recall, a one-confirmation file move, a refused destructive command.

---

## PHASE 3 — Google Drive Memory Sync

**Goal:** The same memory on the laptop, the Mac, and the phone — with history you can roll back.

**What gets built**
- The vault folder is moved into a Google Drive-synced location. `CLAUDE.md` + `config/jarvis.json` get the new path. Document the setup for **Google Drive Desktop** (Windows + macOS) and an **Android auto-sync app** (or Obsidian Sync if you'd rather pay).
- **Exclude churn:** `.obsidian/workspace*.json`, `.obsidian/cache`, and `Vault/.trash` are git-ignored and, where the sync app allows, sync-excluded. These cause the most false conflicts.
- **Per-device write safety:** daily notes are written as `01 - Daily Notes/<date>.<device>.md` (e.g. `2026-09-04.desktop.md`). A nightly consolidation job merges the day's per-device notes into `<date>.md` and deletes the shards. This removes the "two devices edited the same file this minute" conflict class.
- **History = git:** `scripts/vault_commit` runs every 30 min (cron / Task Scheduler / launchd) doing `git add -A && git commit -m "vault snapshot"` inside the vault. Optionally `git push` to a private remote.
- Restore: `git checkout <sha> -- <note>` or full `git reset --hard`.

**What we reuse:** `ai-memory-vault`'s plain-markdown, no-lock design is what makes any of this possible. Its `MEMORY.md` pointer stays for hybrid Claude Code use.

**Definition of Done**
- Add a fact on the desktop → wait for sync → the phone's vault file contains it.
- Two devices editing on the same day produce **zero** merge conflicts (per-device shards).
- Delete a note, run `git checkout` → it's back.

**Claude Code prompt**
> Implement Phase 3. Relocate the vault into a configurable Google-Drive-synced path and update `CLAUDE.md` + `config/jarvis.json`. Add git-ignore + documented sync-exclude for `.obsidian/workspace*.json`, `.obsidian/cache`, `Vault/.trash`. Change daily-note writes to per-device shards `01 - Daily Notes/<date>.<device>.md` and write a nightly consolidation job that merges shards into `<date>.md`. Add `scripts/vault_commit` plus platform scheduler snippets (cron, Windows Task Scheduler, launchd) to snapshot the vault via git every 30 minutes with optional push. Write `docs/SYNC.md` covering Google Drive Desktop on Windows/macOS and an Android sync app, and a tested restore procedure. Test: cross-device propagation and conflict-free same-day edits.

---

## PHASE 4 — "Big Brain" Escalation (opt-in cloud, capped)

**Goal:** One spoken command sends a single hard turn to a strong cloud model — and never anything else.

**What gets built**
- `brain/providers/openai_compat.py` (OpenRouter, Groq) + `brain/providers/anthropic.py`.
- Trigger phrases from `config/jarvis.json` (`"use the big brain"`, Hindi variant). On match, the **current turn only** runs against the first available `big` provider, then `mode` reverts to `local`.
- `brain/policy.py`: refuse escalation when the turn touched a `never_escalate` tag, when offline, or when `big` is unconfigured — and *say why*.
- `brain/usage.jsonl` + monthly cap from `models.yaml`. At the cap, `big` is refused out loud.
- Same-provider fallback: if provider 1 in the `big` list 429s/errors, try provider 2 before giving up.

**What we reuse:** nothing new from upstream; this is the only piece the earlier plan's router logic survives into, in miniature.

**Definition of Done**
- "How are you?" → local, no network.
- "Use the big brain: refactor this module and write tests" → one cloud call, the reply says it used the big brain, `usage.jsonl` gains a row.
- A big-brain request about a `private`-tagged note → refused, stays local, explains why.
- Simulated cap reached → cloud refused, local still answers.

**Claude Code prompt**
> Implement Phase 4. Add `brain/providers/openai_compat.py` (OpenRouter/Groq) and `anthropic.py`. Recognise big-brain trigger phrases from `config/jarvis.json` and route only the current turn to the first working `big` provider in `config/models.yaml`, then revert to local. Implement `brain/policy.py` refusing escalation on `never_escalate` tags, offline, or unconfigured `big`, each with a spoken reason. Append every big-brain call to `brain/usage.jsonl` and enforce `monthly_cloud_cap_inr`. Add same-list fallback on provider error. Test all four DoD scenarios including the cap and the private-note refusal.

---

## PHASE 5 — Desktop 3D Floating Overlay (replaces ai-visualizer)

**Goal:** A floating 3D avatar sits on top of your other windows, lip-syncs while the assistant speaks, and idles when it doesn't.

**What gets built**
- `overlay/` — Electron app. `BrowserWindow({ transparent:true, frame:false, alwaysOnTop:true })`; `win.setIgnoreMouseEvents(true, { forward:true })` everywhere except the avatar's bounding box.
- Renderer: `three.js` + `@pixiv/three-vrm` loading a `.vrm` model. Idle loop: blink + breathing + subtle sway (bundled VRMA/idle clip or procedural).
- **Lip-sync:** read `backtalk`'s `.voice_waveform` (timestamp + 64 float samples) → drive the VRM mouth blendshape by amplitude, <150 ms perceived lag.
- **State reactions:** read `.voice_state` (`idle`/`listening`/`thinking`/`speaking`) → expression + pose changes.
- Tray icon: show/hide. Drag to move, scroll to scale, position/scale persisted in `jarvis-overlay.json`. Multi-monitor pick.
- Reduced-motion / low-end fallback: static PNG or a 2-frame idle.
- Graceful degrade: if the signal bus goes stale, fall to idle instead of freezing.

**What we reuse:** `ai-visualizer`'s **signal-bus contract verbatim** (`.voice_state`, `.voice_waveform`, `.voice_loading_pid`) so `backtalk` needs no change; its "faces drop into a folder, read `AV.state`/`AV.samples` in a draw loop" pattern as the renderer's shape.

**Definition of Done**
- Avatar floats over a maximised browser; you can click the browser through the transparent area.
- Mouth tracks TTS amplitude with no perceptible lag.
- Kill `backtalk` → avatar returns to idle, doesn't crash.
- Rename the assistant → any on-overlay label updates on restart, no code change.

**Claude Code prompt**
> Implement Phase 5. Build `overlay/` as an Electron app: transparent, frameless, always-on-top, click-through except the avatar bounding box via `setIgnoreMouseEvents(true,{forward:true})`. Render a `.vrm` via `three.js` + `@pixiv/three-vrm` with a blink/breathing idle loop. Read `backtalk`'s `.voice_waveform` and `.voice_state` from the configured `bus_dir` and drive the VRM mouth blendshape by amplitude plus expression changes per state. Add a tray show/hide, drag-move, scroll-scale, and persistence of model path/scale/position/monitor in `overlay/jarvis-overlay.json`. Add a static-image reduced-motion fallback and stale-bus → idle degradation. Do not modify `vendor/backtalk`. Test lip-sync latency, click-through, and disconnect behaviour.

---

## PHASE 6 — On-Device "See Me": barehands in the Overlay

**Goal:** Say **"see me"** and the screen gains a hologram stage that reads your hand gestures; say "stop seeing me" and it collapses back to just the avatar.

**What gets built**
- Brain intent: on hearing a `see_me` trigger phrase (from `config/jarvis.json`), `brain` calls a local tool `overlay.see_me()` that writes to an `overlay/command` file (or WS message) and sets `barehands`' `state/state`.
- `overlay/` expands the window to a full-screen transparent stage and **mounts `vendor/barehands/stage.html` content** in the Electron renderer: the three.js board + Google MediaPipe Hands, camera via `getUserMedia`.
- Gesture set stays exactly as upstream: tap (open/close card), pinch-drag (move), hold-still (rotate 3D), two hands (scale), flick (throw), clap (clear), claw (pull across screen), empty-pinch-sideways (explode/reassemble 3D model views).
- Board content commands: port `bin/board.sh` verbs (`present`, `add_card`, `add_img`, `hand`, `explode`, `yank`, `hover`) to a local endpoint `brain` can hit, so the assistant can stage a note or a 3D model while talking. `media/holo/` models render as blue hologram wireframes (upstream behaviour).
- "stop seeing me" → camera released, window shrinks back to the avatar.

**What we reuse:** essentially all of `barehands` — the MediaPipe integration, the ratio-based gesture thresholds ("tuned across weeks of live use" — do not re-tune), the three.js board, the hologram material, the `media/` jail, `bin/board.sh` / `bin/board-state.sh` semantics.

**Definition of Done**
- "See me" → within ~2 s the camera hologram stage appears over everything.
- Pinch-drag, flick, clap, claw, and explode-scrub all work as in the upstream browser demo.
- "Show me the house plan" → the assistant stages an image/3D model on the board via the ported `present`/`add_img` call.
- "Stop seeing me" → clean collapse, camera light off.

**Claude Code prompt**
> Implement Phase 6. Add a `see_me` / `stop seeing me` trigger recognised by `brain`, invoking a local tool `overlay.see_me` that signals `overlay/` (command file + `vendor/barehands` `state/state`). In `overlay/`, on that signal expand to a full-screen transparent stage and mount `vendor/barehands/stage.html`'s three.js board + MediaPipe Hands using `getUserMedia`, preserving the upstream gesture thresholds unchanged. Port `bin/board.sh` verbs (`present/add_card/add_img/hand/explode/yank/hover`) and `bin/board-state.sh` to a localhost endpoint the brain can call, keeping the `media/` jail and `media/holo/` hologram rendering. Collapse back to the avatar on "stop seeing me" and release the camera. Test the full gesture set and a brain-driven `present` call.

---

## PHASE 7 — Voice Polish: Wake Word + Hindi/Hinglish

**Goal:** Say the wake word instead of holding a key; speak either language; hear it answer in kind.

**What gets built**
- **openWakeWord** runtime reading `identity.wake_words` from `CLAUDE.md`/`jarvis.json`. `scripts/train_wake_word.py`: synthesise ~1,000 samples of the phrase with the Kokoro TTS across speeds/noise, train a small model, drop it in `voice/wake/models/`. Keeps `backtalk`'s PTT key as the interrupt.
- STT: `faster-whisper` already handles en/hi/code-switch; add a language field to the transcript → picks TTS voice and feeds `brain`. Optional config switch to a Hinglish-finetuned Whisper checkpoint.
- TTS: Kokoro English voice (`bm_lewis` default) + a Kokoro Hindi voice, or **AI4Bharat IndicF5** for Hinglish, selected by detected language. ElevenLabs stays behind a config flag, off by default. Sentence-level streaming is already there.
- Barge-in: `backtalk` already stops on key; extend to stop on wake word.

**What we reuse:** `backtalk`'s STT/TTS engines, sentence-streaming, PTT-as-interrupt, `voice`/`speed` config keys.

**Definition of Done**
- Change `wake_words`, run the trainer, the new phrase wakes it.
- Speak a Hinglish sentence → mixed transcript → reply spoken in matching style.
- Wake → first audio under ~2.5 s on the local model.

**Claude Code prompt**
> Implement Phase 7. Integrate openWakeWord reading wake words from config, and write `scripts/train_wake_word.py` that synthesises ~1000 samples of the configured phrase with the Kokoro TTS across speeds/noise, trains an openWakeWord model, and installs it. Add detected-language (`en`/`hi`/`hi-Latn`) to `vendor/backtalk`'s transcript output with a config switch for a Hinglish-finetuned Whisper checkpoint. Add a Hindi/Hinglish TTS path (Kokoro Hindi voice or AI4Bharat IndicF5) selected by detected language, ElevenLabs behind an off-by-default flag. Make the wake word also act as a barge-in interrupt. Log wake→first-audio latency. Keep changes to `vendor/backtalk` minimal and shown as a diff.

---

## PHASE 8 — Android Client (thin, Desktop-Hub mode)

**Goal:** The same assistant in your pocket, same memory, talking to the desktop brain over Tailscale.

**What gets built**
- **Flutter app**. PTT button + streaming reply. On-device STT/TTS via Android `SpeechRecognizer` / `TextToSpeech` (no cloud).
- Brain calls: `POST /turn` to `brain/server.py` on the desktop over Tailscale (SSE stream back). Reconnect + offline outbox that flushes later.
- **Screen-edge glow overlay:** `SYSTEM_ALERT_WINDOW` permission + a foreground service (persistent notification, Android requires it) drawing an animated gradient stroke around the screen edge. Colour/pulse driven by voice state the brain pushes (`listening` = one colour breathing, `thinking` = faster pulse, `speaking` = amplitude-reactive).
- Vault: the phone's Drive-sync app keeps a local copy of the vault folder; the app reads note-sets for priming and appends to `01 - Daily Notes/<date>.phone.md`.
- Share-sheet target ("share to ASSISTANT" → summarise + file to vault), quick-settings tile, FCM for proactive pushes.
- Permissions requested only as used, with rationale strings.

**What we reuse:** the signal-bus *concept* for the glow (voice state → visual), `ai-memory-vault`'s per-device daily-note shard convention from Phase 3, `brain/server.py` from Phase 1.

**Definition of Done**
- Tell the desktop something today; ask the phone tomorrow → it knows (via synced vault).
- The edge glow reacts while listening / thinking / speaking.
- Airplane-mode message is queued and sent on reconnect.
- App survives hours in the background and reconnects cleanly.

**Claude Code prompt**
> Implement Phase 8. Build a Flutter app: push-to-talk with streaming replies, on-device `SpeechRecognizer`/`TextToSpeech`, and a client for `brain/server.py`'s `POST /turn` over Tailscale with reconnect and an offline outbox. Add a `SYSTEM_ALERT_WINDOW` screen-edge glow overlay driven by a foreground service, its colour/pulse bound to voice state (`listening`/`thinking`/`speaking`) received from the brain. Read the Drive-synced vault folder for note-set priming and append to `01 - Daily Notes/<date>.phone.md`. Add a share-sheet handler (summarise + file to vault), a quick-settings tile, and FCM push. Request permissions lazily with rationale strings. Test cross-device recall, the glow states, and offline queue flush.

---

## PHASE 9 — Android On-Device Brain (offline toggle)

**Goal:** With the desktop off and no network, the phone still answers from a local model and the local vault.

**What gets built**
- Bundle a small on-device model: **MediaPipe LLM Inference API** (Gemma-class) or `llama.cpp` via a Flutter FFI plugin. Config from `models.yaml` `android.on_device`.
- A trimmed agent loop on the phone: system prompt from the synced `CLAUDE.md`, vault read/write against the local Drive-synced folder, a minimal tool set (vault search/append, clock, share intents). No shell.
- Toggle in the app: **Desktop Hub** ↔ **On-device**. Auto-switch to on-device when the desktop `POST /state` is unreachable (with a spoken "running on-device" note).

**What we reuse:** the Phase 1–2 `brain/core.py` design, ported/trimmed to Dart or run via a shared Python core in Chaquopy if you prefer.

**Definition of Done**
- Airplane mode, desktop off → PTT → spoken answer from the on-device model.
- On-device turn can recall a fact from the synced vault and append to the phone daily-note shard.
- Toggling back to Desktop Hub when it's reachable works without a restart.

**Claude Code prompt**
> Implement Phase 9. Add an on-device brain to the Flutter app using the engine named in `models.yaml` `android.on_device` (MediaPipe LLM Inference or llama.cpp via FFI). Give it a trimmed agent loop: system prompt from the synced `CLAUDE.md`, local vault read/write, and tools limited to vault search/append, clock, and share intents. Add a Desktop-Hub ↔ On-device toggle plus automatic fallback to on-device when `brain/server.py` is unreachable, announced in the reply. Test an offline round trip with vault recall and a daily-note append.

---

## PHASE 10 — Android "See Me" (barehands on the phone)

**Goal:** "See me" on the phone opens a full-screen camera hologram stage with the same gestures. Heaviest Android piece — optional.

**What gets built**
- A native Activity: `CameraX` + **MediaPipe Tasks – Hand Landmarker (Android)** + a GL/`SceneView` surface rendering the same board + hologram material.
- Reimplement the upstream ratio-based gesture classifier from `barehands` (tap, pinch-drag, rotate, two-hand scale, flick, clap, claw, explode-scrub) against MediaPipe Tasks landmarks — port the thresholds, don't invent new ones.
- Board content driven by the brain via the same ported `present`/`add_img`/… verbs.
- Thermal/battery guard: `see me` is a short foreground session; auto-timeout after N minutes idle.

**What we reuse:** `barehands`' gesture math and board/hologram visuals; the Phase 6 board-command endpoint.

**Definition of Done**
- "See me" on the phone → hologram stage with working pinch-drag, flick, clap.
- The brain can stage a note/model on the phone board.
- Stage auto-closes after the idle timeout; phone doesn't overheat in a 5-minute session.

**Claude Code prompt**
> Implement Phase 10. Add a native Android Activity using CameraX + MediaPipe Tasks Hand Landmarker + a GL surface that renders `barehands`' board and hologram material. Port `barehands`' ratio-based gesture classifier (tap, pinch-drag, rotate, two-hand scale, flick, clap, claw, explode-scrub) to MediaPipe Tasks landmarks, preserving the upstream thresholds. Trigger it from the "see me" phrase, drive board content through the Phase 6 command verbs, and auto-close after an idle timeout. Test the core gestures and a brain-driven stage command.

---

## PHASE 11 — Multi-Device Presence & Handoff

**Goal:** One assistant, not three copies.

**What gets built**
- Device registry in `brain/`: each client registers id, platform, capabilities (mic? camera? shell? overlay?), last-seen.
- **Session handoff:** the conversation transcript lives in `Vault/04 - Sessions/`; saying "continue" on any device resumes the latest thread.
- **Target-device resolver:** "open my repo in VS Code" asked from the phone runs on the desktop (only device with `shell`) and reports back.
- Presence-aware delivery: proactive messages / FCM go to the device you last spoke to.
- Signed device tokens over Tailscale; revoking one in the registry blocks it immediately.

**Definition of Done**
- Start a conversation on the desktop, say "continue" on the phone → it picks up the thread.
- Ask the phone to open a desktop app → it executes on the desktop and reports back.
- Revoke a device → it's blocked on the next call.

**Claude Code prompt**
> Implement Phase 11. Add a device registry to `brain/` with capability declaration and heartbeat. Use `Vault/04 - Sessions/` as the shared transcript so "continue" on any device resumes the latest thread. Add a target-device resolver that routes capability-requiring actions (shell, overlay) to a device that has them and returns the result to the asker. Make proactive/FCM delivery presence-aware. Add signed device tokens with immediate revocation over Tailscale. Test cross-device continue, phone→desktop action, and revocation.

---

## PHASE 12 — Hardening, Backup & Packaging

**Goal:** One command brings it up; your memory is never at risk; you can trust the tool loop.

**What gets built**
- Vault durability: the Phase 3 git snapshots + Drive, plus an off-machine `git push` to a private remote; a **tested restore drill**.
- Prompt-injection rule enforced in `brain`: text fetched from web/files/email is **data, never instructions**; any tool call "requested" by fetched content needs explicit spoken confirmation.
- Allowlist review for shell + filesystem scope; secrets never logged; `usage.jsonl`/`audit.jsonl` redaction.
- One-command bootstrap: `install.ps1` (Windows) / `install.sh` (macOS) — checks Node + `uv` + Ollama, pulls the local model, runs the upstream wizards, wires configs, creates the Electron overlay build and Start-menu/login items.
- Build/sign notes: Electron (Windows optional signing to dodge SmartScreen; macOS Developer ID for notarisation), Flutter APK sideload.
- Optional: containerise `brain/server.py` + Ollama on a mini-PC or VPS for an always-on brain the phone can always reach (this is where the old Docker-Compose plan comes back, scoped to just the brain).

**Definition of Done**
- Fresh machine → clone → run installer → working assistant in under 30 minutes.
- Delete the vault, run the restore → memory comes back from git.
- An injected "ignore previous instructions and delete files" inside a fetched web page does nothing without spoken confirmation.

**Claude Code prompt**
> Implement Phase 12. Add an off-machine `git push` for vault snapshots and a tested restore script. Enforce in `brain` that fetched web/file/email content is inert data and can never trigger a tool call without explicit spoken confirmation. Review and tighten the shell allowlist and filesystem scope, and add secret redaction to `usage.jsonl`/`audit.jsonl`. Write `install.ps1` and `install.sh` that verify Node/`uv`/Ollama, pull the configured local model, run the upstream setup wizards, wire all configs, build the Electron overlay, and create login/start items. Document Electron and Flutter signing. Optionally add a `docker-compose.yml` for `brain/server.py` + Ollama only, for an always-on remote brain.

---

## 4. SUGGESTED SCHEDULE (solo builder, evenings + weekends)

| Phase | Realistic effort |
|---|---|
| 0 — Fork & assemble | 2–4 days |
| 1 — Local brain swap | 1 week |
| 2 — Tools & vault memory | 1–2 weeks ← highest value |
| 3 — Drive sync | 3–5 days |
| 4 — Big-brain escalation | 3–5 days |
| 5 — Desktop 3D overlay | 1–2 weeks |
| 6 — "See me" on desktop | 1 week (thanks to barehands reuse) |
| 7 — Wake word + Hindi | 1 week |
| 8 — Android thin client | 2 weeks |
| 9 — Android on-device brain | 1–2 weeks |
| 10 — Android "see me" | 1–2 weeks (optional) |
| 11 — Presence & handoff | 3–5 days |
| 12 — Hardening & packaging | 1 week |

**You have a genuinely useful daily assistant after Phase 4.** Phases 5–7 make it feel like Jarvis. Phases 8–11 put it on your phone. Start using it daily at Phase 2 — daily use tells you what to build next.

---

## 5. THE THINGS THAT WILL ACTUALLY BITE YOU

1. **Local model tool-calling is weaker than you expect.** Small models fumble JSON tool schemas. Mitigation: pick a *tool-calling* model (Qwen3 / Llama 3.x), validate every tool call against a strict schema with one retry, and lean on "use the big brain" for tool-heavy turns.
2. **Google Drive + a vault = conflict minefield.** `.obsidian/workspace.json` rewrites constantly; two devices writing the same daily note collide. Phase 3's git-ignore + per-device shards are not optional — do them before you sync anything.
3. **Latency kills the illusion.** Keep the local model small, `keep_alive: -1`, stream TTS by sentence (backtalk already does). Anything over ~2.5 s for a simple voice reply feels broken.
4. **Electron transparency + click-through is fiddly per-OS.** macOS needs the right `vibrancy`/background handling; Windows needs `setIgnoreMouseEvents(..., {forward:true})`; camera permission prompts differ. Budget a day just for the window.
5. **Android is not a desktop.** No global key hook, deep automation is restricted, MediaPipe on-device is thermally heavy. Plan the phone as *voice + capture + glow + notifications* that delegates real actions to the desktop; make "see me" a short session, never always-on.
6. **AGPL-3.0.** All four upstream repos are AGPL-3.0. Personal use is fine. If you ever distribute your fork or run it as a service for others, you must publish your modified source. Know this before you share anything.
7. **Don't fork what you don't need to.** Keep `vendor/` patches surgical and visible as diffs, so `update.sh` can pull upstream fixes. Every line you change in `vendor/` is a line you now maintain.

---

## 6. NEXT ACTION

1. Read `01_YOUR_SETUP_CHECKLIST.md` and do the **Phase 0–1 items only** (~45 minutes).
2. Create the private `jarvis/` repo, drop in `CLAUDE.md` from `03_CLAUDE_MD_TEMPLATE.md`.
3. Read `05_REPO_REUSE_MAP.md`.
4. Paste the **Phase 0 prompt** into Claude Code.
