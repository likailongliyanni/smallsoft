// Electron 主进程：开窗口 + 启动 Python 后端(backend.py) + 转发界面命令。
const { app, BrowserWindow, ipcMain, clipboard, dialog, desktopCapturer, screen } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let mainWin = null;
let captureWin = null;
let overlayWin = null;       // 拖框时的选框可视化覆盖窗（全屏透明、鼠标穿透）
let dragStartPt = null;      // 物理坐标的起点

let pyProc = null;
let pyBuffer = "";
let reqId = 0;

// 拖框选区可视化：Python 钩子推 capture_drag_start/move/end，这里画绿框
function ensureOverlay() {
  if (overlayWin && !overlayWin.isDestroyed()) return overlayWin;
  const primary = screen.getPrimaryDisplay();
  const { width, height } = primary.size;
  overlayWin = new BrowserWindow({
    x: 0, y: 0, width, height,
    frame: false, transparent: true, fullscreen: false,
    alwaysOnTop: true, skipTaskbar: true, resizable: false, movable: false,
    focusable: false, hasShadow: false, enableLargerThanScreen: true,
    webPreferences: { preload: path.join(__dirname, "overlay-preload.js"), contextIsolation: true },
  });
  overlayWin.setIgnoreMouseEvents(true);     // 鼠标穿透，不挡网页操作
  overlayWin.setAlwaysOnTop(true, "screen-saver");
  overlayWin.loadFile(path.join(__dirname, "overlay.html"));
  return overlayWin;
}

function handleDragOverlay(msg) {
  const sf = screen.getPrimaryDisplay().scaleFactor || 1;
  if (msg.event === "capture_drag_start") {
    dragStartPt = { x: msg.x, y: msg.y };
    const w = ensureOverlay();
    w.showInactive();
  } else if (msg.event === "capture_drag_move") {
    if (!dragStartPt || !overlayWin || overlayWin.isDestroyed()) return;
    // 物理坐标 → CSS 逻辑坐标（除以缩放）
    const r = {
      x: Math.min(dragStartPt.x, msg.x) / sf,
      y: Math.min(dragStartPt.y, msg.y) / sf,
      w: Math.abs(msg.x - dragStartPt.x) / sf,
      h: Math.abs(msg.y - dragStartPt.y) / sf,
    };
    overlayWin.webContents.send("overlay-rect", r);
  } else if (msg.event === "capture_drag_end") {
    dragStartPt = null;
    if (overlayWin && !overlayWin.isDestroyed()) overlayWin.hide();
  }
}
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
      // 后台事件推送（截图进度等）→ 转发给界面
      if (msg.event) {
        handleDragOverlay(msg);  // 拖框时显示选框
        if (mainWin) mainWin.webContents.send("py-event", msg);
        continue;
      }
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
  mainWin = win;
}

// ── 截图：抓全屏 → 全屏覆盖层框选 → 裁剪存盘 ──
async function startCapture() {
  // 主屏尺寸（含缩放）
  const primary = screen.getPrimaryDisplay();
  const { width, height } = primary.size;
  const scale = primary.scaleFactor || 1;

  // 抓整屏（按物理像素，避免高分屏糊）
  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize: { width: Math.round(width * scale), height: Math.round(height * scale) },
  });
  if (!sources.length) throw new Error("无法获取屏幕画面");
  const fullPng = sources[0].thumbnail.toDataURL();

  // 隐藏主窗口，避免遮挡截图
  if (mainWin) mainWin.hide();
  await new Promise((r) => setTimeout(r, 180));

  captureWin = new BrowserWindow({
    x: 0, y: 0, width, height,
    frame: false, transparent: false, fullscreen: true,
    alwaysOnTop: true, skipTaskbar: true, resizable: false, movable: false,
    backgroundColor: "#000000",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  await captureWin.loadFile(path.join(__dirname, "capture.html"));
  captureWin.webContents.send("capture-bg", { img: fullPng, w: width, h: height, scale });
  captureWin.focus();
}

// 覆盖层框选完成：data{ dataURL } 或取消
ipcMain.on("capture-done", async (_e, data) => {
  if (captureWin) { captureWin.close(); captureWin = null; }
  if (mainWin) mainWin.show();
  if (data && data.dataURL) {
    try {
      const raw = data.dataURL.split(",")[1];
      const res = await callBackend("save_capture", { png_base64: raw });
      if (mainWin) mainWin.webContents.send("capture-saved", res);
    } catch (err) {
      if (mainWin) mainWin.webContents.send("capture-saved", { error: err.message });
    }
  }
});

ipcMain.handle("startCapture", async () => {
  try { await startCapture(); return { ok: true }; }
  catch (e) {
    if (mainWin) mainWin.show();
    return { ok: false, error: e.message };
  }
});

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

// 选图片文件（原生对话框），返回路径数组
ipcMain.handle("pickImages", async () => {
  const r = await dialog.showOpenDialog({
    title: "选择截图",
    properties: ["openFile", "multiSelections"],
    filters: [{ name: "图片", extensions: ["jpg", "jpeg", "png", "bmp", "webp"] }],
  });
  return r.canceled ? [] : r.filePaths;
});

// 选表格文件（Excel/CSV/txt），返回单个路径
ipcMain.handle("pickFile", async () => {
  const r = await dialog.showOpenDialog({
    title: "选择名称+链接列表文件",
    properties: ["openFile"],
    filters: [{ name: "表格/文本", extensions: ["xlsx", "xlsm", "csv", "txt"] }],
  });
  return r.canceled ? "" : r.filePaths[0];
});

// 选文件夹，返回路径
ipcMain.handle("pickFolder", async () => {
  const r = await dialog.showOpenDialog({
    title: "选择图片文件夹",
    properties: ["openDirectory"],
  });
  return r.canceled ? "" : r.filePaths[0];
});

// 读图为 dataURL（界面显示缩略图用）
ipcMain.handle("readThumb", (_e, filePath) => {
  try {
    const buf = fs.readFileSync(filePath);
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mime = ext === "png" ? "image/png" : ext === "webp" ? "image/webp" : "image/jpeg";
    return `data:${mime};base64,` + buf.toString("base64");
  } catch {
    return "";
  }
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
