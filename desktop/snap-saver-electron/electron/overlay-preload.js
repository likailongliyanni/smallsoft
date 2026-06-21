const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("overlayAPI", {
  onRect: (cb) => ipcRenderer.on("overlay-rect", (_e, r) => cb(r)),
  onMessage: (cb) => ipcRenderer.on("overlay-message", (_e, data) => cb(data)),
  onWindow: (cb) => ipcRenderer.on("overlay-window", (_e, data) => cb(data)),
  onWindowHide: (cb) => ipcRenderer.on("overlay-window-hide", (_e, data) => cb(data)),
  onReset: (cb) => ipcRenderer.on("overlay-reset", (_e, data) => cb(data)),
});
