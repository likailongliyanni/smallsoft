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
  // 选表格/文本文件 → 单个路径
  pickFile: () => ipcRenderer.invoke("pickFile"),
  // 选文件夹 → 路径
  pickFolder: (options) => ipcRenderer.invoke("pickFolder", options),
  // 用系统默认程序打开，并让主程序自动最小化
  openExternalPath: (p) => ipcRenderer.invoke("openExternalPath", p),
  // 把所见即所得编辑器内容导出为 PDF / 长图
  exportRichDoc: (payload) => ipcRenderer.invoke("exportRichDoc", payload),
  // 读图为 dataURL（显示缩略图）
  readThumb: (p) => ipcRenderer.invoke("readThumb", p),
  // 开始截图（弹全屏框选层）
  startCapture: () => ipcRenderer.invoke("startCapture"),
  // 截图保存完成回调
  onCaptureSaved: (cb) => ipcRenderer.on("capture-saved", (_e, res) => cb(res)),
  // 后台事件推送（批量采集进度/截图等）
  onPyEvent: (cb) => ipcRenderer.on("py-event", (_e, msg) => cb(msg)),
});

// 截图覆盖层（capture.html）专用桥
contextBridge.exposeInMainWorld("captureAPI", {
  onBg: (cb) => ipcRenderer.on("capture-bg", (_e, data) => cb(data)),
  done: (data) => ipcRenderer.send("capture-done", data),
});
