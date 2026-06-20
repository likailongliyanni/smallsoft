// 安全桥接层：以后在这里把 Python 后端的能力安全地暴露给界面。
// 这一版（空窗口）暂时不暴露任何东西，先占位。
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("snapAPI", {
  version: "1.0.0",
  // 以后会加：syncQuota(), describeImage(path, hint), startCapture() 等
});
