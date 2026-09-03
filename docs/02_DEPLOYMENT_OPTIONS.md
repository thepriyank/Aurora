# DEPLOYMENT OPTIONS — Where To Run Your Assistant

## SHORT ANSWER

Run it **natively on your desktop**: Ollama + a few `uv`-managed Python processes + one Electron app. **Docker is not required** — the `jaredrhod` stack is deliberately native, and dropping Postgres/Qdrant/Redis (see `00_MASTER_BUILD_PLAN.md` §1.2) means there's very little infra left to containerise. Your **memory lives in a Google-Drive-synced Obsidian vault with git history**, so it survives a dead disk without any backup daemon.

Docker comes back **once**, optionally, in Phase 12: wrap *only* `brain/server.py` + Ollama so a mini-PC or VPS can be an always-on brain your phone always reaches.

---

## THE RUNTIME (what actually runs)

```
DESKTOP (Windows / macOS) — native, started by ./start.sh voice
────────────────────────────────────────────────────────────────
 Ollama                     native service, host GPU, model kept warm (KEEP_ALIVE=-1)
 vendor/backtalk            uv process — PTT, STT, TTS, signal-bus writer
 brain/                     uv process — agent loop, MCP tools, vault R/W
 brain/server.py            uv process — HTTP/WS on Tailscale (POST /turn, GET /state)
 overlay/                   Electron app — floating VRM avatar; "see me" stage
 scripts/vault_commit       cron / Task Scheduler / launchd — git snapshot every 30 min

MEMORY
────────────────────────────────────────────────────────────────
 Obsidian vault  ──▶ Google Drive for desktop ──▶ cloud ──▶ phone
                 └─▶ git (local + optional private remote) = history / restore

ANDROID (Flutter) — over Tailscale
────────────────────────────────────────────────────────────────
 default:  POST /turn  → desktop brain/server.py
 fallback: on-device small model + local (Drive-synced) vault copy
 always:   edge-glow overlay service + on-device STT/TTS
```

Two things to start on the desktop (Ollama + `start.sh`), and `start.sh` launches the rest. `overlay/` can auto-start at login.

---

## OPTION 1 — Native on your desktop ⭐ START HERE, PROBABLY FOREVER

**Pros**
- ✅ Free. No hosting bill.
- ✅ Full GPU / Apple-Neural-Engine speed — Ollama runs native on every platform.
- ✅ Complete privacy — memory, files, voice never leave the house in local mode.
- ✅ Simplest debugging — no container layer, no VM file-I/O penalty.
- ✅ Memory durability is *already solved* by Drive + git.

**Cons**
- ❌ **Only works when the desktop is on** — the phone then falls back to cloud or its on-device model.
- ❌ You install a handful of things natively (Ollama, `uv`, Node, espeak-ng). The Phase 12 `install.ps1`/`install.sh` scripts automate it.
- ❌ Three OSes = occasional "works on my Mac, not my Windows box" — mitigated by `uv` locking Python deps and Electron being one codebase.

**Best for:** Phases 0–11. Almost certainly your permanent setup.

---

## OPTION 2 — Native desktop **+ always-on brain elsewhere** (Phase 12, optional)

Containerise just `brain/server.py` + Ollama (CPU or a small GPU) on:

| Host | Notes |
|---|---|
| A mini-PC / old laptop at home, always on | Cheapest always-on; stays on your LAN + Tailscale; full privacy |
| Hetzner / DigitalOcean CPU VPS (~€5–15/mo) 💳 | Always on, static address; **no GPU** so the local model is slow — pair with free hosted open-weight for `big` |
| Oracle Cloud Free Tier (ARM, 4 core / 24 GB) | Genuinely free; availability is patchy |

Router logic gains one check: **phone's request → is the desktop brain reachable?**
- yes → desktop (fast, free, private)
- no → the always-on brain, or the phone's on-device model, or hosted `big`

**Do this only if "my phone must work at 3am while my PC sleeps" matters more than "zero monthly cost".**

---

## OPTION 3 — GPU cloud (RunPod / Vast.ai) 💳

Rent a GPU to host a big open-weight model. **Usually the wrong call:** cold starts of 1–5 min kill conversational latency, and OpenRouter/Groq host the same weights cheaper by amortising the GPU across thousands of users. Use it only for batch jobs or fine-tuning. For everyday use, "use the big brain" → OpenRouter is simpler and cheaper.

---

## MEMORY DURABILITY (learn this before a data loss)

1. **The vault is the product.** Everything else is reinstallable.
2. **Google Drive = availability** (same notes on every device), **git = history** (roll back a bad edit, recover a deleted note). You need both; neither alone is enough.
3. `scripts/vault_commit` snapshots every 30 min. Add `git push` to an off-machine private repo (Phase 12) so a dead disk loses at most 30 minutes.
4. **Test the restore.** Delete a note, `git checkout <sha> -- <note>`, confirm it's back. An untested restore is a rumour.
5. **Conflict hygiene (Phase 3):** git-ignore + sync-exclude `.obsidian/workspace*.json`, `.obsidian/cache`, `Vault/.trash`; write daily notes as per-device shards merged nightly. Do this *before* you point Drive at the vault.
6. **`docker compose down -v` deletes volumes** — only relevant if you take Option 2. Know it before you type it at 2am.

---

## PLATFORM NOTES

| Platform | Watch out for |
|---|---|
| **Windows** | Ollama uses the NVIDIA GPU natively — no WSL needed. Electron click-through needs `setIgnoreMouseEvents(..., {forward:true})`. Task Scheduler for `vault_commit`. |
| **macOS** | Ollama uses the Apple GPU natively. Grant Terminal/app **Input Monitoring** + **Microphone** + (for "see me") **Camera**. `LSUIElement` so the overlay has no Dock icon. `launchd` for `vault_commit`. Developer ID for a notarised overlay build (Phase 12). |
| **Android** | No global key hook — PTT is an in-app button. `SYSTEM_ALERT_WINDOW` + foreground service (persistent notification required) for the edge-glow. MediaPipe on-device is thermally heavy — "see me" is a short session with an idle timeout. Battery: glow only animates when state ≠ idle. |

---

## DECISION SHORTCUTS

| If this is true for you… | Do this |
|---|---|
| "I just want to build and use it" | Option 1. Native desktop. Nothing else. |
| "I'm on a Mac" | Option 1 — Ollama native is the whole reason it's easy on Mac. |
| "My phone must work when my PC is off" | Option 2 always-on brain, **or** rely on the phone's Phase 9 on-device model. |
| "Nothing personal may leave my machine" | Stay 100% local; tag sensitive notes `private`; never configure a `big` provider. |
| "My desktop is weak" | Option 1 still; say "use the big brain" more; run the phone in Desktop-Hub mode. |
| "I want a 70B-class model" | Don't rent a GPU — "use the big brain" → OpenRouter open-weight. |
