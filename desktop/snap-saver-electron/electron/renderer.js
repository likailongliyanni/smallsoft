// 界面逻辑：通过 window.snapAPI 调 Python 后端干活。

const $ = (id) => document.getElementById(id);
let outputDir = "";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[ch]);

function setBadge(text, ok) {
  const b = $("statusBadge");
  if (!b) return;
  b.textContent = text;
  b.className = "badge " + (ok ? "badge-ok" : "badge-warn");
}

function setQuota(q) {
  if (!q) return;
  if ($("quotaNum")) $("quotaNum").textContent = String(q.available ?? 0);
}

// 启动：拉真实软件编号 + 登记拿额度
async function init() {
  setBadge("连接中…", true);
  await loadOutputSettings();
  try {
    const r = await window.snapAPI.backend("get_serial");
    if (r.ok && r.data?.serial && $("serial")) $("serial").textContent = r.data.serial;
  } catch {}

  try {
    const r = await window.snapAPI.backend("register");
    if (r.ok) {
      if (r.data?.serial && $("serial")) $("serial").textContent = r.data.serial;
      setQuota(r.data?.quota);
      setBadge("● 已就绪", true);
    } else {
      setBadge("● 离线", false);
    }
  } catch {
    setBadge("● 离线", false);
  }
}

async function loadOutputSettings() {
  const r = await window.snapAPI.backend("get_settings");
  if (!r.ok || !r.data?.output_dir) {
    if ($("outputDir")) $("outputDir").value = "读取失败";
    return;
  }
  outputDir = r.data.output_dir;
  if ($("repairKeepOriginal")) $("repairKeepOriginal").checked = Boolean(r.data.keep_original);
  if ($("outputDir")) {
    $("outputDir").value = outputDir;
    $("outputDir").title = outputDir;
  }
}

$("outputPick")?.addEventListener("click", async () => {
  const dir = await window.snapAPI.pickFolder({
    title: "选择截图和文档的输出目录",
    defaultPath: outputDir || undefined,
  });
  if (!dir) return;
  const r = await window.snapAPI.backend("set_output_dir", { path: dir });
  if (!r.ok) {
    alert("设置输出目录失败：" + (r.error || "未知错误"));
    return;
  }
  outputDir = r.data.output_dir;
  $("outputDir").value = outputDir;
  $("outputDir").title = outputDir;
});

$("outputOpen")?.addEventListener("click", async () => {
  if (!outputDir) await loadOutputSettings();
  const r = await window.snapAPI.openExternalPath(outputDir);
  if (!r.ok) alert("打开目录失败：" + (r.error || "未知错误"));
});

// 复制软件编号
$("copySerial")?.addEventListener("click", async () => {
  const serial = $("serial")?.textContent.trim() || "";
  await window.snapAPI.copy(serial);
  const btn = $("copySerial");
  btn.title = "已复制：" + serial;
  btn.classList.add("flash-ok");
  setTimeout(() => btn.classList.remove("flash-ok"), 600);
});

// 同步额度
$("syncBtn")?.addEventListener("click", async () => {
  const btn = $("syncBtn");
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = old.replace("同步额度", "同步中…");
  try {
    const r = await window.snapAPI.backend("sync_quota");
    if (r.ok) {
      setQuota(r.data?.quota);
      setBadge("● 已就绪", true);
    } else {
      setBadge("● 同步失败", false);
    }
  } catch {
    setBadge("● 同步失败", false);
  } finally {
    btn.disabled = false;
    btn.innerHTML = old;
  }
});

// ───────────────────────── 所见即所得文档编辑器 ─────────────────────────
let docQuill = null;
let docSelectedImage = null;
const docImagePaths = new Map(); // dataURL -> 原图路径
let productTableRegistered = false;
let docImageResizer = null;

function registerProductTable() {
  if (productTableRegistered) return;
  const BlockEmbed = window.Quill.import("blots/block/embed");
  class ProductTableBlot extends BlockEmbed {
    static blotName = "productTable";
    static tagName = "div";
    static className = "product-params-block";

    static create(value) {
      const node = super.create();
      node.setAttribute("contenteditable", "false");
      const table = document.createElement("table");
      table.className = "product-params-table";
      const body = document.createElement("tbody");
      for (const item of Array.isArray(value) ? value : []) {
        const row = document.createElement("tr");
        const name = document.createElement("th");
        const val = document.createElement("td");
        name.textContent = String(item?.name || "");
        val.textContent = String(item?.value || "");
        row.append(name, val);
        body.appendChild(row);
      }
      table.appendChild(body);
      node.appendChild(table);
      return node;
    }

    static value(node) {
      return Array.from(node.querySelectorAll("tr")).map((row) => ({
        name: row.querySelector("th")?.textContent || "",
        value: row.querySelector("td")?.textContent || "",
      }));
    }
  }
  window.Quill.register(ProductTableBlot);
  productTableRegistered = true;
}

function updateImageResizer() {
  if (!docImageResizer || !docSelectedImage || !docSelectedImage.isConnected || $("docModal")?.style.display === "none") {
    docImageResizer?.classList.remove("is-visible");
    return;
  }
  const rect = docSelectedImage.getBoundingClientRect();
  docImageResizer.style.left = String(rect.left) + "px";
  docImageResizer.style.top = String(rect.top) + "px";
  docImageResizer.style.width = String(rect.width) + "px";
  docImageResizer.style.height = String(rect.height) + "px";
  docImageResizer.classList.add("is-visible");
}

function ensureImageResizer() {
  if (docImageResizer) return;
  docImageResizer = document.createElement("div");
  docImageResizer.className = "doc-image-resizer";
  const handle = document.createElement("span");
  handle.className = "doc-image-resizer-handle";
  handle.title = "拖动调整图片大小";
  docImageResizer.appendChild(handle);
  document.body.appendChild(docImageResizer);
  handle.addEventListener("pointerdown", (event) => {
    if (!docSelectedImage) return;
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = docSelectedImage.getBoundingClientRect().width;
    const maxWidth = docQuill?.root.clientWidth || startWidth;
    handle.setPointerCapture?.(event.pointerId);
    const move = (moveEvent) => {
      const width = Math.max(120, Math.min(maxWidth, startWidth + moveEvent.clientX - startX));
      docSelectedImage.style.width = String(Math.round(width)) + "px";
      docSelectedImage.style.height = "auto";
      updateImageResizer();
    };
    const done = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", done);
      handle.removeEventListener("pointercancel", done);
      updateImageResizer();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", done);
    handle.addEventListener("pointercancel", done);
  });
  $("docModal")?.querySelector(".doc-editor-stage")?.addEventListener("scroll", updateImageResizer, { passive: true });
  window.addEventListener("resize", updateImageResizer);
}

function selectDocImage(image) {
  document.querySelectorAll("#docEditor img.doc-image-selected").forEach((img) => img.classList.remove("doc-image-selected"));
  docSelectedImage = image || null;
  if (image) image.classList.add("doc-image-selected");
  const path = image ? docImagePaths.get(image.getAttribute("src")) : "";
  $("docAiSelected").disabled = !path;
  $("docAiSelling").disabled = !path;
  $("docSelectionHint").textContent = path ? "已选中：" + path.split(/[\\/]/).pop() : "单击编辑器中的图片后可生成 AI 描述";
  updateImageResizer();
}

function ensureDocEditor() {
  if (docQuill) return docQuill;
  if (!window.Quill) throw new Error("文档编辑器加载失败，请重启软件。");
  registerProductTable();
  ensureImageResizer();
  docQuill = new window.Quill("#docEditor", {
    theme: "snow",
    placeholder: "像网页编辑器一样，从这里直接输入和排版……",
    modules: { toolbar: "#docQuillToolbar" },
  });
  docQuill.setText("使用说明\n从这里开始编辑正文，或点击上方按钮导入截图。\n");
  docQuill.formatLine(0, 1, "header", 1);
  docQuill.root.addEventListener("click", (event) => {
    const image = event.target.closest?.("img");
    selectDocImage(image);
  });
  docQuill.root.addEventListener("dblclick", (event) => {
    const image = event.target.closest?.("img");
    const path = image ? docImagePaths.get(image.getAttribute("src")) : "";
    if (path) window.snapAPI.openExternalPath(path);
  });
  docQuill.on("text-change", () => setTimeout(updateImageResizer));
  return docQuill;
}

function openDoc() {
  $("docModal").style.display = "flex";
  try { ensureDocEditor(); } catch (error) { $("docStatus").textContent = error.message; }
}
function closeDoc() {
  $("docModal").style.display = "none";
  docImageResizer?.classList.remove("is-visible");
}
$("docBtn")?.addEventListener("click", openDoc);
$("docClose")?.addEventListener("click", closeDoc);
$("docMaximize")?.addEventListener("click", () => {
  const m = document.querySelector("#docModal .doc-editor-modal");
  if (m) {
    m.classList.toggle("doc-maximized");
    setTimeout(updateImageResizer);
  }
});
$("docModal")?.addEventListener("click", (event) => { if (event.target.id === "docModal") closeDoc(); });

async function insertDocImage(item, atEnd = false, sellingPoint = false) {
  const editor = ensureDocEditor();
  const source = item.thumb || await window.snapAPI.readThumb(item.path);
  if (!source) return false;
  docImagePaths.set(source, item.path);
  // atEnd=true（批量导入）：每张都追加到文档末尾，保证「图→说明→图→说明」严格交替，
  // 不依赖 getSelection（批量时光标时序不稳，会导致图堆在一起、说明全挤到后面）。
  let index;
  if (atEnd) {
    index = editor.getLength() - 1;
  } else {
    const range = editor.getSelection(true) || { index: editor.getLength() - 1, length: 0 };
    index = range.index;
  }
  editor.insertEmbed(index, "image", source, "user");
  if (sellingPoint) {
    const inserted = Array.from(editor.root.querySelectorAll("img"))
      .reverse().find((image) => image.getAttribute("src") === source);
    inserted?.classList.add("selling-point-image");
  }
  editor.insertText(index + 1, sellingPoint ? "\n在这里输入商品卖点……\n" : "\n在这里输入图片说明……\n", "user");
  editor.formatLine(index + 2, 1, "blockquote", true, "user");
  editor.setSelection(index + 3, 0, "silent");
  return true;
}

$("docAddImg")?.addEventListener("click", async () => {
  const dir = await window.snapAPI.pickFolder({ title: "选择要插入文档的图片文件夹" });
  if (!dir) return;
  $("docStatus").textContent = "正在导入图片……";
  const result = await window.snapAPI.backend("list_folder_images", { dir });
  const images = result.ok ? result.data?.images || [] : [];
  if (!images.length) { $("docStatus").textContent = result.error || "该文件夹里没有图片。"; return; }
  let added = 0;
  for (const image of images) if (await insertDocImage(image, true)) added++;
  $("docStatus").textContent = `已插入 ${added} 张图片，可直接编辑标题和说明。`;
});

$("docAddSession")?.addEventListener("click", async () => {
  if (!shots.length) { $("docStatus").textContent = "本轮还没有截图。"; return; }
  $("docStatus").textContent = "正在导入本轮截图……";
  let added = 0;
  for (const shot of [...shots].reverse()) if (await insertDocImage(shot, true)) added++;
  $("docStatus").textContent = `已插入本轮 ${added} 张截图。`;
});

async function describeSelectedImage(style, button, originalLabel) {
  if (!docQuill || !docSelectedImage) return;
  const image = docSelectedImage;
  const path = docImagePaths.get(image.getAttribute("src"));
  if (!path) return;
  button.disabled = true;
  button.textContent = "AI 生成中……";
  $("docStatus").textContent = style === "marketing" ? "正在提炼商品卖点……" : "正在理解选中的图片……";
  try {
    const result = await window.snapAPI.backend("describe_image", { path, hint: "", style });
    if (!result.ok || !result.data?.description) throw new Error(result.error || "没有生成描述");
    if (!image.isConnected) throw new Error("图片已从文档中移除");
    if (style === "marketing") image.classList.add("selling-point-image");
    const blot = window.Quill.find(image);
    const index = docQuill.getIndex(blot) + 1;
    for (const placeholder of ["\n在这里输入图片说明……\n", "\n在这里输入商品卖点……\n"]) {
      if (docQuill.getText(index, placeholder.length) === placeholder) {
        docQuill.deleteText(index, placeholder.length, "user");
        break;
      }
    }
    docQuill.insertText(index, "\n" + result.data.description + "\n", "user");
    docQuill.formatLine(index + 1, 1, "blockquote", true, "user");
    $("docStatus").textContent = style === "marketing" ? "AI 卖点已插入图片下方，可继续修改。" : "AI 描述已插入图片下方，可继续修改。";
  } catch (error) {
    $("docStatus").textContent = "AI 描述失败：" + error.message;
  } finally {
    button.disabled = !docSelectedImage;
    button.textContent = originalLabel;
  }
}

$("docAiSelected")?.addEventListener("click", () => {
  describeSelectedImage("detail", $("docAiSelected"), "AI 描述选中图片");
});
$("docAiSelling")?.addEventListener("click", () => {
  describeSelectedImage("marketing", $("docAiSelling"), "AI 卖点描述");
});

$("docAddSelling")?.addEventListener("click", async () => {
  const dir = await window.snapAPI.pickFolder({ title: "选择白底商品图文件夹" });
  if (!dir) return;
  $("docStatus").textContent = "正在导入商品卖点图……";
  const result = await window.snapAPI.backend("list_folder_images", { dir });
  const images = result.ok ? result.data?.images || [] : [];
  if (!images.length) {
    $("docStatus").textContent = result.error || "该文件夹里没有图片。";
    return;
  }
  const editor = ensureDocEditor();
  const headingIndex = editor.getLength() - 1;
  editor.insertText(headingIndex, "商品卖点\n", "user");
  editor.formatLine(headingIndex, 1, "header", 2, "user");
  let added = 0;
  for (const image of images) if (await insertDocImage(image, true, true)) added++;
  $("docStatus").textContent = "已插入 " + String(added) + " 张卖点图；选中图片可生成 AI 卖点描述。";
});

function addProductParamRow(name = "", value = "") {
  const row = document.createElement("div");
  row.className = "product-param-row";
  const nameInput = document.createElement("input");
  nameInput.placeholder = "参数名，如材质";
  nameInput.value = name;
  nameInput.dataset.role = "name";
  const valueInput = document.createElement("input");
  valueInput.placeholder = "参数值";
  valueInput.value = value;
  valueInput.dataset.role = "value";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "btn product-param-remove";
  remove.textContent = "×";
  remove.title = "删除此行";
  remove.addEventListener("click", () => row.remove());
  row.append(nameInput, valueInput, remove);
  $("productParamRows").appendChild(row);
}

function currentProductParams() {
  return Array.from($("productParamRows").querySelectorAll(".product-param-row"))
    .map((row) => ({
      name: row.querySelector('[data-role="name"]').value.trim(),
      value: row.querySelector('[data-role="value"]').value.trim(),
    }))
    .filter((item) => item.name && item.value);
}

$("docToggleParams")?.addEventListener("click", () => {
  const panel = $("productParamPanel");
  const opening = panel.style.display === "none";
  panel.style.display = opening ? "block" : "none";
  if (opening && !$("productParamRows").children.length) {
    addProductParamRow("材质", "");
    addProductParamRow("颜色", "");
    addProductParamRow("尺寸", "");
  }
});
$("productAddRow")?.addEventListener("click", () => addProductParamRow());

$("productAiParams")?.addEventListener("click", async () => {
  const text = $("productSentence").value.trim();
  if (!text) {
    $("docStatus").textContent = "请先输入一句商品介绍。";
    return;
  }
  const button = $("productAiParams");
  button.disabled = true;
  button.textContent = "AI 生成中……";
  $("docStatus").textContent = "正在整理商品参数……";
  try {
    const result = await window.snapAPI.backend("generate_product_params", { text });
    if (!result.ok || !result.data?.params?.length) throw new Error(result.error || "没有识别到参数");
    $("productParamRows").innerHTML = "";
    for (const item of result.data.params) addProductParamRow(item.name, item.value);
    const title = String(result.data.title || "").trim();
    const editor = ensureDocEditor();
    const firstLine = editor.getText().split("\n")[0];
    if (title && (!firstLine.trim() || firstLine === "使用说明")) {
      editor.deleteText(0, firstLine.length, "user");
      editor.insertText(0, title, "user");
      editor.formatLine(0, 1, "header", 1, "user");
    }
    $("docStatus").textContent = "AI 已生成参数，请检查后插入文档。";
  } catch (error) {
    $("docStatus").textContent = "参数生成失败：" + error.message;
  } finally {
    button.disabled = false;
    button.textContent = "AI 生成参数";
  }
});

$("productInsertTable")?.addEventListener("click", () => {
  const params = currentProductParams();
  if (!params.length) {
    $("docStatus").textContent = "请至少填写一行完整参数。";
    return;
  }
  const editor = ensureDocEditor();
  const existing = editor.root.querySelector(".product-params-block");
  let index;
  if (existing) {
    const blot = window.Quill.find(existing);
    index = editor.getIndex(blot);
    editor.deleteText(index, 1, "user");
  } else {
    const firstBreak = editor.getText().indexOf("\n");
    const headingIndex = firstBreak >= 0 ? firstBreak + 1 : 0;
    editor.insertText(headingIndex, "商品参数\n", "user");
    editor.formatLine(headingIndex, 1, "header", 2, "user");
    index = headingIndex + "商品参数\n".length;
  }
  editor.insertEmbed(index, "productTable", params, "user");
  editor.insertText(index + 1, "\n", "user");
  $("docStatus").textContent = existing ? "商品参数表已更新。" : "商品参数表已插入文档顶部。";
});

$("docClear")?.addEventListener("click", () => {
  if (!docQuill || !confirm("确定清空当前文档并新建空白文档吗？")) return;
  docQuill.setText("使用说明\n");
  docQuill.formatLine(0, 1, "header", 1);
  docImagePaths.clear();
  docSelectedImage = null;
  $("docAiSelected").disabled = true;
  $("docAiSelling").disabled = true;
  updateImageResizer();
  $("docStatus").textContent = "已新建空白文档。";
});

$("docOrientation")?.addEventListener("change", () => {
  $("docEditor").classList.toggle("landscape", $("docOrientation").value === "landscape");
});
$("docTheme")?.addEventListener("change", () => {
  $("docEditor").classList.toggle("theme-green", $("docTheme").value === "green");
});

async function docExport(format) {
  const editor = ensureDocEditor();
  if (!editor.getText().trim() && !editor.root.querySelector("img")) {
    $("docStatus").textContent = "文档还是空的。";
    return;
  }
  $("docStatus").textContent = format === "pdf"
    ? "正在生成 A4 PDF……"
    : format === "segments" ? "正在按内容块生成分段图……" : "正在生成长图……";
  const title = editor.getText().split("\n").find((line) => line.trim())?.trim() || "使用说明";
  const result = await window.snapAPI.exportRichDoc({
    html: editor.root.innerHTML,
    title,
    format,
    orientation: $("docOrientation").value,
    theme: $("docTheme").value,
    outDir: outputDir,
  });
  if (!result.ok) { $("docStatus").textContent = "导出失败：" + result.error; return; }
  const target = format === "segments" ? result.dir : result.path;
  $("docStatus").textContent = format === "segments"
    ? "已导出 " + String(result.paths?.length || 0) + " 张分段图：" + result.dir
    : "已导出：" + result.path;
  const opened = await window.snapAPI.openExternalPath(target);
  if (!opened.ok) $("docStatus").textContent += "；自动打开失败：" + opened.error;
}
$("docExportPdf")?.addEventListener("click", () => docExport("pdf").catch((e) => { $("docStatus").textContent = "导出失败：" + e.message; }));
$("docExportLong")?.addEventListener("click", () => docExport("long").catch((e) => { $("docStatus").textContent = "导出失败：" + e.message; }));
$("docExportSegments")?.addEventListener("click", () => docExport("segments").catch((e) => { $("docStatus").textContent = "导出失败：" + e.message; }));

// 「导入图片」仍进入 AI 修复流程。
$("importBtn")?.addEventListener("click", async () => {
  await openRepair();
  $("repairPick")?.click();
});

// ───────────────────────── AI 智能修复（选文件夹 + 勾选 + 批量）─────────────────────────
let repairImgs = [];      // [{path, name, thumb, sel, status}]
let repairOutDir = "";
let repairOutputs = [];
let repairSourceDir = "";
let repairRefreshTimer = null;
let repairRefreshBusy = false;
let repairRunning = false;

function stopRepairAutoRefresh() {
  if (repairRefreshTimer) clearTimeout(repairRefreshTimer);
  repairRefreshTimer = null;
}

function startRepairAutoRefresh() {
  stopRepairAutoRefresh();
  if (!repairSourceDir || $("repairModal").style.display === "none") return;
  repairRefreshTimer = setTimeout(async () => {
    await refreshRepairFolder(false);
    startRepairAutoRefresh();
  }, 1600);
}

async function refreshRepairFolder(initial = false) {
  if (!repairSourceDir || repairRefreshBusy || repairRunning) return;
  repairRefreshBusy = true;
  try {
    const r = await window.snapAPI.backend("list_folder_images", { dir: repairSourceDir });
    if (!r.ok) {
      if (initial) $("repairStatus").textContent = "读取文件夹失败：" + (r.error || "未知错误");
      return;
    }
    const images = r.data?.images || [];
    const previous = new Map(repairImgs.map((item) => [item.path, item]));
    const next = [];
    let changed = images.length !== repairImgs.length;
    for (const meta of images) {
      const old = previous.get(meta.path);
      const fingerprintChanged = Boolean(old)
        && (old.mtime_ns !== meta.mtime_ns || old.size !== meta.size);
      if (!old || fingerprintChanged) changed = true;
      const thumb = !old || fingerprintChanged
        ? await window.snapAPI.readThumb(meta.path)
        : old.thumb;
      next.push({
        path: meta.path, name: meta.name, thumb,
        mtime_ns: meta.mtime_ns, size: meta.size,
        sel: old && !fingerprintChanged ? old.sel : false,
        status: old && !fingerprintChanged ? old.status : "",
        error: old && !fingerprintChanged ? old.error : "",
      });
    }
    repairImgs = next;
    repairOutDir = repairSourceDir;
    repairOutputs = repairOutputs.filter((path) => next.some((item) => item.path === path));
    $("repairOpen").disabled = !repairSourceDir;
    renderRepairGrid();
    if (initial) {
      $("repairStatus").textContent = images.length
        ? "已载入 " + String(images.length) + " 张，目录会自动刷新。为避免误扣额度，默认不选。"
        : "该文件夹暂时没有图片；新增图片后会自动出现。";
    } else if (changed) {
      $("repairStatus").textContent = "目录已自动刷新，当前 " + String(images.length) + " 张图片。";
    }
  } finally {
    repairRefreshBusy = false;
  }
}

async function openRepair() {
  $("repairModal").style.display = "flex";
  const sel = $("repairMode");
  if (sel && !sel.dataset.loaded) {
    try {
      const r = await window.snapAPI.backend("repair_modes");
      if (r.ok && r.data?.modes) {
        sel.innerHTML = r.data.modes.map((m) => `<option value="${m.key}">${m.label}</option>`).join("");
        sel.dataset.loaded = "1";
      }
    } catch {}
  }
  if (repairSourceDir) await refreshRepairFolder(false);
  startRepairAutoRefresh();
}
function closeRepair() {
  $("repairModal").style.display = "none";
  stopRepairAutoRefresh();
}
$("repairBtn")?.addEventListener("click", openRepair);
$("repairClose")?.addEventListener("click", closeRepair);
$("repairModal")?.addEventListener("click", (e) => { if (e.target.id === "repairModal") closeRepair(); });

function renderRepairGrid() {
  const grid = $("repairGrid");
  const has = repairImgs.length > 0;
  $("repairSelAll").style.display = has ? "inline-flex" : "none";
  $("repairSelNone").style.display = has ? "inline-flex" : "none";
  const selCount = repairImgs.filter((x) => x.sel).length;
  const runnableCount = repairImgs.filter((x) => x.sel && x.status !== "done").length;
  $("repairPickCount").textContent = has
    ? `共 ${repairImgs.length} 张，选中 ${selCount}${repairSourceDir ? " · 自动刷新" : ""}`
    : (repairSourceDir ? "自动刷新中" : "");
  $("repairRun").disabled = repairRunning || runnableCount === 0;
  if (!has) {
    grid.innerHTML = repairSourceDir
      ? '<div class="doc-empty">当前目录暂无图片；软件正在监控，新增图片后会自动显示。</div>'
      : '<div class="doc-empty">点「选择文件夹」，列出里面所有图片，勾选要处理的，再点「开始修复」批量执行。</div>';
    return;
  }
  grid.innerHTML = "";
  repairImgs.forEach((im, i) => {
    const card = document.createElement("div");
    card.className = "repair-card" + (im.sel ? " sel" : "");
    const statusTag = im.status === "done" ? '<span class="rc-status rc-done">✓ 已修</span>'
      : im.status === "run" ? '<span class="rc-status rc-run">修复中</span>'
      : im.status === "fail" ? '<span class="rc-status rc-fail">失败</span>' : "";
    const errorText = im.status === "fail" && im.error
      ? `<div class="rc-error" title="${escapeHtml(im.error)}">${escapeHtml(im.error)}</div>` : "";
    card.innerHTML = `
      <div class="rc-check">${im.sel ? "✓" : ""}</div>${statusTag}
      <img class="rc-img" src="${im.thumb || ""}" alt="" />
      <div class="rc-name">${escapeHtml(im.name)}</div>${errorText}`;
    card.addEventListener("click", () => { im.sel = !im.sel; renderRepairGrid(); });
    grid.appendChild(card);
  });
}

$("repairPick")?.addEventListener("click", async () => {
  const dir = await window.snapAPI.pickFolder();
  if (!dir) return;
  $("repairStatus").textContent = "正在读取文件夹…";
  repairImgs = [];
  repairOutputs = [];
  repairSourceDir = dir;
  repairOutDir = dir;
  $("repairOpen").disabled = true;
  await refreshRepairFolder(true);
  startRepairAutoRefresh();
});

$("repairKeepOriginal")?.addEventListener("change", async () => {
  const keep = $("repairKeepOriginal").checked;
  const r = await window.snapAPI.backend("set_keep_original", { keep_original: keep });
  if (!r.ok) {
    $("repairKeepOriginal").checked = !keep;
    $("repairStatus").textContent = "保存设置失败：" + (r.error || "未知错误");
  }
});

$("repairSelAll")?.addEventListener("click", () => { repairImgs.forEach((x) => x.sel = true); renderRepairGrid(); });
$("repairSelNone")?.addEventListener("click", () => { repairImgs.forEach((x) => x.sel = false); renderRepairGrid(); });

$("repairRun")?.addEventListener("click", async () => {
  const targets = repairImgs.filter((x) => x.sel && x.status !== "done");
  if (!targets.length) return;
  const keepOriginal = $("repairKeepOriginal").checked;
  const outputHint = keepOriginal
    ? "原图会备份到同目录的 _含水印原图，修复结果替换原位置。"
    : "修复结果会直接替换原图，且不保留备份。";
  if (!confirm(`即将修复 ${targets.length} 张图片，每张成功处理会消耗 1 次额度。\n${outputHint}\n是否继续？`)) return;
  const mode = $("repairMode").value || "watermark";
  repairRunning = true;
  stopRepairAutoRefresh();
  $("repairRun").disabled = true;
  $("repairPick").disabled = true;
  $("repairKeepOriginal").disabled = true;
  let done = 0, fail = 0;
  for (let k = 0; k < targets.length; k++) {
    const im = targets[k];
    im.status = "run"; im.error = ""; renderRepairGrid();
    $("repairStatus").textContent = `修复中 ${k + 1}/${targets.length}：${im.name}`;
    try {
      const r = await window.snapAPI.backend("repair_image", {
        path: im.path, mode, keep_original: keepOriginal,
      });
      if (r.ok && r.data?.out) {
        im.status = "done";
        im.mtime_ns = r.data.mtime_ns;
        im.size = r.data.size;
        im.thumb = await window.snapAPI.readThumb(im.path);
        repairOutDir = r.data.dir || repairOutDir;
        if (!repairOutputs.includes(r.data.out)) repairOutputs.push(r.data.out);
        done++;
      }
      else { im.status = "fail"; im.error = r.error || "后端没有返回修复结果"; fail++; }
    } catch (e) { im.status = "fail"; im.error = e.message || "请求异常"; fail++; }
    renderRepairGrid();
  }
  const firstError = targets.find((x) => x.status === "fail")?.error;
  $("repairStatus").textContent = `完成：成功 ${done}${fail ? "，失败 " + fail : ""}。`
    + (firstError ? `失败原因：${firstError}`
      : keepOriginal ? "原图已备份，修复结果已替换原路径。" : "修复结果已替换原路径。");
  $("repairOpen").disabled = !repairOutDir;
  $("repairPick").disabled = false;
  $("repairKeepOriginal").disabled = false;
  repairRunning = false;
  renderRepairGrid();
  startRepairAutoRefresh();
});

$("repairOpen")?.addEventListener("click", () => {
  const target = repairOutputs.length === 1 ? repairOutputs[0] : repairOutDir;
  if (target) window.snapAPI.openExternalPath(target);
});

// ───────────────────────── 截图 ─────────────────────────
const shots = []; // [{path, name, w, h, thumb}]
let lastShotPath = "";
$("shotOpenLatest")?.addEventListener("click", () => {
  if (lastShotPath) window.snapAPI.openExternalPath(lastShotPath);
});

function renderShots() {
  const list = $("shotList");
  $("shotCount").textContent = "共 " + shots.length + " 张";
  if (shots.length === 0) {
    list.innerHTML = '<div class="doc-empty">点「开始截图」框选屏幕，或「自由截图」连续截图。截好的图会列在这里。</div>';
    return;
  }
  list.innerHTML = "";
  shots.forEach((s) => {
    const row = document.createElement("div");
    row.className = "shot";
    row.innerHTML = `
      <div class="shot-thumb" style="background:#f1f5f3;overflow:hidden">${s.thumb ? `<img src="${s.thumb}" style="width:100%;height:100%;object-fit:cover">` : ""}</div>
      <div class="shot-info"><div class="shot-name">${s.name}</div><div class="shot-meta">${s.w} × ${s.h}</div></div>
      <button class="btn shot-open">打开</button>
      <span class="pill pill-ok">✓ 已保存</span>`;
    row.querySelector(".shot-open").addEventListener("click", () => window.snapAPI.openExternalPath(s.path));
    row.querySelector(".shot-thumb").addEventListener("dblclick", () => window.snapAPI.openExternalPath(s.path));
    list.appendChild(row);
  });
}

// ─────────────────── 电商批量采集 ───────────────────
let collecting = false;

function openCollect() { $("collectModal").style.display = "flex"; }
function closeCollect() { $("collectModal").style.display = "none"; }
$("captureBtn")?.addEventListener("click", openCollect);
$("collectClose")?.addEventListener("click", () => { if (!collecting) closeCollect(); });

// 导入表格文件（Excel/CSV/txt）→ 填到商品列表框
$("collectImport")?.addEventListener("click", async () => {
  const file = await window.snapAPI.pickFile();
  if (!file) return;
  const r = await window.snapAPI.backend("import_rows_file", { path: file });
  if (r.ok && r.data?.rows?.length) {
    $("collectRows").value = r.data.rows.map((x) => `${x.name}\t${x.link}`).join("\n");
    $("collectStatus").textContent = `已导入 ${r.data.rows.length} 行。`;
  } else {
    $("collectStatus").textContent = "导入失败：" + (r.error || "没读到有效行");
  }
});

$("collectStart")?.addEventListener("click", async () => {
  const text = $("collectRows").value.trim();
  if (!text) { $("collectStatus").textContent = "请先粘贴商品名称+链接列表。"; return; }
  // 解析列表
  const pr = await window.snapAPI.backend("parse_rows", { text });
  const rows = (pr.ok && pr.data?.rows) || [];
  if (!rows.length) { $("collectStatus").textContent = "没解析到有效的行。"; return; }
  const mainCount = parseInt($("mainCount").value) || 0;
  const detailCount = parseInt($("detailCount").value) || 0;

  const r = await window.snapAPI.backend("capture_start", {
    rows, main_count: mainCount, detail_count: detailCount, out_dir: outputDir,
  });
  if (!r.ok) { $("collectStatus").textContent = "启动失败：" + (r.error || ""); return; }
  collecting = true;
  lastShotPath = "";
  if ($("taskOpen")) $("taskOpen").disabled = true;
  // 关闭采集弹窗，主界面显示进度视窗（边截边看）
  closeCollect();
  $("taskPanel").style.display = "block";
  setBadge("● 采集中", true);
});

function stopCollect() {
  window.snapAPI.backend("capture_stop");
  collecting = false;
  $("taskPanel").style.display = "none";
  setBadge("● 已就绪", true);
}
$("collectStop")?.addEventListener("click", stopCollect);
$("taskStop")?.addEventListener("click", stopCollect);
$("collectNext")?.addEventListener("click", () => window.snapAPI.backend("capture_next_row"));
$("taskNext")?.addEventListener("click", () => window.snapAPI.backend("capture_next_row"));
$("taskOpen")?.addEventListener("click", () => {
  if (lastShotPath) window.snapAPI.openExternalPath(lastShotPath);
});

// 自由截图：Ctrl 悬停识别窗口，单击截整窗；也可按住 Ctrl 拖框。
let freeOn = false;
$("freeBtn")?.addEventListener("click", async () => {
  if (!freeOn) {
    const r = await window.snapAPI.backend("free_capture_start", { out_dir: outputDir });
    if (!r.ok) { setBadge("● 启用失败", false); alert("自由截图启用失败：" + (r.error || "可能被安全软件拦截")); return; }
    freeOn = true;
    $("freeBtn").classList.add("btn-primary");
    $("freeBtn").lastChild.textContent = " 结束自由截图";
    setBadge("● Ctrl 单击智能区域 / 拖动框选", true);
  } else {
    await window.snapAPI.backend("capture_stop");
    freeOn = false;
    $("freeBtn").classList.remove("btn-primary");
    $("freeBtn").lastChild.textContent = "自由截图";
    setBadge("● 已就绪", true);
  }
});

// 监听后台采集事件 → 更新主界面进度视窗 + 截图列表
window.snapAPI.onPyEvent(async (msg) => {
  if (msg.event === "capture_progress") {
    if ($("taskCur")) $("taskCur").textContent = `第 ${msg.index + 1}/${msg.total} 个：${msg.row_name || ""}（正在截「${msg.category}」）`;
    if ($("taskStat")) $("taskStat").textContent = `主图 ${msg.main_done}/${msg.main_count} · 详情 ${msg.detail_done}/${msg.detail_count}`;
  } else if (msg.event === "capture_saved") {
    let thumb = "";
    try { thumb = await window.snapAPI.readThumb(msg.path); } catch {}
    const label = msg.category ? `${msg.row_name}/${msg.category}/${msg.name}` : msg.name;
    shots.unshift({ path: msg.path, name: label, w: msg.w, h: msg.h, thumb });
    lastShotPath = msg.path;
    if ($("taskOpen")) $("taskOpen").disabled = false;
    if ($("shotOpenLatest")) $("shotOpenLatest").disabled = false;
    renderShots();
  } else if (msg.event === "capture_link_wait") {
    if ($("taskCur")) $("taskCur").textContent = `正在打开第 ${msg.index + 1}/${msg.total} 个：${msg.row_name || ""}`;
    if ($("taskStat")) $("taskStat").textContent = `页面切换中，${msg.delay || 2.5} 秒内已暂停截图，请不要拖框。`;
    setBadge("● 正在切换商品", true);
  } else if (msg.event === "capture_link_ready") {
    if ($("taskCur")) $("taskCur").textContent = `第 ${msg.index + 1}/${msg.total} 个：${msg.row_name || ""}`;
    if ($("taskStat")) $("taskStat").textContent = "新链接已打开，请确认商品页面正确后再截图。";
    setBadge("● 可截图", true);
  } else if (msg.event === "capture_all_done") {
    collecting = false;
    $("taskPanel").style.display = "none";
    setBadge("● 已就绪", true);
    alert("列表已全部截完！可以去「整理成文档」或「AI 智能修复」。");
  } else if (msg.event === "capture_error") {
    setBadge("● 截图出错", false);
    if ($("taskStat")) $("taskStat").textContent = "截图失败：" + (msg.error || "未知错误");
  }
});

window.addEventListener("DOMContentLoaded", () => { init(); renderShots(); });
