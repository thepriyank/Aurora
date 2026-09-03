# THE BODY — Desktop 3D Floating Overlay, Android Edge-Glow, On-Device Hologram

Supersedes the earlier Live2D/pixi spec. This is the plan for Phases 5, 6, 8 and 10 of `00_MASTER_BUILD_PLAN.md`.

## Problem statement

`backtalk` gives the assistant a voice but no visible presence. The upstream `ai-visualizer` gives it a full-screen "face" — which we don't want. We want:

- **On laptops (Windows/macOS):** a small **floating 3D avatar** that sits on top of your other windows, lip-syncs while the assistant speaks, and idles when it doesn't.
- **On Android:** no avatar — just a **simple animated glow around the screen edge** that reacts to the assistant's state.
- **On command ("see me"), any device:** the screen gains a **hologram stage** that reads your **hand gestures** — the `barehands` experience, but running on the device instead of in a browser tab.

## Design principles (kept from the earlier spec — still right)

- The body is a **thin presentation layer**. It never touches LLM routing, memory, or the agent loop. It only *reads state and audio* and *sends "see me" / gesture events*.
- It is a **separate process** from `brain/` and `backtalk`, so either can restart without the other.
- Name / wake word / model path / scale come from the **same config** as the rest of the assistant. No hardcoding.
- It **degrades gracefully** — stale bus → idle pose, dropped backend → static image, low-end machine → 2-frame fallback. Never a crash, never a frozen model.

---

## Part A — Desktop 3D floating overlay (Phase 5)

### Shell

`overlay/` — an **Electron** app (chosen so the `barehands` browser code drops straight in later).

```js
new BrowserWindow({
  transparent: true,
  frame: false,
  alwaysOnTop: true,
  hasShadow: false,
  resizable: false,
  skipTaskbar: true,
  webPreferences: { backgroundThrottling: false },
});
win.setIgnoreMouseEvents(true, { forward: true }); // click-through…
// …toggled off only while the cursor is over the avatar's bounding box
win.setAlwaysOnTop(true, "screen-saver");
```

- macOS: `vibrancy` off, `visualEffectState: 'active'` not needed; set `LSUIElement` so no Dock icon.
- Windows: the `{ forward: true }` flag is what actually makes mouse events pass through to the app behind.

### Renderer

- `three.js` + **`@pixiv/three-vrm`** loading a `.vrm` model (see `01_YOUR_SETUP_CHECKLIST.md` for where to get one).
- Idle loop: eye blink on a random 2–6 s timer, breathing via chest bone or `A` viseme micro-oscillation, slow head sway. Bundle one Mixamo/VRMA idle clip or drive procedurally.
- Transparent WebGL clear colour (`alpha: true`, `setClearColor(0x000000, 0)`).

### Lip-sync + state (reads `backtalk`'s signal bus — no `backtalk` change)

| Bus file (from `backtalk` `signals_dir`) | Overlay uses it for |
|---|---|
| `.voice_state` = `idle` / `listening` / `thinking` / `speaking` | Expression + pose: attentive lean on `listening`, subtle "processing" head tilt + slower blink on `thinking`, mouth active on `speaking` |
| `.voice_waveform` = `{ ts, samples: [64 floats] }` | Drive VRM mouth blendshape (`aa` / `mouthOpen`) by RMS amplitude each animation frame. Target perceived lag < 150 ms |
| `.voice_loading_pid` present | Same as `thinking` if `.voice_state` is stale |

Copy the exact contract into `docs/SIGNAL_BUS.md` from `ai-visualizer` (see `05_REPO_REUSE_MAP.md` §3).

### Controls & persistence (`overlay/jarvis-overlay.json`)

```json
{
  "name": "Aria",
  "model_path": "~/jarvis/overlay/models/aria.vrm",
  "scale": 1.0,
  "position": { "x": 1680, "y": 720 },
  "monitor": 0,
  "bus_dir": "~/jarvis/vendor/backtalk/signals",
  "reduced_motion": false,
  "see_me_command_file": "~/jarvis/overlay/command"
}
```

- Tray icon: show / hide, "reset position", quit.
- Drag the avatar to move; scroll to scale; both persisted.
- `reduced_motion: true` or a WebGL-init failure → swap to a static PNG / 2-frame idle.

### Definition of Done — see plan Phase 5.

---

## Part B — "See me": barehands inside the overlay (Phase 6)

### Trigger

1. You say **"see me"** (phrase list in `config/jarvis.json`).
2. `brain` matches the intent and calls a local tool `overlay.see_me()`.
3. That tool writes `overlay/command` (`{"cmd":"see_me"}`) **and** sets `vendor/barehands` `state/state`.
4. `overlay/` watches `command`, expands the window to full-screen transparent, and **mounts `vendor/barehands/stage.html` content** in the renderer.

"Stop seeing me" → `{"cmd":"hide"}` → camera released, window shrinks back to the avatar box.

### What runs in the expanded window

- `vendor/barehands`' three.js board + hologram material, **unchanged**.
- **MediaPipe Hands** via `getUserMedia` (desktop keeps the upstream CDN load).
- The upstream **gesture set, thresholds untouched**:

| Gesture | Action |
|---|---|
| Tap (quick pinch) | Open / close a card |
| Pinch-drag | Move a card |
| Hold still while carrying | Rotate object in 3D |
| Two hands | Scale object |
| Flick | Throw a card across the screen |
| Clap (palms, fingers up) | Clear the board |
| Claw (open → claw → aim → hold 2 s → snap shut) | Pull an object across the screen |
| Empty pinch dragged sideways | Explode / reassemble a 3D model's views |

### Board content, driven by the assistant

Port `bin/board.sh` / `bin/board-state.sh` to a localhost endpoint (e.g. `POST 127.0.0.1:8794/board`) that `brain` can call:

| Verb | Effect |
|---|---|
| `present {title, body}` | Stage a titled card (e.g. read a note aloud while showing it) |
| `add_card` / `add_img` | Add a markdown card / an image from `media/` |
| `hand` | Point the on-stage hand at something |
| `explode` / `yank` / `hover` | Manipulate a staged 3D model |

- Media jail preserved: only `media/misc|fx|models|holo/`. `media/holo/*` renders as the blue hologram wireframe.
- `orbs` in `barehands.json` point at the vault: `{ "title": "Notes", "path": "<vault path>", "kind": "notes" }` so you can pull real notes onto the stage.

### Definition of Done — see plan Phase 6.

---

## Part C — Android edge-glow overlay (Phase 8)

No avatar on the phone. A **foreground service** + `SYSTEM_ALERT_WINDOW` draws an animated stroke just inside the screen edge.

- Permission: prompt for "Display over other apps"; persistent notification (Android requires it for a foreground service).
- The window is a full-screen, **fully click-through** overlay (`FLAG_NOT_TOUCHABLE` | `FLAG_NOT_FOCUSABLE`) that only paints a ~6–10 dp gradient border.
- State comes from the brain (Desktop Hub pushes it, or the on-device loop sets it):

| State | Glow behaviour |
|---|---|
| `idle` | Off, or a very faint static line |
| `listening` | One accent colour, slow breathing (~0.3 Hz) |
| `thinking` | Faster pulse (~1.5 Hz), cooler colour |
| `speaking` | Amplitude-reactive: border brightness follows the TTS envelope the phone is playing |

- Battery: the service only animates while state ≠ `idle`; it drops to a single static draw otherwise.
- Colour + thickness in the app settings, defaulting from `config/jarvis.json`.

### Definition of Done — see plan Phase 8.

---

## Part D — Android "see me" (Phase 10, optional)

The heaviest mobile piece — a short foreground session, never always-on.

- Native Activity: `CameraX` + **MediaPipe Tasks – Hand Landmarker (Android)** + a `SceneView`/GL surface rendering the same `barehands` board + hologram material.
- The upstream ratio-based gesture classifier is **ported** to MediaPipe Tasks landmarks — same gestures, same thresholds, ported not reinvented.
- Board content driven by the brain through the same Part-B verbs.
- Auto-close after an idle timeout (default ~3 min) to manage heat/battery.
- `stage.html?portrait=1` semantics inform the vertical layout.

### Definition of Done — see plan Phase 10.

---

## Open questions (non-blocking)

- Which `.vrm` ships as the default avatar (a free VRoid Hub model vs. one made in VRoid Studio vs. commissioned).
- Whether the overlay auto-launches at login or is started by the "Talk" shortcut.
- Lip-sync: amplitude-only (v1) vs. phoneme→viseme mapping from the TTS text (later, non-blocking).
- Android "see me": `SceneView` vs. raw `GLSurfaceView` for the hologram — decide when you get there.
