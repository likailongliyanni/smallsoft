const Api = {
  userToken: localStorage.getItem("wa_user_token") || "",
  adminToken: localStorage.getItem("wa_admin_token") || "",
  setUserToken(token) {
    this.userToken = token || "";
    if (token) localStorage.setItem("wa_user_token", token);
    else localStorage.removeItem("wa_user_token");
  },
  setAdminToken(token) {
    this.adminToken = token || "";
    if (token) localStorage.setItem("wa_admin_token", token);
    else localStorage.removeItem("wa_admin_token");
  },
  async call(action, options = {}) {
    const headers = options.headers || {};
    if (options.admin && this.adminToken) headers.Authorization = `Bearer ${this.adminToken}`;
    if (!options.admin && this.userToken) headers.Authorization = `Bearer ${this.userToken}`;
    if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const url = action.includes("&") ? `/api.php?action=${action}` : `/api.php?action=${encodeURIComponent(action)}`;
    const res = await fetch(url, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || `请求失败：${res.status}`);
    return data;
  }
};

function $(selector) {
  return document.querySelector(selector);
}

function statusBox(selector, message, error = false) {
  const el = typeof selector === "string" ? $(selector) : selector;
  if (!el) return;
  el.hidden = false;
  el.textContent = message;
  el.className = error ? "status error" : "status";
}

async function compressImage(file, maxSide = 400, maxBytes = 50 * 1024) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  let quality = 0.82;
  let blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
  while (blob && blob.size > maxBytes && quality > 0.35) {
    quality -= 0.08;
    blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
  }
  return blob || file;
}

async function fileText(file) {
  return await file.text();
}
