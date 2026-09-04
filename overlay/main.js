"use strict";
const {
  app, BrowserWindow, Tray, Menu, ipcMain, screen, dialog, nativeImage,
} = require("electron");
const fs = require("fs");
const path = require("path");

const cfg = require("./config");
const { Bus } = require("./bus");

let win = null;
let tray = null;
let bus = null;
let state = cfg.loadState();

// --------------------------------------------------------------------------- //
// window
// --------------------------------------------------------------------------- //
function currentDisplay() {
  const all = screen.getAllDisplays();
  if (state.display != null) {
    const d = all.find((x) => x.id === state.display);
    if (d) return d;
  }
  const pt = screen.getCursorScreenPoint();
  return screen.getDisplayNearestPoint(pt);
}

function createWindow() {
  const disp = currentDisplay();
  const w = state.width || cfg.DEFAULTS.width;
  const h = state.height || cfg.DEFAULTS.height;
  const x = state.x != null ? state.x : disp.workArea.x + disp.workArea.width - w - 24;
  const y = state.y != null ? state.y : disp.workArea.y + disp.workArea.height - h - 24;

  win = new BrowserWindow({
    x, y, width: w, height: h,
    transparent: true,
    frame: false,
    resizable: false,
    movable: true,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    hasShadow: false,
    focusable: false,
    alwaysOnTop: true,
    show: !state.hidden,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true }); // click-through by default
  win.loadFile(path.join(__dirname, "renderer", "index.html"));

  win.on("moved", () => {
    const b = win.getBounds();
    state = cfg.saveState({ x: b.x, y: b.y });
  });
}

// --------------------------------------------------------------------------- //
// tray
// --------------------------------------------------------------------------- //
function trayIcon() {
  const p = path.join(__dirname, "assets", "tray.png");
  if (fs.existsSync(p)) return nativeImage.createFromPath(p);
  // 16px transparent dot so the tray still shows something
  return nativeImage.createFromDataURL(
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKklEQVR42mNgGAX" +
    "UBv///2fAhwEDGQY0MDCwYWBg+M+ABgYyDGgAAG2XCgqM8V6mAAAAAElFTkSuQmCC"
  );
}

function buildTrayMenu() {
  const displays = screen.getAllDisplays();
  return Menu.buildFromTemplate([
    {
      label: win && win.isVisible() ? "Hide avatar" : "Show avatar",
      click: () => toggleVisible(),
    },
    { type: "separator" },
    { label: "Change model…", click: pickModel },
    {
      label: "Move to display",
      submenu: displays.map((d, i) => ({
        label: `${i + 1}: ${d.size.width}×${d.size.height}${d.id === currentDisplay().id ? "  ✓" : ""}`,
        click: () => moveToDisplay(d),
      })),
    },
    { label: "Reset position & size", click: resetBounds },
    {
      label: "Reduced motion",
      type: "checkbox",
      checked: !!state.reducedMotion,
      click: (mi) => {
        state = cfg.saveState({ reducedMotion: mi.checked });
        win && win.webContents.send("reduced-motion", mi.checked);
      },
    },
    { type: "separator" },
    { label: "Quit overlay", click: () => app.quit() },
  ]);
}

function refreshTray() {
  if (!tray) return;
  tray.setContextMenu(buildTrayMenu());
  tray.setToolTip(`${cfg.assistantName()} — avatar overlay`);
}

// --------------------------------------------------------------------------- //
// actions
// --------------------------------------------------------------------------- //
function toggleVisible() {
  if (!win) return;
  if (win.isVisible()) win.hide();
  else win.show();
  state = cfg.saveState({ hidden: !win.isVisible() });
  refreshTray();
}

function moveToDisplay(d) {
  if (!win) return;
  const b = win.getBounds();
  win.setBounds({
    x: Math.round(d.workArea.x + d.workArea.width - b.width - 24),
    y: Math.round(d.workArea.y + d.workArea.height - b.height - 24),
    width: b.width, height: b.height,
  });
  const nb = win.getBounds();
  state = cfg.saveState({ display: d.id, x: nb.x, y: nb.y });
  refreshTray();
}

function resetBounds() {
  state = cfg.saveState({
    x: null, y: null, display: null, modelScale: 1.0,
    width: cfg.DEFAULTS.width, height: cfg.DEFAULTS.height,
  });
  if (win) {
    win.close();
    win = null;
  }
  state = cfg.loadState();
  createWindow();
  refreshTray();
}

async function pickModel() {
  const res = await dialog.showOpenDialog({
    title: "Choose a 3D avatar model",
    properties: ["openFile"],
    filters: [{ name: "3D model (glTF / GLB)", extensions: ["glb", "gltf"] }],
  });
  if (res.canceled || !res.filePaths.length) return;
  const src = res.filePaths[0];
  let dest = src;
  try {
    fs.mkdirSync(cfg.MODELS_DIR, { recursive: true });
    dest = path.join(cfg.MODELS_DIR, path.basename(src));
    if (path.resolve(src) !== path.resolve(dest)) fs.copyFileSync(src, dest);
  } catch (e) {
    dest = src; // fall back to referencing it in place
  }
  state = cfg.saveState({ modelPath: dest, modelScale: 1.0 });
  win && win.webContents.send("load-model", dest);
}

// --------------------------------------------------------------------------- //
// IPC from the renderer
// --------------------------------------------------------------------------- //
ipcMain.handle("get-config", () => {
  const modelPath = state.modelPath || cfg.resolveDefaultModel();
  return {
    modelPath,
    modelScale: state.modelScale || 1.0,
    reducedMotion: !!state.reducedMotion,
    name: cfg.assistantName(),
  };
});

ipcMain.handle("assistant-name", () => cfg.assistantName());

// The renderer hit-tests the avatar and toggles interactivity so the rest of
// the window stays click-through.
ipcMain.on("set-interactive", (_e, interactive) => {
  if (win) win.setIgnoreMouseEvents(!interactive, { forward: true });
});

ipcMain.on("drag-by", (_e, dx, dy) => {
  if (!win) return;
  const b = win.getBounds();
  win.setBounds({ x: b.x + Math.round(dx), y: b.y + Math.round(dy), width: b.width, height: b.height });
});

ipcMain.on("save-bounds", () => {
  if (!win) return;
  const b = win.getBounds();
  state = cfg.saveState({ x: b.x, y: b.y });
});

ipcMain.on("nudge-scale", (_e, dir) => {
  let s = (state.modelScale || 1.0) * (dir > 0 ? 1.08 : 1 / 1.08);
  s = Math.max(0.3, Math.min(3.0, s));
  state = cfg.saveState({ modelScale: s });
  win && win.webContents.send("set-scale", s);
});

// --------------------------------------------------------------------------- //
// lifecycle
// --------------------------------------------------------------------------- //
app.whenReady().then(() => {
  createWindow();

  tray = new Tray(trayIcon());
  refreshTray();
  tray.on("click", () => toggleVisible());
  screen.on("display-added", refreshTray);
  screen.on("display-removed", refreshTray);

  bus = new Bus(cfg.resolveBusDir());
  bus.start((snap) => {
    if (win && !win.isDestroyed() && win.isVisible()) {
      win.webContents.send("bus", snap);
    }
  });

  if (!state.modelPath && !cfg.resolveDefaultModel()) {
    dialog.showMessageBox({
      type: "info",
      message: "No avatar model set",
      detail: "Pick a .glb or .gltf model from the tray menu → “Change model…”.",
    });
  }
});

app.on("window-all-closed", (e) => {
  // keep running in the tray
  e.preventDefault();
});

app.on("before-quit", () => {
  bus && bus.stop();
});
