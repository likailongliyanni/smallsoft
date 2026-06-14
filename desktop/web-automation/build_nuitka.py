"""
Nuitka 打包脚本 —— 好办法自动化
================================

相对 PyInstaller 的收益：源码编译为 C，启动更快、更难反编译、体积通常更小。

前置：
    pip install nuitka              # 已在 requirements 中
    Windows 首次编译会自动下载 MinGW64 编译器（--assume-yes-for-downloads）

用法：
    python build_nuitka.py
输出：
    dist_nuitka/好办法自动化/好办法自动化.exe   （整个文件夹分发给用户）

说明：
    - 浏览器内核（chromium/edge）不打进包；运行时用系统 Edge/Chrome，
      或用户机器上 %LOCALAPPDATA%\\ms-playwright 里 playwright 装好的内核。
    - 资源（inject.js / stealth.js / pay_qr.png）随包到 app/ 子目录，
      运行时由 app/paths.py 的 resource() 统一定位。
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path


def pkg_dir(name: str) -> Path:
    mod = __import__(name)
    return Path(mod.__file__).parent


def build():
    root = Path(__file__).parent
    main_script = root / "main.py"

    playwright = pkg_dir("playwright")
    driver = playwright / "driver"
    if not driver.exists():
        sys.exit(f"找不到 Playwright driver 目录: {driver}")

    app = root / "app"
    inject = app / "inject.js"
    stealth = app / "stealth.js"
    pay_qr = app / "pay_qr.png"

    out_dir = root / "dist_nuitka"

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--remove-output",
        "--windows-console-mode=disable",
        f"--output-dir={out_dir}",
        "--output-filename=好办法自动化.exe",

        # ── GUI / 框架 ──
        "--enable-plugin=tk-inter",
        "--include-package=customtkinter",
        "--include-package-data=customtkinter",   # 主题 .json + 字体

        # ── playwright：python 包 + driver（node.exe 等）数据 ──
        "--include-package=playwright",
        f"--include-data-dir={driver}=playwright/driver",

        # ── 其它第三方（含函数内 lazy import，显式纳入更稳）──
        "--include-package=requests",
        "--include-package-data=certifi",   # requests 的 HTTPS 根证书 cacert.pem
        "--include-package=openpyxl",
        "--include-package=PIL",

        # ── 自有资源（运行时 resource("app", ...) 定位）──
        f"--include-data-files={inject}=app/inject.js",
        f"--include-data-files={stealth}=app/stealth.js",

        # ── exe 文件元数据 ──
        "--company-name=好办法",
        "--product-name=好办法自动化",
        "--product-version=2.0.0",
        "--file-description=好办法自动化",
    ]
    if pay_qr.exists():
        cmd.append(f"--include-data-files={pay_qr}=app/pay_qr.png")
    cmd.append(str(main_script))

    print("=" * 56)
    print("  好办法自动化 - Nuitka 打包")
    print("=" * 56)
    print(f"  主脚本     : {main_script}")
    print(f"  driver     : {driver}")
    print(f"  输出目录   : {out_dir}")
    print()

    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("\n打包失败！请检查上方错误信息。")

    # standalone 文件夹名固定随主脚本：main.dist → 「好办法自动化」
    # 替换策略：先把旧目录【原子改名】为备份（被占用时这一步直接失败、绝不破坏旧目录），
    #          再把 main.dist 改名到位，最后删备份。彻底避免「删一半留残缺」。
    src = out_dir / "main.dist"
    final = out_dir / "好办法自动化"
    if src.exists():
        backup = None
        if final.exists():
            backup = out_dir / f"好办法自动化_old_{int(time.time())}"
            try:
                final.rename(backup)
            except Exception as ex:
                sys.exit(f"无法替换旧目录 {final}\n"
                         f"  → 多半是旧版程序在运行、或资源管理器开着该文件夹，请全部关闭后重试。\n  {ex}")
        try:
            src.rename(final)
        except Exception as ex:
            if backup is not None:
                try: backup.rename(final)   # 还原旧目录
                except Exception: pass
            sys.exit(f"改名失败：{src} → {final}\n"
                     f"  → 关闭占用后把 main.dist 手动改名为「好办法自动化」即可（无需重编）。\n  {ex}")
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)

    print()
    print("=" * 56)
    print("  打包完成！")
    print(f"  运行文件: {final / '好办法自动化.exe'}")
    print("  分发时把整个「好办法自动化」文件夹给用户即可")
    print("=" * 56)


if __name__ == "__main__":
    build()
