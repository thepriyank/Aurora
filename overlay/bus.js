"use strict";
// Poll backtalk's signal-bus files and emit a compact snapshot for the renderer.
//
//   .voice_state       idle | listening | thinking | speaking   (bare word)
//   .voice_waveform    {ts, samples:[64 floats]}  (~15 writes/sec while speaking)
//   .voice_loading_pid  exists while the "thinking" sound plays
//
// fs.watch is unreliable for rapid rewrites on Windows, so we poll. ~60 ms is
// well under one animation frame's worth of staleness at 60 fps.
const fs = require("fs");
const path = require("path");

const POLL_MS = 60;
const STALE_MS = 1500; // no waveform for this long while "speaking" -> treat as idle

class Bus {
  constructor(dir) {
    this.dir = dir;
    this._timer = null;
    this._cb = null;
    this._lastWaveTs = 0;
    this._lastState = "idle";
  }

  start(cb) {
    this._cb = cb;
    const tick = () => {
      try {
        this._cb(this._read());
      } catch (e) {
        /* never let a bad read kill the loop */
      }
      this._timer = setTimeout(tick, POLL_MS);
    };
    tick();
  }

  stop() {
    clearTimeout(this._timer);
    this._timer = null;
  }

  setDir(dir) {
    this.dir = dir;
  }

  _readText(name) {
    try {
      return fs.readFileSync(path.join(this.dir, name), "utf8").trim();
    } catch {
      return null;
    }
  }

  _readJSON(name) {
    const t = this._readText(name);
    if (!t) return null;
    try {
      return JSON.parse(t);
    } catch {
      return null;
    }
  }

  _read() {
    let state = this._readText(".voice_state") || "idle";
    const wave = this._readJSON(".voice_waveform");
    const thinking = fs.existsSync(path.join(this.dir, ".voice_loading_pid"));

    let rms = 0;
    let waveTs = this._lastWaveTs;
    if (wave && Array.isArray(wave.samples) && wave.samples.length) {
      waveTs = wave.ts || Date.now() / 1000;
      let sum = 0;
      for (const s of wave.samples) sum += s * s;
      rms = Math.min(1, Math.sqrt(sum / wave.samples.length) / 32768);
      this._lastWaveTs = waveTs;
    }

    // staleness guard: bus stopped mid-speech -> fall back to idle
    const ageMs = Date.now() - waveTs * 1000;
    if (state === "speaking" && ageMs > STALE_MS) {
      state = thinking ? "thinking" : "idle";
      rms = 0;
    }
    if (thinking && state === "idle") state = "thinking";

    this._lastState = state;
    return { state, rms, waveTs, connected: waveTs > 0 || state !== "idle" };
  }
}

module.exports = { Bus };
