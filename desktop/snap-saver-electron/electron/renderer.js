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

let outputDirPrompted = false; // 首次使用引导只弹一次

function applyOutputDir(dir) {
  outputDir = dir;
  if ($("outputDir")) { $("outputDir").value = dir; $("outputDir").title = dir; }
}

async function loadOutputSettings() {
  const r = await window.snapAPI.backend("get_settings");
  if (!r.ok || !r.data?.output_dir) {
    if ($("outputDir")) $("outputDir").value = "读取失败";
    return;
  }
  applyOutputDir(r.data.output_dir);
  if ($("repairKeepOriginal")) $("repairKeepOriginal").checked = Boolean(r.data.keep_original);
  // 首次使用（从没设过存放位置）：主动引导用户选目录，避免截图默默存到找不到的地方。
  if (!r.data.configured && !outputDirPrompted) {
    outputDirPrompted = true;
    await promptFirstRunOutputDir();
  }
}

async function chooseOutputDir(title) {
  const dir = await window.snapAPI.pickFolder({
    title: title || "选择截图和成品的存放位置",
    defaultPath: outputDir || undefined,
  });
  if (!dir) return false;
  const r = await window.snapAPI.backend("set_output_dir", { path: dir });
  if (!r.ok) { alert("设置存放位置失败：" + (r.error || "未知错误")); return false; }
  applyOutputDir(r.data.output_dir);
  return true;
}

async function promptFirstRunOutputDir() {
  // 弹一次系统文件夹选择（标题里说明用途）；取消就用默认并写入配置，下次不再弹。
  const ok = await chooseOutputDir("首次使用：请选择截图和成品的存放位置（之后可在右上角随时更改）");
  if (!ok) await window.snapAPI.backend("set_output_dir", { path: outputDir });
}

$("outputPick")?.addEventListener("click", () => chooseOutputDir("选择截图和成品的存放位置"));

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

// 点击图片只用于「选中」（给 AI 描述用）；勾选「✕ 不导出」用单独的角标 checkbox。
function selectDocImage(image) {
  document.querySelectorAll("#docEditor img.doc-image-selected").forEach((img) => img.classList.remove("doc-image-selected"));
  docSelectedImage = image || null;
  if (image) image.classList.add("doc-image-selected");
  const path = image ? docImagePaths.get(image.getAttribute("src")) : "";
  $("docAiSelected").disabled = !path;
  $("docAiSelling").disabled = !path;
  $("docSelectionHint").textContent = path ? "已选中：" + path.split(/[\\/]/).pop() : "单击图片可选中并生成 AI 描述；单击图片左上角的勾选框可控制是否导出";
}

// 点图片左上角区域 = 切换「是否导出」。被排除的图加 .doc-image-excluded（灰罩+角标），
// 导出时连同其后的说明一起删掉。纯 class 跟着图片走，绝不飘。
function toggleImageExcluded(image) {
  if (!image) return;
  image.classList.toggle("doc-image-excluded");
}

function ensureDocEditor() {
  if (docQuill) return docQuill;
  if (!window.Quill) throw new Error("文档编辑器加载失败，请重启软件。");
  registerProductTable();
  docQuill = new window.Quill("#docEditor", {
    theme: "snow",
    placeholder: "像网页编辑器一样，从这里直接输入和排版……",
    modules: { toolbar: "#docQuillToolbar" },
  });
  docQuill.root.addEventListener("click", (event) => {
    const image = event.target.closest?.("img");
    if (!image) { selectDocImage(null); return; }
    // 点图片左上角「✓ 导出 / ✕ 不导出」徽章区 = 切换是否导出；点别处 = 仅选中。
    // 判定区放大到覆盖整个文字徽章（徽章在图片内 top:0 起、约 70×26），绝不漏点。
    const r = image.getBoundingClientRect();
    const x = event.clientX - r.left;
    const y = event.clientY - r.top;
    if (x >= -6 && x <= 96 && y >= -6 && y <= 48) {
      toggleImageExcluded(image);
    }
    selectDocImage(image); // 任意点击都选中（仅徽章描边，不出大框），便于 AI 描述
  });
  docQuill.root.addEventListener("dblclick", (event) => {
    const image = event.target.closest?.("img");
    const path = image ? docImagePaths.get(image.getAttribute("src")) : "";
    if (path) window.snapAPI.openExternalPath(path);
  });
  return docQuill;
}

function openDoc() {
  $("docModal").style.display = "flex";
  try { ensureDocEditor(); } catch (error) { $("docStatus").textContent = error.message; }
}
function closeDoc() {
  $("docModal").style.display = "none";
}
$("docBtn")?.addEventListener("click", openDoc);
$("docClose")?.addEventListener("click", closeDoc);
$("docMaximize")?.addEventListener("click", () => {
  const m = document.querySelector("#docModal .doc-editor-modal");
  if (m) m.classList.toggle("doc-maximized");
});
$("docModal")?.addEventListener("click", (event) => { if (event.target.id === "docModal") closeDoc(); });

async function insertDocImage(item, atEnd = false, sellingPoint = false) {
  const editor = ensureDocEditor();
  // 编辑器里显示 800px 缩略图（小、快，避免大图 base64 撑爆 DOM 卡死）。
  // 原图路径单独记在 docImagePaths，导出时再换回高清原图。
  let source = "";
  if (item.path) {
    try {
      const t = await window.snapAPI.backend("make_thumb", { path: item.path, max_width: 800 });
      if (t.ok && t.data?.thumb) source = t.data.thumb;
    } catch {}
  }
  if (!source) source = item.thumb || await window.snapAPI.readThumb(item.path);
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
  docQuill.setText("\n"); // 真正空白，靠 placeholder 提示，不再残留「使用说明」
  docImagePaths.clear();
  docSelectedImage = null;
  $("docAiSelected").disabled = true;
  $("docAiSelling").disabled = true;
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
  const title = editor.getText().split("\n").find((line) => line.trim())?.trim() || "详情页";

  // 导出前：在 HTML 副本上操作，不动编辑器本身（编辑器继续用缩略图保持流畅）。
  const exportRoot = editor.root.cloneNode(true);

  // ① 删掉用户「取消勾选 / 标记不导出」的图：连同图所在段、以及紧随其后的说明段一起移除。
  exportRoot.querySelectorAll("img.doc-image-excluded").forEach((img) => {
    const block = img.closest("p, div, li") || img;
    const next = block.nextElementSibling; // 图后面那段说明
    if (next && /^(blockquote|p)$/i.test(next.tagName) && !next.querySelector("img")) next.remove();
    block.remove();
  });

  // ② 删掉用户没填的占位说明（如「在这里输入图片说明……」），避免原样印进成品。
  const placeholders = ["在这里输入图片说明……", "在这里输入商品卖点……", "在这里输入图片说明…", "在这里输入商品卖点…"];
  exportRoot.querySelectorAll("blockquote, p").forEach((el) => {
    if (el.querySelector("img")) return;
    if (placeholders.includes(el.textContent.trim())) el.remove();
  });

  // ③ 把剩下的「800px 缩略图」换回「原图高清」，保证成品清晰。
  const imgs = Array.from(exportRoot.querySelectorAll("img"));
  for (const img of imgs) {
    const thumbSrc = img.getAttribute("src");
    const fullPath = docImagePaths.get(thumbSrc);
    if (!fullPath) continue;
    try {
      const r = await window.snapAPI.backend("read_full_image", { path: fullPath });
      if (r.ok && r.data?.data) img.setAttribute("src", r.data.data);
    } catch {}
  }

  const result = await window.snapAPI.exportRichDoc({
    html: exportRoot.innerHTML,
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
let repairImgs = [];      // [{path, name, thumb, sel, order, status}]
let repairOutDir = "";
let repairOutputs = [];
let repairSourceDir = "";
let repairRefreshTimer = null;
let repairRefreshBusy = false;
let repairRunning = false;

// 勾选顺序：order=0 未选；>0 是第几个勾选的（合成组合图时第 1 个=主图）。sel 与 order>0 保持一致。
function maxRepairOrder() {
  return repairImgs.reduce((m, x) => Math.max(m, x.order || 0), 0);
}
function renumberRepairOrders() {
  repairImgs.filter((x) => x.order > 0).sort((a, b) => a.order - b.order)
    .forEach((x, i) => { x.order = i + 1; });
}
function toggleRepairSel(im) {
  if (im.order > 0) { im.order = 0; im.sel = false; renumberRepairOrders(); }
  else { im.order = maxRepairOrder() + 1; im.sel = true; }
}
function repairSelectedOrdered() {
  return repairImgs.filter((x) => x.order > 0).sort((a, b) => a.order - b.order);
}

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
        order: old && !fingerprintChanged ? (old.order || 0) : 0,
        status: old && !fingerprintChanged ? old.status : "",
        error: old && !fingerprintChanged ? old.error : "",
      });
    }
    repairImgs = next;
    renumberRepairOrders(); // 图片增删后让勾选序号保持连续 1..k
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
  // 单图场景主图：只处理 1 张，避免多图组合链路。
  if ($("repairScene")) $("repairScene").disabled = repairRunning || selCount !== 1;
  if ($("repairPoster")) $("repairPoster").disabled = repairRunning || selCount < 2;
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
      <div class="rc-check">${im.order ? im.order : ""}</div>${statusTag}
      <img class="rc-img" src="${im.thumb || ""}" alt="" />
      <div class="rc-name">${escapeHtml(im.name)}</div>${errorText}`;
    card.addEventListener("click", () => { toggleRepairSel(im); renderRepairGrid(); });
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

$("repairSelAll")?.addEventListener("click", () => { repairImgs.forEach((x, i) => { x.sel = true; x.order = i + 1; }); renderRepairGrid(); });
$("repairSelNone")?.addEventListener("click", () => { repairImgs.forEach((x) => { x.sel = false; x.order = 0; }); renderRepairGrid(); });

// AI 商品主视觉：单张商品图交给 AI，重新生成一张全新电商图。
let sceneGenerating = false;
let sceneResultPath = "";
let sceneMode = "main";      // "main"=场景主图 | "poster"=组合海报

function sceneOutputSubdir() {
  const base = String(outputDir || "").replace(/[\\\/]+$/, "");
  if (!base) return "";
  const sep = base.includes("\\") ? "\\" : "/";
  return `${base}${sep}${sceneMode === "poster" ? "组合图" : "AI主视觉"}`;
}

function posterIsAI() { return sceneMode === "poster" && $("posterMethod")?.value === "ai"; }
function sceneUsesAI() { return sceneMode === "main" || posterIsAI(); }

// 按模式/做法 显示对应控件：AI 路径才显示用途/风格/强度/留白；海报才显示做法。
function applySceneMode() {
  document.querySelectorAll(".scene-mode-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === sceneMode));
  const isPoster = sceneMode === "poster";
  const usesAI = sceneUsesAI();
  document.querySelectorAll(".scene-only-poster").forEach((el) => { el.style.display = isPoster ? "" : "none"; });
  document.querySelectorAll(".scene-only-ai").forEach((el) => { el.style.display = usesAI ? "" : "none"; });
  $("sceneTip").style.display = sceneMode === "main" ? "" : "none";
  $("sceneTitle").textContent = isPoster ? "组合海报" : "AI 场景主图";
  if (sceneMode === "main") $("sceneUsage").value = "main";
  else if ($("sceneUsage").value === "main") $("sceneUsage").value = "poster";
}

document.querySelectorAll(".scene-mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => { sceneMode = btn.dataset.mode; applySceneMode(); });
});
$("posterMethod")?.addEventListener("change", applySceneMode);

function openSceneModal(mode) {
  const chosen = repairSelectedOrdered();
  if (mode === "poster") {
    $("repairStatus").textContent = "组合海报功能已暂停；请勾选 1 张图生成 AI 场景主图。";
    return;
  }
  if (chosen.length !== 1) {
    $("repairStatus").textContent = "请只勾选 1 张干净 / 白底商品图来生成 AI 场景主图。";
    return;
  }
  const min = mode === "poster" ? 2 : 1;
  if (chosen.length < min) {
    $("repairStatus").textContent = mode === "poster"
      ? "请至少勾选 2 张白底图来组合海报（按勾选顺序，第 1 张为主图）。"
      : "请至少勾选 1 张干净 / 白底商品图。";
    return;
  }
  sceneMode = mode;
  applySceneMode();
  $("sceneIntro").textContent = mode === "poster"
    ? `已选 ${chosen.length} 张（第 1 张「${chosen[0].name}」为主图）。组合成一张海报，可选比例。`
    : `已选「${chosen[0].name}」。AI 会锁定商品特征，重画一张全新的电商场景主图。`;
  $("sceneResult").style.display = "none";
  $("sceneResultImg").src = "";
  $("sceneOpen").style.display = "none";
  $("sceneOpen").title = "";
  $("sceneOverlay").style.display = "none";
  $("sceneOverlay").open = false;
  $("sceneStatus").textContent = "";
  sceneResultPath = "";
  $("sceneModal").style.display = "flex";
}
$("repairScene")?.addEventListener("click", () => openSceneModal("main"));
$("repairPoster")?.addEventListener("click", () => openSceneModal("poster"));

// 出图成功后统一展示结果并打开「文案/角标」叠加区。
function showSceneResult(path, statusText) {
  sceneResultPath = path;
  window.snapAPI.readThumb(path).then((thumb) => {
    if (thumb) { $("sceneResultImg").src = thumb; $("sceneResult").style.display = "block"; }
  });
  $("sceneOpen").style.display = "inline-flex";
  $("sceneOpen").title = path;
  $("sceneOverlay").style.display = "block";
  if (statusText) $("sceneStatus").textContent = statusText;
}

function closeScene() { if (!sceneGenerating) $("sceneModal").style.display = "none"; }
$("sceneClose")?.addEventListener("click", closeScene);
$("sceneModal")?.addEventListener("click", (e) => { if (e.target.id === "sceneModal") closeScene(); });

$("sceneOpen")?.addEventListener("click", async () => {
  if (!sceneResultPath) return;
  const r = await window.snapAPI.openExternalPath(sceneResultPath);
  if (!r.ok) $("sceneStatus").textContent = "打开失败：" + (r.error || "");
});

$("sceneGenerate")?.addEventListener("click", async () => {
  if (sceneGenerating) return;
  const chosen = repairSelectedOrdered();
  if (sceneMode !== "poster" && chosen.length !== 1) {
    $("sceneStatus").textContent = "请只勾选 1 张图生成场景主图。";
    return;
  }
  const min = sceneMode === "poster" ? 2 : 1;
  if (chosen.length < min) { $("sceneStatus").textContent = `请至少勾选 ${min} 张图。`; return; }
  sceneGenerating = true;
  $("sceneGenerate").disabled = true;
  $("sceneClose").disabled = true;
  $("sceneResult").style.display = "none";
  $("sceneOpen").style.display = "none";
  $("sceneOpen").title = "";
  $("sceneOverlay").style.display = "none";
  sceneResultPath = "";

  // 本地拼图：不调 AI、不扣额度，直接合成。
  if (sceneMode === "poster" && !posterIsAI()) {
    $("sceneStatus").textContent = "正在本地合成海报……";
    try {
      const r = await window.snapAPI.backend("compose_images", {
        paths: chosen.map((x) => x.path), ratio: $("sceneRatio").value, out_dir: outputDir,
      });
      if (!r.ok) { $("sceneStatus").textContent = "合成失败：" + (r.error || "未知错误"); return; }
      showSceneResult(r.data.path, "已合成：" + r.data.path);
    } catch (e) {
      $("sceneStatus").textContent = "合成失败：" + e.message;
    } finally {
      sceneGenerating = false;
      $("sceneGenerate").disabled = false;
      $("sceneClose").disabled = false;
    }
    return;
  }

  // AI 路径（场景主图 / AI 海报）：服务端分析+生成，这里轮播阶段文案。
  const stages = ["正在分析参考图、锁定商品特征……", "正在重新设计电商场景并生成……", "正在出图，请稍候（高峰期可能 1-5 分钟）……"];
  let si = 0;
  $("sceneStatus").textContent = stages[0];
  const timer = setInterval(() => { si = Math.min(si + 1, stages.length - 1); $("sceneStatus").textContent = stages[si]; }, 12000);
  try {
    const r = await window.snapAPI.backend("reconstruct_scene", {
      paths: [chosen[0].path],
      ratio: $("sceneRatio").value,
      usage: $("sceneUsage").value,
      style: $("sceneStyle").value, strength: $("sceneStrength").value,
      copy_space: $("sceneCopySpace").checked, extra: $("sceneExtra").value.trim(),
      out_dir: outputDir,
    });
    clearInterval(timer);
    if (!r.ok) { $("sceneStatus").textContent = "生成失败：" + (r.error || "未知错误"); return; }
    showSceneResult(r.data.path, "已生成：" + r.data.path);
  } catch (e) {
    clearInterval(timer);
    if (String(e.message || "").includes("请求超时")) {
      const dir = sceneOutputSubdir();
      sceneResultPath = outputDir || dir;
      if (sceneResultPath) {
        $("sceneOpen").style.display = "inline-flex";
        $("sceneOpen").title = "打开输出目录";
      }
      $("sceneStatus").textContent = dir
        ? `界面等待超时，但后台可能仍在生成；如果已完成，会保存到：${dir}`
        : "界面等待超时，但后台可能仍在生成；请稍后到输出目录查看。";
    } else {
      $("sceneStatus").textContent = "生成失败：" + e.message;
    }
  } finally {
    sceneGenerating = false;
    $("sceneGenerate").disabled = false;
    $("sceneClose").disabled = false;
  }
});

// 文案 / 角标：在已出图上本地叠加，生成成品图（不调 AI、不扣额度）。
$("ovApply")?.addEventListener("click", async () => {
  if (!sceneResultPath || sceneGenerating) return;
  const copyText = $("ovCopyText").value.trim();
  const badgeText = $("ovBadgeText").value.trim();
  if (!copyText && !badgeText) { $("sceneStatus").textContent = "请先填文案或角标文字。"; return; }
  $("ovApply").disabled = true;
  $("sceneStatus").textContent = "正在叠加文案 / 角标……";
  try {
    const r = await window.snapAPI.backend("overlay_text_badge", {
      path: sceneResultPath, out_dir: outputDir,
      copy: { text: copyText, position: $("ovCopyPos").value, size: $("ovCopySize").value,
              color: $("ovCopyColor").value, stroke: $("ovCopyStroke").checked },
      badge: { text: badgeText, corner: $("ovBadgeCorner").value, color: $("ovBadgeColor").value },
    });
    if (!r.ok) { $("sceneStatus").textContent = "叠加失败：" + (r.error || "未知错误"); return; }
    showSceneResult(r.data.path, "已出成品图：" + r.data.path);
  } catch (e) {
    $("sceneStatus").textContent = "叠加失败：" + e.message;
  } finally {
    $("ovApply").disabled = false;
  }
});

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
