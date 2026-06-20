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
$("importBtn")?.addEventListener("click", async () => { openDoc(); await docAddImages(); });

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

window.addEventListener("DOMContentLoaded", init);
