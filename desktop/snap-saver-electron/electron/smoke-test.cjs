const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");

const transparentPixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLz0QAAAABJRU5ErkJggg==";
app.disableHardwareAcceleration();
let folderScanCount = 0;

ipcMain.handle("backend", (_event, cmd) => {
  if (cmd === "get_settings") {
    return { ok: true, data: { output_dir: path.join(app.getPath("documents"), "存图结果") } };
  }
  if (cmd === "get_serial") return { ok: true, data: { serial: "00-11-22-33-44-55" } };
  if (cmd === "register") return { ok: true, data: { quota: { available: 10 } } };
  if (cmd === "list_folder_images") {
    folderScanCount++;
    const images = [{ path: "sample-a.png", name: "sample-a.png", mtime_ns: 1, size: 10 }];
    if (folderScanCount > 1) images.push({ path: "sample-b.png", name: "sample-b.png", mtime_ns: 1, size: 10 });
    return { ok: true, data: { images, dir: "sample-folder" } };
  }
  return { ok: true, data: {} };
});
for (const channel of ["copy", "pickImages", "pickFile", "pickFolder", "openExternalPath", "exportRichDoc", "readThumb", "startCapture"]) {
  ipcMain.handle(channel, () => channel === "readThumb" ? transparentPixel : { ok: true });
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    width: 1280,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  try {
    await win.loadFile(path.join(__dirname, "index.html"));
    const script = "(async () => {"
      + "document.getElementById('docBtn').click();"
      + "document.getElementById('docToggleParams').click();"
      + "const rows = document.querySelectorAll('.product-param-row');"
      + "rows[0].querySelector('[data-role=\"value\"]').value = '100% 棉';"
      + "document.getElementById('productInsertTable').click();"
      + "await insertDocImage({ path: 'sample.png', thumb: " + JSON.stringify(transparentPixel) + " }, true, true);"
      + "const image = document.querySelector('#docEditor img');"
      + "image.click();"
      + "const handle = document.querySelector('.doc-image-resizer-handle');"
      + "handle.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: 0, pointerId: 1 }));"
      + "handle.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: 200, pointerId: 1 }));"
      + "handle.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, clientX: 200, pointerId: 1 }));"
      + "repairSourceDir = 'sample-folder';"
      + "await refreshRepairFolder(true);"
      + "const firstRefreshCount = repairImgs.length;"
      + "await refreshRepairFolder(false);"
      + "const secondRefreshCount = repairImgs.length;"
      + "return {"
      + "modalVisible: document.getElementById('docModal').style.display === 'flex',"
      + "parameterRows: rows.length,"
      + "tableRows: document.querySelectorAll('.product-params-table tr').length,"
      + "imageWidth: image.style.width,"
      + "imageRadius: getComputedStyle(image).borderRadius,"
      + "sellingPoint: image.classList.contains('selling-point-image'),"
      + "resizerVisible: document.querySelector('.doc-image-resizer').classList.contains('is-visible'),"
      + "segmentButton: Boolean(document.getElementById('docExportSegments')),"
      + "autoRefreshAddsImage: firstRefreshCount === 1 && secondRefreshCount === 2,"
      + "plainTheme: document.getElementById('docTheme').value === 'plain'"
      + "&& getComputedStyle(document.querySelector('#docEditor blockquote')).backgroundColor === 'rgb(255, 255, 255)'"
      + "&& getComputedStyle(document.querySelector('#docEditor blockquote')).borderLeftWidth === '0px'"
      + "};})()";
    const result = await win.webContents.executeJavaScript(script);
    const highResWin = new BrowserWindow({
      show: false, frame: false, width: 1120, height: 400,
      webPreferences: { contextIsolation: true, nodeIntegration: false, offscreen: true },
    });
    await highResWin.loadURL("data:text/html,<html><body style='margin:0;background:white'></body></html>");
    highResWin.webContents.debugger.attach("1.3");
    await highResWin.webContents.debugger.sendCommand("Emulation.setDeviceMetricsOverride", {
      width: 2240, height: 800, deviceScaleFactor: 2, mobile: false,
    });
    const cssWidth = await highResWin.webContents.executeJavaScript("window.innerWidth");
    const captureSize = (await highResWin.webContents.capturePage()).getSize();
    result.highResCssWidth = cssWidth;
    result.highResCaptureWidth = captureSize.width;
    result.highResRender = cssWidth === 1120 && captureSize.width === 2240;
    highResWin.webContents.debugger.detach();
    highResWin.destroy();
    const passed = result.modalVisible
      && result.parameterRows === 3
      && result.tableRows === 1
      && parseInt(result.imageWidth, 10) >= 200
      && result.imageRadius === "0px"
      && result.sellingPoint
      && result.resizerVisible
      && result.segmentButton
      && result.autoRefreshAddsImage
      && result.plainTheme
      && result.highResRender;
    console.log(JSON.stringify({ passed, ...result }));
    app.exit(passed ? 0 : 1);
  } catch (error) {
    console.error(error);
    app.exit(1);
  }
});
