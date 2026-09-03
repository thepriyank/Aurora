# YOUR SETUP CHECKLIST — Things Only You Can Do

Everything here needs a human with a browser, a card, or a phone. Claude Code cannot do any of it.
Work through it **phase by phase** — don't sign up for everything on day one.

**How to use:** as you get each key, paste it into your local `.env` (repo root). Never commit `.env`.

---

## LEGEND

| Tag | Meaning |
|---|---|
| 🔴 | Required — build is blocked without it |
| 🟡 | Recommended — makes life much easier |
| 🟢 | Optional — nice to have |
| 💳 | Costs money (or has paid tiers) |

---

## PART A — BEFORE PHASE 0 (do these first, ~45 min)

### A1. 🔴 Development machine check
Record these — the plan's model choices depend on them:
- [ ] OS + version: ____________
- [ ] CPU: ____________
- [ ] RAM: ______ GB
- [ ] GPU + VRAM: ______ GB (or "Apple Silicon, ___ GB unified")
- [ ] Free disk space: ______ GB (**want 150 GB+**; local models are 5–30 GB, plus Node/Electron/Flutter toolchains)

> Comfortable floor: 16 GB RAM. Sweet spot: 32 GB RAM + 16 GB VRAM GPU, or a 32 GB+ Apple Silicon Mac. On a weaker box you lean on "use the big brain" more often — nothing breaks.

### A2. 🔴 Ollama (the local brain)
- [ ] Install from https://ollama.com/download (**native on the host**, not in Docker)
- [ ] Pull a **tool-calling** model to confirm it works: `ollama run qwen3:8b` (or the current best small tool-calling model — check https://ollama.com/library)
- [ ] Note: set `OLLAMA_KEEP_ALIVE=-1` so the model stays resident (latency)

### A3. 🔴 Claude Code
- [ ] Set it up per https://docs.claude.com/en/docs/claude-code/overview
- [ ] Requires a Claude subscription or API credits 💳 (the $20 Pro plan is enough — it's what the upstream stack targets)
- [ ] Verify it runs inside your `jarvis/` folder before Phase 0
- [ ] This also gives you the `brain: "claude"` fallback path for bisecting bugs

### A4. 🔴 GitHub account + the upstream repos
- [ ] Account at https://github.com; create a **private** repo `jarvis`
- [ ] Personal Access Token (Settings → Developer settings → Tokens) → `GITHUB_TOKEN`
- [ ] Git installed locally; SSH keys set up
- [ ] Skim the four upstream READMEs so you know what you're forking:
  - https://github.com/jaredrhod/fullstack-agent
  - https://github.com/jaredrhod/backtalk
  - https://github.com/jaredrhod/ai-memory-vault
  - https://github.com/jaredrhod/barehands
  - (https://github.com/jaredrhod/ai-visualizer — being dropped, skim only)
- [ ] **License note:** all four are **AGPL-3.0**. Fine for personal use. If you ever distribute your fork or run it as a service for others, you must publish your modified source.

### A5. 🔴 Dev environment basics
- [ ] Python 3.12+
- [ ] `uv` (fast Python package manager) — https://github.com/astral-sh/uv  *(the upstream repos use it)*
- [ ] Node.js LTS + npm — https://nodejs.org  *(for the Electron `overlay/`)*
- [ ] `ripgrep` (`rg`) — used for vault search
- [ ] VS Code or your editor

### A6. 🔴 System audio libraries (backtalk deps)
- [ ] **espeak-ng** — Kokoro TTS phonemisation. Win: installer from the espeak-ng releases; Mac: `brew install espeak-ng`
- [ ] **ffmpeg** — needed if you later enable ElevenLabs. Win: `winget install ffmpeg`; Mac: `brew install ffmpeg`
- [ ] macOS only: grant **Input Monitoring** + **Microphone** to your terminal / the backtalk app (System Settings → Privacy)

### A7. 🔴 A decent microphone
- [ ] A cheap USB mic or a good headset beats a laptop mic dramatically. This saves hours of debugging "bad transcription" that was actually bad audio.

---

## PART B — MEMORY: OBSIDIAN + GOOGLE DRIVE (Phase 3)

### B1. 🔴 Obsidian on every device
- [ ] Desktop app on Windows **and** macOS — https://obsidian.md
- [ ] Obsidian on Android (Play Store)
- [ ] Do **not** open the same vault from two devices at the same second during setup

### B2. 🔴 Google Drive sync
- [ ] Google account
- [ ] **Google Drive for desktop** on Windows + macOS — https://www.google.com/drive/download/
- [ ] Decide the vault location inside the synced Drive folder, e.g. `…/My Drive/Vault`
- [ ] **Android sync** — pick one:
  - [ ] 🟡 A folder auto-sync app (e.g. "Autosync for Google Drive" / "DriveSync") pointed at the vault folder ↔ a local folder Obsidian opens
  - [ ] 🟢 💳 Obsidian Sync ($4–8/mo) — simplest, most reliable, skips Drive entirely on mobile
- [ ] Note for the plan: Phase 3 git-ignores `.obsidian/workspace*.json`, `.obsidian/cache`, `Vault/.trash` and switches daily notes to per-device filenames to avoid conflicts

### B3. 🟡 Vault history via git
- [ ] Optionally a second private repo (e.g. `jarvis-vault`) as the push target for `scripts/vault_commit` snapshots — off-machine history/restore

---

## PART C — THE BODY (Phases 5–6, 10)

### C1. 🔴 A `.vrm` avatar model (desktop 3D overlay)
- [ ] Get one of:
  - [ ] A free model from **VRoid Hub** — https://hub.vroid.com (check each model's license for personal use)
  - [ ] Make your own in **VRoid Studio** (free) — https://vroid.com/en/studio
- [ ] Drop it at `overlay/models/<name>.vrm`

### C2. 🟢 An idle animation clip
- [ ] Optional: a Mixamo idle (https://www.mixamo.com, free with an Adobe account) or a VRMA idle clip. Procedural blink/breath is a fine v1 without this.

### C3. Hand tracking — no account
- [ ] **Google MediaPipe** loads from a CDN (desktop) / ships as an Android Tasks bundle. Nothing to sign up for.
- [ ] 🔴 A webcam (built-in laptop cam is fine for "see me")

---

## PART D — MODEL PROVIDERS (Phase 4, "big brain" only)

You only need these for the opt-in "use the big brain" command. Skip until Phase 4.

### D1. 🟡 Free / cheap open-weight API (first choice for `big`)
| Provider | URL | Env var |
|---|---|---|
| **OpenRouter** 🟡 | https://openrouter.ai | `OPENROUTER_API_KEY` |
| **Groq** 🟢 | https://console.groq.com | `GROQ_API_KEY` |

- [ ] OpenRouter account + key (add ~$5 credit; unlocks better rate limits even for free models)

### D2. 💳 One paid frontier key (last-resort `big`)
| Provider | URL | Env var |
|---|---|---|
| **Anthropic** 🟡 | https://console.anthropic.com | `ANTHROPIC_API_KEY` |
| OpenAI 🟢 | https://platform.openai.com | `OPENAI_API_KEY` |
| Google AI Studio 🟢 | https://aistudio.google.com | `GOOGLE_API_KEY` |

- [ ] Create **one** key
- [ ] **Set a hard spend limit in the provider's billing console before the first call.**
- [ ] Also set `monthly_cloud_cap_inr` in `config/models.yaml`

### D3. 🟡 Hugging Face
- [ ] Account + read token → `HF_TOKEN`
- [ ] Needed for: `faster-whisper` model downloads, Kokoro voices, a Hinglish Whisper checkpoint, AI4Bharat IndicF5 (Hindi/Hinglish TTS — accept model terms at https://huggingface.co/ai4bharat)

---

## PART E — TOOLS (Phase 2, as needed)

### E1. Web search — pick one
- [ ] 🟡 **Brave Search API** — https://brave.com/search/api — ~2,000 free queries/mo → `BRAVE_API_KEY`
- [ ] 🟢 **Tavily** — https://tavily.com → `TAVILY_API_KEY`
- [ ] 🟢 **SearXNG** self-hosted — no key

### E2. 🟢 Google Calendar / Gmail (via an MCP server)
- [ ] Google Cloud Console → new project → enable Calendar API + Gmail API
- [ ] OAuth consent screen: External → Testing (add yourself as a test user)
- [ ] Create OAuth 2.0 **Desktop** credentials → download `credentials.json` → `secrets/credentials.json`
- [ ] Note: Testing-mode tokens expire every 7 days

### E3. 🟢 Other integrations (only if you'll use them)
- [ ] Notion / Todoist / Linear / Home Assistant — API tokens from account settings

---

## PART F — VOICE POLISH (Phase 7)

- [ ] 🟢 **Picovoice** — https://console.picovoice.ai — free personal tier → `PICOVOICE_ACCESS_KEY`. Only if you choose Porcupine over openWakeWord (openWakeWord needs no account).
- [ ] 🟢 **ElevenLabs** 💳 — https://elevenlabs.io — only for a premium voice. Off by default. `ELEVENLABS_API_KEY`
- [ ] 🟢 AI4Bharat IndicF5 model terms accepted (D3) for Hinglish TTS

---

## PART G — ANDROID (Phases 8–10)

### G1. 🔴 Tailscale
- [ ] Sign up at https://tailscale.com (free plan covers 100 devices)
- [ ] Install on Windows desktop, Mac, Android phone
- [ ] Note the desktop's Tailscale IP (`100.x.x.x`) → `TAILSCALE_HUB_IP`
- [ ] ACLs so only your devices reach the brain's port

### G2. 🔴 Flutter toolchain
- [ ] Flutter SDK — https://docs.flutter.dev/get-started/install
- [ ] Android Studio + Android SDK + platform tools
- [ ] Phone: enable **Developer options + USB debugging**
- [ ] Phone: allow **install from unknown sources** (sideload; no Play Store account needed)
- [ ] Phone: you'll grant **Display over other apps** (edge-glow) and **Camera** ("see me") at runtime

### G3. 🟡 Firebase (proactive push, Phase 8+)
- [ ] https://console.firebase.google.com → project → add Android app → `google-services.json`
- [ ] Service account JSON for the brain → `FCM_SERVICE_ACCOUNT`

### G4. 🟢 On-device model (Phase 9)
- [ ] Nothing to buy. Note the current small on-device model (MediaPipe LLM Inference / Gemma-class, or a `llama.cpp` GGUF) to put in `config/models.yaml` `android.on_device`

---

## PART H — `.env` TEMPLATE

Create `.env` in the repo root (in `.gitignore`):

```bash
# ---- Core ----
ASSISTANT_ENV=local
GITHUB_TOKEN=

# ---- Local inference ----
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_KEEP_ALIVE=-1

# ---- Memory / sync ----
VAULT_PATH=                 # e.g. /Users/you/Library/CloudStorage/GoogleDrive-.../My Drive/Vault
VAULT_GIT_REMOTE=           # optional private repo for vault snapshots

# ---- "Big brain" (Phase 4, opt-in only) ----
OPENROUTER_API_KEY=
GROQ_API_KEY=
ANTHROPIC_API_KEY=
MONTHLY_CLOUD_CAP_INR=1000

# ---- Models / voice ----
HF_TOKEN=
PICOVOICE_ACCESS_KEY=
ELEVENLABS_API_KEY=

# ---- Tools ----
BRAVE_API_KEY=
TAVILY_API_KEY=
GOOGLE_OAUTH_CREDENTIALS=./secrets/credentials.json

# ---- Networking / Android ----
TAILSCALE_HUB_IP=
FCM_SERVICE_ACCOUNT=./secrets/fcm.json
```

---

## PART I — ORDERED TODO

**Before Phase 0 (~45 min)**
1. [ ] Record hardware specs (A1)
2. [ ] Install Ollama + pull a tool-calling model (A2)
3. [ ] Claude Code working in the `jarvis/` folder (A3)
4. [ ] GitHub private repo + token; skim the 4 upstream READMEs; note the AGPL-3.0 terms (A4)
5. [ ] Python 3.12, `uv`, Node LTS, ripgrep (A5)
6. [ ] espeak-ng (+ ffmpeg), macOS mic/input-monitoring permissions (A6)
7. [ ] A real microphone plugged in (A7)

**Before Phase 3** — Obsidian on all 3 devices, Google Drive for desktop, an Android sync method (B1–B2)
**Before Phase 4** — OpenRouter key; one paid key **with a hard spend limit set**; HF token (D1–D3)
**Before Phase 5** — a `.vrm` avatar model (C1)
**Before Phase 7** — accept AI4Bharat terms; optionally Picovoice (F)
**Before Phase 8** — Tailscale on all devices, Flutter + Android Studio, phone in dev mode, Firebase project (G1–G3)

---

## PART J — THINGS TO DECIDE (not buy)

Write your answers here; Claude Code will need them.

- [ ] Assistant's **name**: ____________
- [ ] **Wake word(s)** (English): ____________
- [ ] **Wake word(s)** (Hindi, optional): ____________
- [ ] Default reply language when ambiguous: `en` / `hi`
- [ ] Monthly "big brain" budget: ₹ ______
- [ ] Top 5 things you want it to handle daily:
  1. ____________  2. ____________  3. ____________  4. ____________  5. ____________
- [ ] Vault folder path (inside Google Drive): ____________
- [ ] Folders it may read (the `workspace/` root): ____________
- [ ] Folders it may **never** touch: ____________
- [ ] Note tags that must **never** leave your machine: `private` / `health` / `finance_personal` / `family` / ____________
- [ ] Default `.vrm` avatar: ____________
- [ ] Android sync: folder-sync app / Obsidian Sync 💳
