"use strict";
const { contextBridge, ipcRenderer } = require("electron");

// Minimal, explicit surface for the renderer. No Node, no ipcRenderer leak.
contextBridge.exposeInMainWorld("overlay", {
  getConfig: () => ipcRenderer.invoke("get-config"),
  assistantName: () => ipcRenderer.invoke("assistant-name"),

  // main -> renderer
  onBus: (cb) => ipcRenderer.on("bus", (_e, snap) => cb(snap)),
  onLoadModel: (cb) => ipcRenderer.on("load-model", (_e, p) => cb(p)),
  onSetScale: (cb) => ipcRenderer.on("set-scale", (_e, s) => cb(s)),
  onReducedMotion: (cb) => ipcRenderer.on("reduced-motion", (_e, v) => cb(v)),

  // renderer -> main
  setInteractive: (v) => ipcRenderer.send("set-interactive", !!v),
  dragBy: (dx, dy) => ipcRenderer.send("drag-by", dx, dy),
  saveBounds: () => ipcRenderer.send("save-bounds"),
  nudgeScale: (dir) => ipcRenderer.send("nudge-scale", dir),
});
