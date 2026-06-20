"""
打包脚本 - 将好办法自动化软件打包为 exe

使用方法:
    1. 先安装依赖:  pip install -r requirements.txt
    2. 运行打包:    python build.py
    3. 输出在 dist/好办法自动化/ 目录
"""

import subprocess
import sys
from pathlib import Path


def find_package_path(name: str) -> Path:
    mod = __import__(name)
    return Path(mod.__file__).parent


def build():
    root = Path(__file__).parent
    main_script = root / "main.py"
    inject_js = root / "app" / "inject.js"
    stealth_js = root / "app" / "stealth.js"
    pay_qr = root / "app" / "pay_qr.png"  # 收款码（可选，缺失时软件显示占位）

    ctk_path = find_package_path("customtkinter")
    playwright_path = find_package_path("playwright")
    driver_path = playwright_path / "driver"

    if not driver_path.exists():
        print("错误：找不到 Playwright driver 目录")
        print(f"  期望路径: {driver_path}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "好办法自动化",
        "--add-data", f"{inject_js};app",
        "--add-data", f"{stealth_js};app",
        "--add-data", f"{ctk_path};customtkinter",
        *(["--add-data", f"{pay_qr};app"] if pay_qr.exists() else []),
        "--add-data", f"{driver_path};playwright/driver",
        "--hidden-import", "customtkinter",
        "--hidden-import", "playwright",
        "--hidden-import", "playwright.sync_api",
        "--hidden-import", "playwright._impl",
        "--hidden-import", "playwright._impl._driver",
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--hidden-import", "certifi",
        "--hidden-import", "openpyxl",
        "--hidden-import", "et_xmlfile",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFilter",
        "--collect-all", "charset_normalizer",
        "--collect-all", "idna",
        "--collect-all", "openpyxl",
        "--collect-all", "PIL",
        str(main_script),
    ]

    print("=" * 50)
    print("  好办法自动化 - 开始打包")
    print("=" * 50)
    print(f"  主脚本: {main_script}")
    print(f"  inject.js: {inject_js}")
    print(f"  stealth.js: {stealth_js}")
    print(f"  customtkinter: {ctk_path}")
    print(f"  playwright driver: {driver_path}")
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\n打包失败！请检查上方错误信息。")
        sys.exit(1)

    dist_dir = root / "dist" / "好办法自动化"
    print()
    print("=" * 50)
    print("  打包完成！")
    print(f"  输出目录: {dist_dir}")
    print(f"  运行文件: {dist_dir / '好办法自动化.exe'}")
    print()
    print("  分发时将整个「好办法自动化」文件夹打包给用户即可")
    print("=" * 50)


if __name__ == "__main__":
    build()
