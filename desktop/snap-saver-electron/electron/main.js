// Electron 主进程：开窗口 + 启动 Python 后端(backend.py) + 转发界面命令。
const { app, BrowserWindow, ipcMain, clipboard, dialog, desktopCapturer, screen, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let mainWin = null;
let captureWin = null;
let overlayWin = null;       // 拖框时的选框可视化覆盖窗（全屏透明、鼠标穿透）
let dragStartPt = null;      // 物理坐标的起点
let overlayBounds = null;    // 虚拟桌面的 DIP 边界
let overlayHideTimer = null;

let pyProc = null;
let pyBuffer = "";
let reqId = 0;

// 拖框选区可视化：Python 钩子推 capture_drag_start/move/end，这里画绿框
function ensureOverlay() {
  if (overlayWin && !overlayWin.isDestroyed()) return overlayWin;
  const displays = screen.getAllDisplays();
  const left = Math.min(...displays.map((d) => d.bounds.x));
  const top = Math.min(...displays.map((d) => d.bounds.y));
  const right = Math.max(...displays.map((d) => d.bounds.x + d.bounds.width));
  const bottom = Math.max(...displays.map((d) => d.bounds.y + d.bounds.height));
  overlayBounds = { x: left, y: top, width: right - left, height: bottom - top };
  overlayWin = new BrowserWindow({
    ...overlayBounds,
    show: false,
    frame: false, transparent: true, fullscreen: false,
    alwaysOnTop: true, skipTaskbar: true, resizable: false, movable: false,
    focusable: false, hasShadow: false, enableLargerThanScreen: true,
    webPreferences: { preload: path.join(__dirname, "overlay-preload.js"), contextIsolation: true },
  });
  overlayWin.setIgnoreMouseEvents(true);     // 鼠标穿透，不挡网页操作
  overlayWin.setAlwaysOnTop(true, "screen-saver");
  overlayWin.on("closed", () => { overlayWin = null; overlayBounds = null; });
  overlayWin.loadFile(path.join(__dirname, "overlay.html"));
  return overlayWin;
}

function sendOverlay(channel, payload) {
  const win = ensureOverlay();
  const send = () => {
    if (!win.isDestroyed()) win.webContents.send(channel, payload);
  };
  if (win.webContents.isLoading()) win.webContents.once("did-finish-load", send);
  else send();
  return win;
}

function showOverlay(win = ensureOverlay(), clearPendingHide = true) {
  if (clearPendingHide && overlayHideTimer) {
    clearTimeout(overlayHideTimer);
    overlayHideTimer = null;
  }
  win.setAlwaysOnTop(true, "screen-saver");
  win.showInactive();
  win.moveTop();
  return win;
}

function physicalRectToOverlay(bbox) {
  const a = screen.screenToDipPoint({ x: bbox[0], y: bbox[1] });
  const b = screen.screenToDipPoint({ x: bbox[2], y: bbox[3] });
  const bounds = overlayBounds || { x: 0, y: 0 };
  return {
    x: Math.min(a.x, b.x) - bounds.x,
    y: Math.min(a.y, b.y) - bounds.y,
    w: Math.abs(b.x - a.x),
    h: Math.abs(b.y - a.y),
    pixelW: Math.abs(bbox[2] - bbox[0]),
    pixelH: Math.abs(bbox[3] - bbox[1]),
  };
}

function handleDragOverlay(msg) {
  if (msg.event === "capture_drag_start") {
    dragStartPt = { x: msg.x, y: msg.y };
    const w = sendOverlay("overlay-reset", {});
    showOverlay(w);
  } else if (msg.event === "capture_drag_move") {
    if (!dragStartPt || !overlayWin || overlayWin.isDestroyed()) return;
    // 物理屏幕坐标 → DIP：用固定缩放因子线性换算（不用 screenToDipPoint —— 它对
    // 移动中的点转换不稳定，会让选框边缘逐帧漂移/缓慢缩小）。
    const scale = screen.getPrimaryDisplay().scaleFactor || 1;
    const bounds = overlayBounds || { x: 0, y: 0 };
    const ax = dragStartPt.x / scale, ay = dragStartPt.y / scale;
    const bx = msg.x / scale, by = msg.y / scale;
    const r = {
      x: Math.min(ax, bx) - bounds.x,
      y: Math.min(ay, by) - bounds.y,
      w: Math.abs(bx - ax),
      h: Math.abs(by - ay),
      pixelW: Math.abs(msg.x - dragStartPt.x),
      pixelH: Math.abs(msg.y - dragStartPt.y),
    };
    sendOverlay("overlay-rect", r);
  } else if (msg.event === "capture_drag_end") {
    dragStartPt = null;
    if (overlayWin && !overlayWin.isDestroyed()) {
      sendOverlay("overlay-reset", {});
      overlayWin.hide();
    }
  }
}

function handleLinkTransitionOverlay(msg) {
  if (msg.event === "capture_link_wait") {
    if (overlayHideTimer) clearTimeout(overlayHideTimer);
    const win = sendOverlay("overlay-message", {
      text: `正在打开：${msg.row_name || "下一个商品"}`,
      subtext: `${msg.delay || 2.5} 秒内暂停截图，请等待新页面显示`,
      ready: false,
    });
    showOverlay(win, false);
  } else if (msg.event === "capture_link_ready") {
    if (!overlayWin || overlayWin.isDestroyed()) return;
    sendOverlay("overlay-message", {
      text: `可以截图：${msg.row_name || "当前商品"}`,
      subtext: "请先确认网页商品正确，再按 Ctrl 拖框",
      ready: true,
    });
    overlayHideTimer = setTimeout(() => {
      if (overlayWin && !overlayWin.isDestroyed()) overlayWin.hide();
    }, 1200);
  }
}


function handleWindowHoverOverlay(msg) {
  if (msg.event === "capture_window_hover" && Array.isArray(msg.bbox)) {
    const win = sendOverlay("overlay-window", {
      ...physicalRectToOverlay(msg.bbox),
      title: msg.title || "当前窗口",
    });
    showOverlay(win);
  } else if (msg.event === "capture_window_hover_end") {
    sendOverlay("overlay-window-hide", {});
    if (!dragStartPt && overlayWin && !overlayWin.isDestroyed()) overlayWin.hide();
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
        handleLinkTransitionOverlay(msg);
        handleWindowHoverOverlay(msg);
        if (mainWin) mainWin.webContents.send("py-event", msg);
        continue;
      }
      const p = pending.get(msg.id);
      if (p) {
        pending.delete(msg.id);
        clearTimeout(p.timer);
        if (msg.ok) p.resolve(msg.data);
        else p.reject(new Error(msg.error || "后端错误"));
      }
    }
  });

  pyProc.stderr.on("data", (d) => console.error("[py]", d.toString("utf-8")));
  pyProc.on("exit", (code) => {
    console.error("[py] backend exited", code);
    for (const [id, p] of pending) {
      clearTimeout(p.timer);
      p.reject(new Error("后端进程已退出"));
      pending.delete(id);
    }
  });
}

// 给界面调用：发命令到 Python，返回 Promise
function callBackend(cmd, args) {
  return new Promise((resolve, reject) => {
    if (!pyProc) return reject(new Error("后端未启动"));
    const id = ++reqId;
    const timeoutMs = cmd === "repair_image" ? 480000
      : cmd === "describe_image" ? 180000
      : cmd === "export_doc" ? 120000
      : 60000;
    const timer = setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        reject(new Error(`请求超时（${Math.round(timeoutMs / 1000)} 秒）`));
      }
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    pyProc.stdin.write(JSON.stringify({ id, cmd, args: args || {} }) + "\n");
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
  win.on("closed", () => {
    mainWin = null;
    if (overlayWin && !overlayWin.isDestroyed()) overlayWin.close();
  });
  return win;
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
ipcMain.handle("pickFolder", async (_e, options = {}) => {
  const r = await dialog.showOpenDialog({
    title: options.title || "选择图片文件夹",
    defaultPath: options.defaultPath || undefined,
    properties: ["openDirectory"],
  });
  return r.canceled ? "" : r.filePaths[0];
});

function safeDocName(value) {
  return String(value || "使用说明")
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[. ]+$/g, "").slice(0, 60) || "使用说明";
}

function sanitizeEditorHtml(value) {
  return String(value || "")
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<\/?(?:script|iframe|object|embed|link|meta|base)[^>]*>/gi, "")
    .replace(/\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/javascript\s*:/gi, "");
}

function richDocumentHtml(editorHtml, orientation, theme = "plain") {
  const quillCss = fs.readFileSync(path.join(__dirname, "node_modules", "quill", "dist", "quill.core.css"), "utf8");
  const page = orientation === "landscape" ? "A4 landscape" : "A4 portrait";
  const themeClass = theme === "green" ? " theme-green" : "";
  return `<!doctype html><html><head><meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:">
    <style>${quillCss}
      @page { size: ${page}; margin: 16mm; }
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; background: #fff; color: #111; }
      body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
      .document { width: 100%; max-width: 980px; margin: 0 auto; padding: 58px 68px; font-size: 16px; line-height: 1.75; }
      .document h1 { margin: 0 0 22px; font-size: 36px; line-height: 1.25; color: #111; }
      .document h2 { margin: 30px 0 13px; color: #111; }
      .document h3 { margin: 24px 0 10px; }
      .document p { margin: 0 0 12px; }
      .document img { display: block; width: auto; max-width: 100%; max-height: 900px; margin: 22px auto 12px; border-radius: 0; object-fit: contain; }
      .document img.selling-point-image { padding: 12px; background: #fff; border: 0; }
      .document blockquote { margin: 14px 0; padding: 0; border: 0; background: #fff; color: #111; }
      .product-params-block { margin: 16px 0 24px; }
      .product-params-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      .product-params-table th, .product-params-table td { padding: 10px 12px; border: 1px solid #d5d5d5; text-align: left; vertical-align: top; }
      .product-params-table th { width: 28%; background: #fff; color: #111; font-weight: 600; }
      .product-params-table td { background: #fff; word-break: break-word; }
      .document.theme-green h1 { color: #0b1f16; }
      .document.theme-green h2 { color: #123b28; }
      .document.theme-green img.selling-point-image { border: 1px solid #edf0ee; }
      .document.theme-green blockquote { padding: 10px 14px; border-left: 4px solid #079a48; background: #eefbf3; color: #234b37; }
      .document.theme-green .product-params-table th, .document.theme-green .product-params-table td { border-color: #dce6e0; }
      .document.theme-green .product-params-table th { background: #f1f7f3; color: #234b37; }
      .ql-align-center { text-align: center; } .ql-align-right { text-align: right; } .ql-align-justify { text-align: justify; }
      .ql-size-small { font-size: .75em; } .ql-size-large { font-size: 1.5em; } .ql-size-huge { font-size: 2.5em; }
      @media print { .document { max-width: none; padding: 0; } }
    </style></head><body><main class="document ql-editor${themeClass}">${sanitizeEditorHtml(editorHtml)}</main></body></html>`;
}

ipcMain.handle("exportRichDoc", async (_e, payload = {}) => {
  let renderWin = null;
  const tempFiles = [];
  try {
    const orientation = payload.orientation === "landscape" ? "landscape" : "portrait";
    const format = ["long", "segments"].includes(payload.format) ? payload.format : "pdf";
    const theme = payload.theme === "green" ? "green" : "plain";
    const outRoot = path.resolve(String(payload.outDir || path.join(app.getPath("documents"), "存图结果")));
    const outDir = path.join(outRoot, "文档");
    fs.mkdirSync(outDir, { recursive: true });
    const title = safeDocName(payload.title);
    const now = new Date();
    const stamp = [now.getFullYear(), now.getMonth() + 1, now.getDate(),
      now.getHours(), now.getMinutes(), now.getSeconds()]
      .map((value) => String(value).padStart(2, "0")).join("");
    const htmlPath = path.join(app.getPath("temp"), `snap-rich-${process.pid}-${Date.now()}.html`);
    fs.writeFileSync(htmlPath, richDocumentHtml(payload.html, orientation, theme), "utf8");
    tempFiles.push(htmlPath);
    const viewportWidth = orientation === "landscape" ? 1500 : 1120;
    const bitmapScale = format === "pdf" ? 1 : 2;
    renderWin = new BrowserWindow({
      show: false, width: viewportWidth, height: 900, frame: false,
      enableLargerThanScreen: true,
      webPreferences: {
        contextIsolation: true, nodeIntegration: false, sandbox: true, offscreen: format !== "pdf",
      },
    });
    await renderWin.loadFile(htmlPath);
    if (format !== "pdf") {
      // 设备像素比 2：保持 1120/1500 CSS 排版宽度，同时实际截图输出双倍像素。
      renderWin.webContents.debugger.attach("1.3");
      await renderWin.webContents.debugger.sendCommand("Emulation.setDeviceMetricsOverride", {
        width: viewportWidth * bitmapScale, height: 900 * bitmapScale,
        deviceScaleFactor: bitmapScale, mobile: false,
      });
    }
    await renderWin.webContents.executeJavaScript(
      `Promise.all(Array.from(document.images).map(img => img.complete ? true : new Promise(resolve => { img.onload = img.onerror = resolve; })))`);

    if (format === "pdf") {
      const target = path.join(outDir, `${title}_${stamp}.pdf`);
      const pdf = await renderWin.webContents.printToPDF({
        pageSize: "A4", landscape: orientation === "landscape",
        printBackground: true, preferCSSPageSize: true,
      });
      fs.writeFileSync(target, pdf);
      return { ok: true, path: target, dir: outDir };
    }

    if (format === "segments") {
      const blocks = await renderWin.webContents.executeJavaScript(
        "Array.from(document.querySelector('.document').children).map(function(el){ return { tag: el.tagName, className: String(el.className || ''), html: el.outerHTML }; })");
      const groups = [];
      let current = [];
      for (const block of blocks) {
        const isHeading = /^H[1-3]$/.test(block.tag);
        const isImage = block.tag === "IMG";
        const currentHasImage = current.some((item) => item.tag === "IMG");
        if (current.length && (isHeading || (isImage && currentHasImage))) {
          groups.push(current);
          current = [];
        }
        current.push(block);
      }
      if (current.length) groups.push(current);
      if (!groups.length) throw new Error("文档中没有可导出的内容块。");

      const segmentDir = path.join(outDir, title + "_" + stamp + "_分段图");
      fs.mkdirSync(segmentDir, { recursive: true });
      const paths = [];
      for (let index = 0; index < groups.length; index++) {
        const segmentHtmlPath = path.join(
          app.getPath("temp"),
          "snap-segment-" + process.pid + "-" + Date.now() + "-" + index + ".html");
        const content = groups[index].map((item) => item.html).join("");
        fs.writeFileSync(segmentHtmlPath, richDocumentHtml(content, "portrait", theme), "utf8");
        tempFiles.push(segmentHtmlPath);
        await renderWin.loadFile(segmentHtmlPath);
        await renderWin.webContents.executeJavaScript(
          "Promise.all(Array.from(document.images).map(function(img){ return img.complete ? true : new Promise(function(resolve){ img.onload = img.onerror = resolve; }); }))");
        const height = await renderWin.webContents.executeJavaScript(
          "Math.ceil(Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))");
        const segmentHeight = Math.max(320, Math.min(4500, height));
        await renderWin.webContents.debugger.sendCommand("Emulation.setDeviceMetricsOverride", {
          width: viewportWidth * bitmapScale, height: segmentHeight * bitmapScale,
          deviceScaleFactor: bitmapScale, mobile: false,
        });
        await new Promise((resolve) => setTimeout(resolve, 60));
        const image = await renderWin.webContents.capturePage();
        const target = path.join(segmentDir, String(index + 1).padStart(2, "0") + ".png");
        fs.writeFileSync(target, image.toPNG());
        paths.push(target);
      }
      return { ok: true, path: paths[0], paths, dir: segmentDir };
    }

    const docHeight = await renderWin.webContents.executeJavaScript(
      `Math.ceil(Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))`);
    const slicePaths = [];
    const maxSlice = 4000;
    for (let y = 0, part = 0; y < docHeight; y += maxSlice, part++) {
      const height = Math.min(maxSlice, docHeight - y);
      await renderWin.webContents.debugger.sendCommand("Emulation.setDeviceMetricsOverride", {
        width: viewportWidth * bitmapScale, height: height * bitmapScale,
        deviceScaleFactor: bitmapScale, mobile: false,
      });
      await renderWin.webContents.executeJavaScript(`window.scrollTo(0, ${y})`);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const image = await renderWin.webContents.capturePage();
      const slicePath = path.join(app.getPath("temp"), `snap-rich-${process.pid}-${Date.now()}-${part}.png`);
      fs.writeFileSync(slicePath, image.toPNG());
      slicePaths.push(slicePath);
      tempFiles.push(slicePath);
    }
    const result = await callBackend("stitch_long_image", {
      paths: slicePaths, out_dir: outRoot, title,
    });
    return { ok: true, path: result.path, dir: result.dir };
  } catch (error) {
    return { ok: false, error: error.message || String(error) };
  } finally {
    if (renderWin && !renderWin.isDestroyed()) {
      try { if (renderWin.webContents.debugger.isAttached()) renderWin.webContents.debugger.detach(); } catch {}
      renderWin.destroy();
    }
    for (const file of tempFiles) {
      try { fs.unlinkSync(file); } catch {}
    }
  }
});

// 用系统默认程序打开生成结果。主窗口先最小化，避免挡住图片/PDF/资源管理器。
ipcMain.handle("openExternalPath", async (_e, target) => {
  const filePath = String(target || "").trim();
  if (!filePath || !fs.existsSync(filePath)) {
    return { ok: false, error: "目录或文件不存在。" };
  }
  if (mainWin && !mainWin.isDestroyed()) mainWin.minimize();
  const error = await shell.openPath(filePath);
  if (error) {
    if (mainWin && !mainWin.isDestroyed()) mainWin.restore();
    return { ok: false, error };
  }
  return { ok: true };
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
  // 提前加载透明选框层，第一次截图也无需临时创建窗口。
  ensureOverlay();
  app.on("activate", () => {
    if (!mainWin) {
      createWindow();
      ensureOverlay();
    }
  });
});

app.on("window-all-closed", () => {
  if (pyProc) { try { pyProc.kill(); } catch {} }
  if (process.platform !== "darwin") app.quit();
});
