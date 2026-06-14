"""
本地测试服务器 - 解决 file:// 协议闪退问题
=============================================

用法：
    cd software_v2
    python test_upload_server.py

启动后会在 http://localhost:8765/ 提供测试页。
然后把这个 URL 粘到「好办法」软件的「目标网址」里录制。
"""

import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 8765
ROOT = Path(__file__).resolve().parent

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        # 只打必要日志，少点噪音
        msg = format % args
        if "test_upload_recording.html" in msg or "404" in msg or "500" in msg:
            print(f"[server] {self.address_string()} - {msg}")

    def end_headers(self):
        # 关闭缓存，避免改了 HTML 后浏览器还显示老的
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()


def main():
    url = f"http://localhost:{PORT}/test_upload_recording.html"
    print("=" * 60)
    print(f"📡 测试服务器已启动")
    print("=" * 60)
    print()
    print(f"🎯 测试页 URL（复制到「好办法」目标网址里）:")
    print(f"   {url}")
    print()
    print(f"📂 服务根目录: {ROOT}")
    print()
    print(f"⏹️  按 Ctrl+C 停止服务器")
    print("=" * 60)
    print()

    # 同时用默认浏览器打开一次，方便先手动看一眼
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            print(f"\n❌ 端口 {PORT} 被占用了")
            print(f"   可能是上次的服务器还在跑。请：")
            print(f"   1) 检查任务管理器有没有别的 python.exe")
            print(f"   2) 或改本脚本的 PORT 变量为别的端口（如 8866）")
        else:
            raise


if __name__ == "__main__":
    main()
