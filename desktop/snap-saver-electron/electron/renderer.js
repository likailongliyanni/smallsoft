// 界面逻辑：通过 window.snapAPI 调 Python 后端干活。

const $ = (id) => document.getElementById(id);

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

// ───────────────────────── 整理成文档 ─────────────────────────
const docItems = []; // [{path, name, caption, hint, size, thumb}]
const SIZE_OPTS = [
  ["full", "全宽"], ["two_third", "三分之二"], ["half", "二分之一"], ["quarter", "四分之一"],
];

function openDoc() { $("docModal").style.display = "flex"; renderDocList(); }
function closeDoc() { $("docModal").style.display = "none"; }

$("docBtn")?.addEventListener("click", openDoc);
$("docClose")?.addEventListener("click", closeDoc);
$("docModal")?.addEventListener("click", (e) => { if (e.target.id === "docModal") closeDoc(); });

async function docAddImages() {
  const paths = await window.snapAPI.pickImages();
  for (const p of paths) {
    const thumb = await window.snapAPI.readThumb(p);
    docItems.push({
      path: p, name: p.split(/[\\/]/).pop(), caption: "", hint: "", size: "full", thumb,
    });
  }
  renderDocList();
}
$("docAddImg")?.addEventListener("click", docAddImages);
// 「导入图片」= 打开 AI 修复弹窗并选图（导入图片就是为了修图，职责清晰）
$("importBtn")?.addEventListener("click", async () => {
  await openRepair();
  $("repairPick")?.click();
});

function syncDocFromDOM() {
  document.querySelectorAll(".doc-row").forEach((row, i) => {
    if (!docItems[i]) return;
    const cap = row.querySelector(".doc-caption");
    const hint = row.querySelector(".doc-hintbox");
    const sel = row.querySelector("select");
    if (cap) docItems[i].caption = cap.value;
    if (hint) docItems[i].hint = hint.value;
    if (sel) docItems[i].size = sel.value;
  });
}

function renderDocList() {
  const list = $("docList");
  $("docCount").textContent = "共 " + docItems.length + " 张";
  if (docItems.length === 0) {
    list.innerHTML = '<div class="doc-empty">点「添加图片」选择截图，给每张填说明或用 AI 一键生成，然后导出 PDF / 长图。</div>';
    return;
  }
  list.innerHTML = "";
  docItems.forEach((it, i) => {
    const row = document.createElement("div");
    row.className = "doc-row";
    const opts = SIZE_OPTS.map(([v, t]) =>
      `<option value="${v}" ${it.size === v ? "selected" : ""}>${t}</option>`).join("");
    row.innerHTML = `
      <img class="doc-thumb" src="${it.thumb || ""}" alt="" />
      <div class="doc-col">
        <div class="doc-row-top">
          <span class="doc-seq">${i + 1}</span>
          <button class="btn btn-blue ai-btn"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" transform="translate(3 2)"/></svg>AI 描述</button>
          <span style="font-size:12px;color:var(--hint)">文档宽度</span>
          <select>${opts}</select>
          <span class="spacer"></span>
          <button class="btn up-btn" title="上移">↑</button>
          <button class="btn down-btn" title="下移">↓</button>
          <button class="btn del-btn" title="删除" style="color:#c0392b">✕</button>
        </div>
        <input class="doc-hintbox" placeholder="给 AI 的提示（这张图想表达什么，可选）" value="${(it.hint || "").replace(/"/g, "&quot;")}" />
        <textarea class="doc-caption" placeholder="说明文字（会出现在文档里；可点 AI 描述自动生成）">${it.caption || ""}</textarea>
      </div>`;
    row.querySelector(".ai-btn").addEventListener("click", () => docDescribe(i, row));
    row.querySelector(".up-btn").addEventListener("click", () => { syncDocFromDOM(); if (i > 0) { [docItems[i - 1], docItems[i]] = [docItems[i], docItems[i - 1]]; renderDocList(); } });
    row.querySelector(".down-btn").addEventListener("click", () => { syncDocFromDOM(); if (i < docItems.length - 1) { [docItems[i + 1], docItems[i]] = [docItems[i], docItems[i + 1]]; renderDocList(); } });
    row.querySelector(".del-btn").addEventListener("click", () => { syncDocFromDOM(); docItems.splice(i, 1); renderDocList(); });
    list.appendChild(row);
  });
}

async function docDescribe(i, row) {
  syncDocFromDOM();
  const it = docItems[i];
  const btn = row.querySelector(".ai-btn");
  const old = btn.innerHTML;
  btn.disabled = true; btn.textContent = "生成中…";
  $("docStatus").textContent = "正在为第 " + (i + 1) + " 张生成 AI 描述…";
  try {
    const r = await window.snapAPI.backend("describe_image", { path: it.path, hint: it.hint, style: "detail" });
    if (r.ok && r.data?.description) {
      it.caption = r.data.description;
      row.querySelector(".doc-caption").value = it.caption;
      $("docStatus").textContent = "第 " + (i + 1) + " 张 AI 描述已生成" + (r.data.charged ? "（已扣 1 次）" : "（当前免费）");
    } else {
      $("docStatus").textContent = "AI 描述失败：" + (r.error || "请重试");
    }
  } catch (e) {
    $("docStatus").textContent = "AI 描述失败：" + e.message;
  } finally {
    btn.disabled = false; btn.innerHTML = old;
  }
}

async function docExport(format) {
  syncDocFromDOM();
  if (docItems.length === 0) { $("docStatus").textContent = "请先添加图片。"; return; }
  $("docStatus").textContent = "正在导出…";
  const items = docItems.map((it) => ({ path: it.path, caption: it.caption, size: it.size }));
  try {
    const r = await window.snapAPI.backend("export_doc", {
      title: $("docTitle").value, intro: $("docIntro").value,
      format, watermark: true, items,
    });
    if (r.ok) {
      $("docStatus").textContent = "已导出：" + r.data.path;
      window.snapAPI.backend("open_path", { path: r.data.dir });
    } else {
      $("docStatus").textContent = "导出失败：" + (r.error || "");
    }
  } catch (e) {
    $("docStatus").textContent = "导出失败：" + e.message;
  }
}
$("docExportPdf")?.addEventListener("click", () => docExport("pdf"));
$("docExportLong")?.addEventListener("click", () => docExport("long"));

// ───────────────────────── AI 智能修复 ─────────────────────────
let repairPath = "";
let repairOutPath = "";

async function openRepair() {
  $("repairModal").style.display = "flex";
  // 拉修复模式填充下拉
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
}
function closeRepair() { $("repairModal").style.display = "none"; }
$("repairBtn")?.addEventListener("click", openRepair);
$("repairClose")?.addEventListener("click", closeRepair);
$("repairModal")?.addEventListener("click", (e) => { if (e.target.id === "repairModal") closeRepair(); });

$("repairPick")?.addEventListener("click", async () => {
  const paths = await window.snapAPI.pickImages();
  if (!paths.length) return;
  repairPath = paths[0];
  const thumb = await window.snapAPI.readThumb(repairPath);
  $("repairBefore").innerHTML = `<img src="${thumb}" alt="原图" />`;
  $("repairAfter").innerHTML = '<span class="doc-empty">点「开始修复」</span>';
  $("repairRun").disabled = false;
  $("repairOpen").disabled = true;
  $("repairStatus").textContent = repairPath.split(/[\\/]/).pop();
});

$("repairRun")?.addEventListener("click", async () => {
  if (!repairPath) return;
  const mode = $("repairMode").value || "watermark";
  const runBtn = $("repairRun");
  runBtn.disabled = true;
  $("repairAfter").innerHTML = '<span class="repair-spin">AI 修复中，请稍候（约 10-40 秒）…</span>';
  $("repairStatus").textContent = "正在修复…";
  try {
    const r = await window.snapAPI.backend("repair_image", { path: repairPath, mode });
    if (r.ok && r.data?.out) {
      repairOutPath = r.data.out;
      const thumb = await window.snapAPI.readThumb(repairOutPath);
      $("repairAfter").innerHTML = `<img src="${thumb}" alt="修复后" />`;
      $("repairStatus").textContent = "修复完成：" + repairOutPath.split(/[\\/]/).pop();
      $("repairOpen").disabled = false;
    } else {
      $("repairAfter").innerHTML = '<span class="doc-empty">修复失败</span>';
      $("repairStatus").textContent = "修复失败：" + (r.error || "请重试");
    }
  } catch (e) {
    $("repairAfter").innerHTML = '<span class="doc-empty">修复失败</span>';
    $("repairStatus").textContent = "修复失败：" + e.message;
  } finally {
    runBtn.disabled = false;
  }
});

$("repairOpen")?.addEventListener("click", () => {
  if (repairOutPath) {
    const dir = repairOutPath.replace(/[\\/][^\\/]+$/, "");
    window.snapAPI.backend("open_path", { path: dir });
  }
});

// ───────────────────────── 截图 ─────────────────────────
const shots = []; // [{path, name, w, h, thumb}]

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
      <span class="pill pill-ok">✓ 已保存</span>`;
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

  const r = await window.snapAPI.backend("capture_start", { rows, main_count: mainCount, detail_count: detailCount });
  if (!r.ok) { $("collectStatus").textContent = "启动失败：" + (r.error || ""); return; }
  collecting = true;
  $("collectStart").style.display = "none";
  $("collectStop").style.display = "inline-flex";
  $("collectNext").style.display = "inline-flex";
  $("collectProgress").style.display = "block";
  $("collectStatus").textContent = "采集中：到浏览器里 Ctrl + 拖框截图";
  setBadge("● 采集中", true);
});

$("collectStop")?.addEventListener("click", async () => {
  await window.snapAPI.backend("capture_stop");
  collecting = false;
  $("collectStart").style.display = "inline-flex";
  $("collectStop").style.display = "none";
  $("collectNext").style.display = "none";
  $("collectStatus").textContent = "已停止采集。";
  setBadge("● 已就绪", true);
});

$("collectNext")?.addEventListener("click", () => window.snapAPI.backend("capture_next_row"));

// 自由截图：连续 Ctrl 拖框随手截，存自由截图目录
let freeOn = false;
$("freeBtn")?.addEventListener("click", async () => {
  if (!freeOn) {
    const r = await window.snapAPI.backend("free_capture_start");
    if (!r.ok) { setBadge("● 启用失败", false); alert("自由截图启用失败：" + (r.error || "可能被安全软件拦截")); return; }
    freeOn = true;
    $("freeBtn").classList.add("btn-primary");
    $("freeBtn").lastChild.textContent = " 结束自由截图";
    setBadge("● 自由截图中", true);
  } else {
    await window.snapAPI.backend("capture_stop");
    freeOn = false;
    $("freeBtn").classList.remove("btn-primary");
    $("freeBtn").lastChild.textContent = "自由截图";
    setBadge("● 已就绪", true);
  }
});

// 监听后台采集事件
window.snapAPI.onPyEvent(async (msg) => {
  if (msg.event === "capture_progress") {
    $("collectCur").textContent = `第 ${msg.index + 1}/${msg.total} 个：${msg.row_name || ""}（正在截「${msg.category}」）`;
    $("collectStat").textContent = `主图 ${msg.main_done}/${msg.main_count} · 详情 ${msg.detail_done}/${msg.detail_count}`;
  } else if (msg.event === "capture_saved") {
    let thumb = "";
    try { thumb = await window.snapAPI.readThumb(msg.path); } catch {}
    shots.unshift({ path: msg.path, name: `${msg.row_name}/${msg.category}/${msg.name}`, w: msg.w, h: msg.h, thumb });
    renderShots();
  } else if (msg.event === "capture_all_done") {
    collecting = false;
    $("collectStart").style.display = "inline-flex";
    $("collectStop").style.display = "none";
    $("collectNext").style.display = "none";
    $("collectStatus").textContent = "全部截完！可以去「整理成文档」或「AI 修复」。";
    setBadge("● 已就绪", true);
  } else if (msg.event === "capture_error") {
    $("collectStatus").textContent = "截图出错：" + (msg.error || "");
  }
});

window.addEventListener("DOMContentLoaded", () => { init(); renderShots(); });
