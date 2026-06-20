// 界面逻辑（这一版只做演示交互，不接后端）。
// 以后这里会通过 window.snapAPI 调 Python 后端。

// 复制软件编号（演示：仅提示，真实复制以后接 clipboard）
const copyBtn = document.getElementById("copySerial");
if (copyBtn) {
  copyBtn.addEventListener("click", () => {
    const serial = document.getElementById("serial").textContent.trim();
    navigator.clipboard?.writeText(serial).catch(() => {});
    copyBtn.title = "已复制：" + serial;
  });
}

// 同步额度（演示：随机变个数，证明界面是活的；以后接 Python 真实额度）
const syncBtn = document.getElementById("syncBtn");
if (syncBtn) {
  syncBtn.addEventListener("click", () => {
    const num = document.getElementById("quotaNum");
    if (num) num.textContent = String(40 + Math.floor(Math.random() * 60));
  });
}
