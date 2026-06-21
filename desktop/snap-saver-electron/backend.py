# -*- coding: utf-8 -*-
"""Electron 界面的 Python 后端桥。

Electron 把每条命令以「一行 JSON」从 stdin 发来，本脚本调用原版
snap_saver.py 里成熟的函数干活，再把结果以「一行 JSON」从 stdout 返回。
这样界面层（Electron/JS）和功能层（Python）解耦，原版逻辑全部复用。

协议（每行一个 JSON 对象）：
  收：{"id": 1, "cmd": "get_serial", "args": {...}}
  回：{"id": 1, "ok": true, "data": {...}}  或  {"id": 1, "ok": false, "error": "..."}
"""
import json
import sys
import io
from pathlib import Path

# 让 stdout/stderr 用 UTF-8，避免中文乱码 / 编码报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", newline="")

# 复用原版 snap_saver.py 的全部逻辑
sys.path.insert(0, str(Path(__file__).resolve().parent))
import snap_saver as S

# 持有一个登记后的 token（同步额度等需要）
_STATE = {"token": "", "server_url": S.DEFAULT_SERVER_URL}


def _server_url() -> str:
    return _STATE.get("server_url") or S.DEFAULT_SERVER_URL


def _pretty_serial(raw: str) -> str:
    """把编号格式化成界面显示用：12 位 MAC → XX-XX-XX-XX-XX-XX，去掉 -pic 等后缀。"""
    hexs = "".join(c for c in str(raw or "") if c.isalnum()).upper()
    # 去掉末尾可能的软件代码后缀（pic/auto）——只保留前 12 位 MAC
    if len(hexs) >= 12:
        hexs = hexs[:12]
    if len(hexs) == 12:
        return "-".join(hexs[i:i + 2] for i in range(0, 12, 2))
    return str(raw or "")


def cmd_get_serial(args):
    """返回本机软件编号（MAC，带横线，界面显示用）。"""
    return {"serial": _pretty_serial(S.local_software_id())}


def cmd_register(args):
    """登记设备，拿 token + 额度。界面启动时调一次。"""
    serial = S.local_software_id()
    data = S.server_register_device(_server_url(), serial)
    _STATE["token"] = str(data.get("token") or "")
    quota = data.get("quota") or {}
    return {
        "serial": _pretty_serial(data.get("software_id") or serial),
        "quota": {
            "free": int(quota.get("free") or 0),
            "paid": int(quota.get("paid") or 0),
            "available": int(quota.get("available") or 0),
        },
    }


def cmd_sync_quota(args):
    """同步额度（没 token 先登记一次）。"""
    if not _STATE["token"]:
        return cmd_register(args)
    data = S.server_device_status(_server_url(), _STATE["token"])
    quota = data.get("quota") or {}
    return {
        "quota": {
            "free": int(quota.get("free") or 0),
            "paid": int(quota.get("paid") or 0),
            "available": int(quota.get("available") or 0),
        },
    }


def cmd_ping(args):
    """连通性测试。"""
    return {"pong": True, "version": S.APP_VERSION}


def cmd_list_shots(args):
    """列出「自由截图」目录里的图片，给整理文档用。
    args.dir 可指定截图目录；默认用户文档下的「存图结果/自由截图」。"""
    folder = args.get("dir")
    if folder:
        folder = Path(folder)
    else:
        # 与原版一致：输出目录/自由截图
        out = Path(S.app_dir()) / "存图结果" / "自由截图"
        folder = out
    shots = []
    if folder.exists():
        for p in sorted(folder.glob("*.jpg")):
            try:
                with S.Image.open(p) as im:
                    w, h = im.size
            except Exception:
                w, h = 0, 0
            shots.append({"path": str(p), "name": p.name, "w": w, "h": h})
    return {"shots": shots, "dir": str(folder)}


def cmd_describe_image(args):
    """对一张图调 AI 生成说明。args: {path, hint, style}"""
    if not _STATE["token"]:
        S.server_register_device(_server_url(), S.local_software_id())  # 兜底先登记
        # 重新登记拿 token
        data = S.server_register_device(_server_url(), S.local_software_id())
        _STATE["token"] = str(data.get("token") or "")
    path = Path(args.get("path") or "")
    hint = str(args.get("hint") or "")
    style = str(args.get("style") or "detail")
    res = S.server_describe_image(_server_url(), _STATE["token"], path, hint=hint, style=style)
    return {"description": res.get("description", ""), "charged": bool(res.get("charged"))}


def cmd_export_doc(args):
    """导出整理文档。args: {title, intro, items:[{path,caption,size}], format:'pdf'|'long', watermark}"""
    title = str(args.get("title") or "使用说明")
    intro = str(args.get("intro") or "")
    fmt = str(args.get("format") or "pdf")
    watermark = bool(args.get("watermark", True))
    raw_items = args.get("items") or []

    loaded = []
    for it in raw_items:
        p = Path(it.get("path") or "")
        if not p.exists():
            continue
        try:
            with S.Image.open(p) as im:
                img = im.convert("RGB")
                img.load()
            loaded.append((img, str(it.get("caption") or ""), str(it.get("size") or "full")))
        except Exception:
            continue
    if not loaded:
        raise RuntimeError("没有可导出的图片。")

    out_dir = Path(S.app_dir()) / "存图结果" / "文档"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = S.safe_folder_name(title, "使用说明")
    stamp = S.time.strftime("%Y%m%d-%H%M%S")

    if fmt == "long":
        out = out_dir / f"{name}_{stamp}.jpg"
        image = S.build_long_image(title, intro, loaded, watermark=watermark)
        image.save(out, "JPEG", quality=92)
    else:
        out = out_dir / f"{name}_{stamp}.pdf"
        S.build_doc_pdf(out, title, intro, loaded, watermark=watermark)
    return {"path": str(out), "dir": str(out_dir)}


def cmd_open_path(args):
    """在资源管理器里打开一个文件/目录。"""
    target = args.get("path") or ""
    try:
        S.os.startfile(str(target))
    except Exception:
        pass
    return {"ok": True}


# ───────────────────────── 电商批量采集（Ctrl 拖框截图）─────────────────────────
class CaptureWorker:
    """复用原版 CtrlDragHook：在网页上按 Ctrl 拖框截图，按主图/详情自动归类、自动翻页。
    钩子事件来了直接截图存盘，并通过 _push_event 主动告诉 Electron 界面更新进度。"""

    def __init__(self):
        self.hook = None
        self.active = False
        self.free_mode = False   # 自由截图模式：不归类、不翻页，直接存自由截图目录
        self.rows = []           # [{name, link}]
        self.index = 0
        self.main_count = 1
        self.detail_count = 3
        self.category = "主图"
        self.counts = {}         # index -> [main_done, detail_done]
        self.gesture_start = None
        self._poll_thread = None
        self.out_dir = Path(S.app_dir()) / "存图结果"

    def start_free(self):
        """自由截图：装钩子，Ctrl 拖框随手截，存到「自由截图」目录。"""
        if self.active:
            return {"ok": True, "msg": "已在采集中"}
        self.free_mode = True
        self.hook = S.CtrlDragHook()
        ok = self.hook.install()
        if not ok:
            self.free_mode = False
            raise RuntimeError(self.hook.last_error or "截图钩子启用失败，可能被安全软件拦截。")
        self.active = True
        self._poll_thread = _threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        return {"ok": True}

    def _save_free(self, sx, sy, ex, ey):
        left, top = min(sx, ex), min(sy, ey)
        right, bottom = max(sx, ex), max(sy, ey)
        if right - left < 5 or bottom - top < 5:
            return
        from PIL import ImageGrab
        self.hook.enabled = False
        try:
            img = ImageGrab.grab(bbox=(int(left), int(top), int(right), int(bottom)), all_screens=True)
        finally:
            self.hook.enabled = True
        if img.mode != "RGB":
            img = img.convert("RGB")
        out_dir = self.out_dir / "自由截图"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = S.time.strftime("%Y%m%d-%H%M%S")
        target = out_dir / f"截图_{stamp}.jpg"
        idx = 2
        while target.exists():
            target = out_dir / f"截图_{stamp}-{idx}.jpg"; idx += 1
        img.save(target, "JPEG", quality=95)
        _push_event("capture_saved", path=str(target), name=target.name,
                    w=img.width, h=img.height, row_name="自由截图", category="")

    def counts_for(self, i):
        return self.counts.setdefault(i, [0, 0])

    def start(self, rows, main_count, detail_count, out_dir=None):
        if self.active:
            return {"ok": True, "msg": "已在采集中"}
        if not rows:
            raise RuntimeError("请先导入名称+链接列表。")
        self.rows = rows
        self.index = 0
        self.main_count = int(main_count)
        self.detail_count = int(detail_count)
        self.category = "主图"
        self.counts = {}
        if out_dir:
            self.out_dir = Path(out_dir)

        self.hook = S.CtrlDragHook()
        ok = self.hook.install()
        if not ok:
            raise RuntimeError(self.hook.last_error or "截图钩子启用失败，可能被安全软件拦截。")
        self.active = True
        self._poll_thread = _threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        # 打开第一个商品链接
        self._open_link()
        self._push_progress()
        return {"ok": True}

    def stop(self):
        self.active = False
        self.free_mode = False
        if self.hook:
            try:
                self.hook.uninstall()
            except Exception:
                pass
        self.hook = None
        return {"ok": True}

    def _open_link(self):
        if 0 <= self.index < len(self.rows):
            link = (self.rows[self.index].get("link") or "").strip()
            if link:
                try:
                    S.webbrowser.open(link)
                except Exception:
                    pass

    def _poll_loop(self):
        import queue as _q
        import time as _t
        while self.active and self.hook:
            try:
                kind, x, y = self.hook.events.get(timeout=0.2)
            except _q.Empty:
                continue
            except Exception:
                break
            try:
                if kind == "start":
                    self.gesture_start = (x, y)
                    _push_event("capture_drag_start", x=x, y=y)
                elif kind == "move":
                    if self.gesture_start:
                        _push_event("capture_drag_move", x=x, y=y)
                elif kind == "finish":
                    if self.gesture_start:
                        sx, sy = self.gesture_start
                        self.gesture_start = None
                        _push_event("capture_drag_end")
                        if self.free_mode:
                            self._save_free(sx, sy, x, y)
                        else:
                            self._do_capture(sx, sy, x, y)
            except Exception as e:
                _push_event("capture_error", error=str(e))

    def _do_capture(self, sx, sy, ex, ey):
        left, top = min(sx, ex), min(sy, ey)
        right, bottom = max(sx, ex), max(sy, ey)
        if right - left < 5 or bottom - top < 5:
            return
        from PIL import ImageGrab
        self.hook.enabled = False
        try:
            img = ImageGrab.grab(bbox=(int(left), int(top), int(right), int(bottom)), all_screens=True)
        finally:
            self.hook.enabled = True
        if img.mode != "RGB":
            img = img.convert("RGB")

        row = self.rows[self.index]
        name = S.safe_folder_name(row.get("name") or f"第{self.index+1}行", f"第{self.index+1}行")
        cat = self.category
        done = self.counts_for(self.index)[0 if cat == "主图" else 1]
        target = self.out_dir / name / cat / f"pic{done + 1}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, "JPEG", quality=95)
        self.counts_for(self.index)[0 if cat == "主图" else 1] += 1

        _push_event("capture_saved", path=str(target), name=target.name,
                    w=img.width, h=img.height, row_name=row.get("name"), category=cat)
        self._after_capture()

    def _after_capture(self):
        md, dd = self.counts_for(self.index)
        if self.category == "主图":
            if self.main_count and md >= self.main_count:
                if self.detail_count > 0:
                    self.category = "详情"
                else:
                    self._advance()
                    return
        else:
            if self.detail_count and dd >= self.detail_count:
                self._advance()
                return
        self._push_progress()

    def _advance(self):
        if self.index + 1 >= len(self.rows):
            _push_event("capture_all_done")
            self._push_progress()
            return
        self.index += 1
        self.category = "主图"
        self._open_link()
        self._push_progress()

    def set_category(self, cat):
        self.category = "详情" if cat == "详情" else "主图"
        self._push_progress()

    def next_row(self):
        self._advance()

    def _push_progress(self):
        md, dd = self.counts_for(self.index)
        cur = self.rows[self.index] if 0 <= self.index < len(self.rows) else {}
        _push_event("capture_progress",
                    index=self.index, total=len(self.rows),
                    row_name=cur.get("name", ""), category=self.category,
                    main_done=md, main_count=self.main_count,
                    detail_done=dd, detail_count=self.detail_count)


_WORKER = CaptureWorker()


def cmd_capture_start(args):
    rows = args.get("rows") or []
    return _WORKER.start(rows, args.get("main_count", 1), args.get("detail_count", 3), args.get("out_dir"))


def cmd_capture_stop(args):
    return _WORKER.stop()


def cmd_capture_set_category(args):
    _WORKER.set_category(str(args.get("category") or "主图"))
    return {"ok": True}


def cmd_capture_next_row(args):
    _WORKER.next_row()
    return {"ok": True}


def cmd_import_rows_file(args):
    """从 Excel/CSV/txt 文件读「名称+链接」列表。args: {path}"""
    p = Path(args.get("path") or "")
    if not p.exists():
        raise RuntimeError("文件不存在。")
    raw = S.read_import_rows(p)  # 返回 [(name, link), ...] 元组列表
    rows = [{"name": t[0], "link": t[1] if len(t) > 1 else ""} for t in raw]
    return {"rows": rows}


def cmd_parse_rows(args):
    """解析「名称+链接」文本（每行：名称<制表符或空格>链接），返回 rows。"""
    text = str(args.get("text") or "")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 制表符或多空格分隔，取第一个链接样式的字段
        parts = line.split("\t") if "\t" in line else line.rsplit(None, 1)
        if len(parts) == 2:
            name, link = parts[0].strip(), parts[1].strip()
        else:
            name, link = line, ""
        rows.append({"name": name, "link": link})
    return {"rows": rows}


def cmd_save_capture(args):
    """保存一张截图到「自由截图」目录。args: {data_url} 或 {png_base64}
    返回 {path}。与原版命名一致：截图_时间戳.jpg。"""
    import base64
    import io as _io
    raw = args.get("png_base64") or ""
    if not raw and args.get("data_url"):
        du = str(args["data_url"])
        raw = du.split(",", 1)[1] if "," in du else du
    if not raw:
        raise RuntimeError("没有图像数据。")
    img_bytes = base64.b64decode(raw)
    img = S.Image.open(_io.BytesIO(img_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    out_dir = Path(S.app_dir()) / "存图结果" / "自由截图"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = S.time.strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"截图_{stamp}.jpg"
    idx = 2
    while target.exists():
        target = out_dir / f"截图_{stamp}-{idx}.jpg"
        idx += 1
    img.save(target, "JPEG", quality=95)
    return {"path": str(target), "name": target.name, "w": img.width, "h": img.height, "dir": str(out_dir)}


def cmd_repair_modes(args):
    """返回 AI 修复的 5 种模式（去水印/去贴纸/去广告/清爽化/白底上图）。"""
    return {"modes": [{"key": k, "label": v} for k, v in S.REPAIR_MODES]}


def _ensure_token():
    if not _STATE["token"]:
        data = S.server_register_device(_server_url(), S.local_software_id())
        _STATE["token"] = str(data.get("token") or "")


def cmd_repair_image(args):
    """对一张图做 AI 修复（去水印/白底等）。
    args: {path, mode, keep_original}
    返回 {out} 处理后图片路径。修复后默认覆盖原图，keep_original=true 则原图备份。"""
    import threading
    import tempfile as _tf
    _ensure_token()
    src = Path(args.get("path") or "")
    mode = str(args.get("mode") or "watermark")
    keep = bool(args.get("keep_original", False))
    if not src.exists():
        raise RuntimeError("图片不存在。")

    # 输出：AI修复 目录下，文件名加 _修复 后缀（不覆盖原图，更安全，界面能对比）
    out_dir = Path(S.app_dir()) / "存图结果" / "AI修复"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / (src.stem + "_修复.jpg")

    stop = threading.Event()
    with _tf.TemporaryDirectory(prefix="snap_repair_") as tmp:
        S.server_remove_watermark_to(
            _server_url(), _STATE["token"], src, target, Path(tmp), mode, stop)
    return {"out": str(target), "dir": str(out_dir)}


HANDLERS = {
    "ping": cmd_ping,
    "get_serial": cmd_get_serial,
    "register": cmd_register,
    "sync_quota": cmd_sync_quota,
    "list_shots": cmd_list_shots,
    "describe_image": cmd_describe_image,
    "export_doc": cmd_export_doc,
    "open_path": cmd_open_path,
    "repair_modes": cmd_repair_modes,
    "repair_image": cmd_repair_image,
    "save_capture": cmd_save_capture,
    "parse_rows": cmd_parse_rows,
    "import_rows_file": cmd_import_rows_file,
    "capture_start": cmd_capture_start,
    "capture_stop": cmd_capture_stop,
    "capture_set_category": cmd_capture_set_category,
    "capture_next_row": cmd_capture_next_row,
    "free_capture_start": lambda args: _WORKER.start_free(),
}


import threading as _threading
_SEND_LOCK = _threading.Lock()


def _send(obj):
    # 线程安全：命令回应和后台钩子事件可能并发写 stdout
    with _SEND_LOCK:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _push_event(event, **data):
    """后台主动推送（非命令回应）。Electron 用 event 字段区分。"""
    _send({"event": event, **data})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        rid = msg.get("id")
        cmd = msg.get("cmd")
        args = msg.get("args") or {}
        handler = HANDLERS.get(cmd)
        if not handler:
            _send({"id": rid, "ok": False, "error": f"未知命令: {cmd}"})
            continue
        try:
            data = handler(args)
            _send({"id": rid, "ok": True, "data": data})
        except Exception as e:
            _send({"id": rid, "ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
