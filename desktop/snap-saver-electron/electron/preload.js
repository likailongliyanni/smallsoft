// 安全桥接层：把主进程的能力暴露给界面（renderer）。
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("snapAPI", {
  version: "1.0.0",
  // 调 Python 后端：snapAPI.backend("sync_quota") → {ok, data} / {ok:false, error}
  backend: (cmd, args) => ipcRenderer.invoke("backend", cmd, args),
  // 复制到剪贴板
  copy: (text) => ipcRenderer.invoke("copy", text),
  // 选图片文件 → 路径数组
  pickImages: () => ipcRenderer.invoke("pickImages"),
  // 读图为 dataURL（显示缩略图）
  readThumb: (p) => ipcRenderer.invoke("readThumb", p),
});
