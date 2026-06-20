import logging
import os
import sys
import traceback
from pathlib import Path

from app.paths import app_dir, is_frozen

_app_dir = app_dir()
if is_frozen():
    # 打包后把 playwright 浏览器目录锚定到用户机器的标准位置
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"),
    )

# error.log 写到用户文档目录（与 flows/ 同一位置）
try:
    _log_dir = Path(os.path.expanduser("~")) / "Documents" / "好办法自动化"
    _log_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    _log_dir = _app_dir

logging.basicConfig(
    filename=str(_log_dir / "error.log"),
    level=logging.ERROR,
    format="%(asctime)s  %(message)s",
    encoding="utf-8",
)


def show_error_dialog(msg: str):
    """可复制的错误弹窗"""
    import tkinter as tk

    root = tk.Tk()
    root.title("好办法自动化 - 启动出错")
    root.geometry("520x340")
    root.resizable(False, False)

    tk.Label(root, text="启动出错，请将以下信息发给客服：",
             font=("Microsoft YaHei", 12), anchor="w").pack(
        fill="x", padx=16, pady=(16, 8))

    text = tk.Text(root, font=("Consolas", 10), wrap="word",
                   bg="#f8f8f8", relief="solid", bd=1)
    text.pack(fill="both", expand=True, padx=16)
    text.insert("1.0", msg)
    text.config(state="disabled")

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(msg)
        btn.config(text="已复制！")

    btn = tk.Button(root, text="一键复制错误信息", font=("Microsoft YaHei", 12),
                    bg="#2563eb", fg="white", relief="flat",
                    cursor="hand2", command=copy_all)
    btn.pack(fill="x", padx=16, pady=(10, 16), ipady=6)

    root.mainloop()


def main():
    from app.window import MainWindow
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        logging.error(msg)
        try:
            show_error_dialog(msg)
        except Exception:
            pass
        sys.exit(1)
