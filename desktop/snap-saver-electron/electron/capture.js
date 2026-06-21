// 截图覆盖层：显示全屏截图，鼠标拖框选区域，松手裁剪后发回主进程。
const bg = document.getElementById("bg");
const sel = document.getElementById("sel");
const sizeTag = document.getElementById("size");
const tip = document.getElementById("tip");

let imgEl = new Image();
let scale = 1;       // 物理像素 / CSS 像素
let dragging = false;
let sx = 0, sy = 0;

// 接收主进程发来的全屏截图
window.captureAPI.onBg(({ img, scale: sc }) => {
  scale = sc || 1;
  bg.src = img;
  imgEl.src = img;
});

function rectOf(x1, y1, x2, y2) {
  return {
    left: Math.min(x1, x2), top: Math.min(y1, y2),
    width: Math.abs(x2 - x1), height: Math.abs(y2 - y1),
  };
}

document.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  dragging = true;
  sx = e.clientX; sy = e.clientY;
  tip.style.display = "none";
  sel.style.display = "block";
  sizeTag.style.display = "block";
});

document.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  const r = rectOf(sx, sy, e.clientX, e.clientY);
  sel.style.left = r.left + "px";
  sel.style.top = r.top + "px";
  sel.style.width = r.width + "px";
  sel.style.height = r.height + "px";
  sizeTag.textContent = Math.round(r.width * scale) + " × " + Math.round(r.height * scale);
  // 尺寸标签放在选框右下角内侧
  sizeTag.style.left = (r.left + r.width - 70) + "px";
  sizeTag.style.top = (r.top + r.height + 6) + "px";
});

document.addEventListener("mouseup", (e) => {
  if (!dragging) return;
  dragging = false;
  const r = rectOf(sx, sy, e.clientX, e.clientY);
  if (r.width < 5 || r.height < 5) {
    // 选区太小，视为取消
    window.captureAPI.done(null);
    return;
  }
  // 按物理像素裁剪
  const px = {
    x: Math.round(r.left * scale), y: Math.round(r.top * scale),
    w: Math.round(r.width * scale), h: Math.round(r.height * scale),
  };
  const canvas = document.createElement("canvas");
  canvas.width = px.w; canvas.height = px.h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(imgEl, px.x, px.y, px.w, px.h, 0, 0, px.w, px.h);
  const dataURL = canvas.toDataURL("image/png");
  window.captureAPI.done({ dataURL });
});

// Esc 取消
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") window.captureAPI.done(null);
});
