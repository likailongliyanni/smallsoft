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


HANDLERS = {
    "ping": cmd_ping,
    "get_serial": cmd_get_serial,
    "register": cmd_register,
    "sync_quota": cmd_sync_quota,
}


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


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
