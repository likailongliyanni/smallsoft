const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("overlayAPI", {
  onRect: (cb) => ipcRenderer.on("overlay-rect", (_e, r) => cb(r)),
});
