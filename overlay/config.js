"use strict";
// Overlay config + signal-bus location. Pure Node, no Electron imports, so it
// can be unit-checked on its own.
const fs = require("fs");
const path = require("path");

const OVERLAY_DIR = __dirname;
const REPO_ROOT = path.resolve(OVERLAY_DIR, "..");
const STATE_FILE = path.join(OVERLAY_DIR, "jarvis-overlay.json");
const MODELS_DIR = path.join(OVERLAY_DIR, "models");

const DEFAULTS = {
  x: null,
  y: null,
  width: 420,
  height: 620,
  display: null,        // Electron display id; null = current
  modelPath: "",        // absolute; empty -> resolveDefaultModel()
  modelScale: 1.0,
  reducedMotion: false,
  hidden: false,
};

function readJSON(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function loadState() {
  return Object.assign({}, DEFAULTS, readJSON(STATE_FILE) || {});
}

let _saveTimer = null;
function saveState(patch) {
  const next = Object.assign(loadState(), patch || {});
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => {
    try {
      fs.mkdirSync(OVERLAY_DIR, { recursive: true });
      fs.writeFileSync(STATE_FILE, JSON.stringify(next, null, 2) + "\n");
    } catch (e) {
      console.error("[overlay] could not save state:", e.message);
    }
  }, 250);
  return next;
}

// Where backtalk writes .voice_state / .voice_waveform. start.ps1 points its
// signals_dir at vendor/backtalk; fall back sensibly.
function resolveBusDir() {
  const st = loadState();
  if (st.busDir && fs.existsSync(st.busDir)) return st.busDir;

  const bt = readJSON(path.join(REPO_ROOT, "vendor", "backtalk", "backtalk.json"));
  if (bt && bt.signals_dir && fs.existsSync(bt.signals_dir)) return bt.signals_dir;

  const vendorBt = path.join(REPO_ROOT, "vendor", "backtalk");
  if (fs.existsSync(vendorBt)) return vendorBt;
  return REPO_ROOT;
}

// First run with no model chosen: use the bundled robot if it's there.
function resolveDefaultModel() {
  const candidates = [
    path.join(REPO_ROOT, "rory-avatar", "somerobot.glb"),
    path.join(MODELS_DIR, "avatar.glb"),
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return "";
}

function assistantName() {
  const j = readJSON(path.join(REPO_ROOT, "config", "jarvis.json"));
  return (j && j.name) || "Assistant";
}

module.exports = {
  OVERLAY_DIR, REPO_ROOT, STATE_FILE, MODELS_DIR, DEFAULTS,
  loadState, saveState, resolveBusDir, resolveDefaultModel, assistantName,
};
