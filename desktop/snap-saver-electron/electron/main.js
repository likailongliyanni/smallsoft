// Electron 主进程：开窗口 + 启动 Python 后端(backend.py) + 转发界面命令。
const { app, BrowserWindow, ipcMain, clipboard } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let pyProc = null;
let pyBuffer = "";
let reqId = 0;
const pending = new Map(); // id -> {resolve, reject}

// 后端脚本在 electron/ 的上一级目录
const BACKEND = path.join(__dirname, "..", "backend.py");

function startBackend() {
  // 用系统 python（开发期）。打包后会换成内置解释器。
  const pythonExe = process.platform === "win32" ? "python" : "python3";
  pyProc = spawn(pythonExe, [BACKEND], {
    cwd: path.join(__dirname, ".."),
    windowsHide: true,
  });

  pyProc.stdout.on("data", (chunk) => {
    pyBuffer += chunk.toString("utf-8");
    let idx;
    while ((idx = pyBuffer.indexOf("\n")) >= 0) {
      const line = pyBuffer.slice(0, idx).trim();
      pyBuffer = pyBuffer.slice(idx + 1);
      if (!line) continue;
      let msg;
      try { msg = JSON.parse(line); } catch { continue; }
      const p = pending.get(msg.id);
      if (p) {
        pending.delete(msg.id);
        if (msg.ok) p.resolve(msg.data);
        else p.reject(new Error(msg.error || "后端错误"));
      }
    }
  });

  pyProc.stderr.on("data", (d) => console.error("[py]", d.toString("utf-8")));
  pyProc.on("exit", (code) => console.error("[py] backend exited", code));
}

// 给界面调用：发命令到 Python，返回 Promise
function callBackend(cmd, args) {
  return new Promise((resolve, reject) => {
    if (!pyProc) return reject(new Error("后端未启动"));
    const id = ++reqId;
    pending.set(id, { resolve, reject });
    pyProc.stdin.write(JSON.stringify({ id, cmd, args: args || {} }) + "\n");
    setTimeout(() => {
      if (pending.has(id)) { pending.delete(id); reject(new Error("请求超时")); }
    }, 60000);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 900,
    minHeight: 640,
    title: "智能截图软件",
    backgroundColor: "#f5faf7",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "index.html"));
}

// IPC：界面 → 主进程 → Python
ipcMain.handle("backend", async (_e, cmd, args) => {
  try {
    const data = await callBackend(cmd, args);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// 复制到剪贴板（界面直接用，无需 Python）
ipcMain.handle("copy", (_e, text) => {
  clipboard.writeText(String(text || ""));
  return true;
});

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (pyProc) { try { pyProc.kill(); } catch {} }
  if (process.platform !== "darwin") app.quit();
});
