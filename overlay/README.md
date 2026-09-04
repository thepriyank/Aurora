# overlay/ — desktop 3D avatar (Phase 5)

A transparent, frameless, always-on-top Electron window that renders a 3D avatar
and reacts to `backtalk`'s signal bus. Replaces `ai-visualizer`; reuses its
`.voice_state` / `.voice_waveform` contract verbatim, so `vendor/backtalk` is
untouched.

## Run

```bash
cd overlay
npm install          # electron + three  (~one-time, ~250 MB)
npm start
```

Or from the repo root: `./start.ps1 overlay` (Windows) / `./start.sh overlay`.

The overlay is a **separate process** from the voice line — start it whenever;
it idles until `backtalk` starts writing the bus.

## What it does

- **Click-through** everywhere except the avatar. Moving the cursor over the
  model makes the window interactive; leaving it makes it transparent to clicks
  again (`setIgnoreMouseEvents(true, { forward:true })` + renderer hit-test).
- **Drag** the avatar to move it, **scroll** over it to resize. Position, scale,
  monitor, and reduced-motion are persisted in `overlay/jarvis-overlay.json`
  (git-ignored).
- **Tray menu**: show/hide, **Change model…**, move to another display, reset,
  reduced-motion toggle, quit.
- **States** from `.voice_state`:
  - `idle` — slow breathing + sway, dim glow
  - `listening` — head tilts up, glow brightens
  - `thinking` — glow pulses
  - `speaking` — the emissive "Lights" mesh tracks the audio amplitude from
    `.voice_waveform`; head bobs with it
- **Degrades**: bus goes stale → back to idle; model fails to load or
  reduced-motion is on → a CSS orb that still reacts to state.

## Models

- Default: `../rory-avatar/somerobot.glb` if present.
- **Any `.glb` / `.gltf`** works — tray → *Change model…*. The file is copied
  into `overlay/models/` and loaded live (no restart).
- The loader auto-stands-up Z-up / Sketchfab exports, centres, and scales the
  model to a fixed height. Idle/head motion is procedural, so a model needs a
  skeleton but **no animation clip and no blendshapes**. A mesh or material
  named `*light*` is driven as the "speaking" glow; without one the whole model
  just doesn't pulse (everything else still works).

## Files

| | |
|---|---|
| `main.js` | Electron main: window, tray, IPC, model dialog |
| `bus.js` | polls the signal-bus dir, emits `{state, rms}` |
| `config.js` | `jarvis-overlay.json` + bus-dir / default-model resolution |
| `preload.js` | the renderer's only bridge to main |
| `renderer/renderer.js` | three.js scene, GLTF load, state machine, interaction |
