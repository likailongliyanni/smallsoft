"""统一资源 / 目录定位
==================

兼容三种运行环境：

1. 源码运行（开发）            —— 路径相对项目根
2. PyInstaller 打包           —— ``sys.frozen`` + ``sys._MEIPASS``
3. Nuitka standalone 打包     —— 每个编译模块注入的 ``__compiled__``

历史代码散落着 ``if getattr(sys, "frozen", False): ... sys._MEIPASS`` 这类
PyInstaller 专用判断，Nuitka 下不成立（Nuitka 既不设 ``sys.frozen`` 也没有
``sys._MEIPASS``）。本模块把判断收敛到一处，业务代码只调用
``resource("app", "inject.js")`` / ``app_dir()`` 即可，与打包器无关。
"""
import os
import sys
from pathlib import Path


def is_pyinstaller() -> bool:
    """PyInstaller 冻结环境（onefile/onedir 均成立）。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def is_nuitka() -> bool:
    """Nuitka 编译环境。

    Nuitka 给每个编译模块注入模块级 ``__compiled__``，这是官方推荐的探测
    方式（实测 ``sys.__compiled__`` 并不存在，必须查模块 globals）。
    """
    return "__compiled__" in globals()


def is_frozen() -> bool:
    """是否处于任意一种打包环境。"""
    return is_pyinstaller() or is_nuitka()


def app_dir() -> Path:
    """可执行文件所在目录（打包后）/ 项目根目录（开发）。

    用于定位与 exe 同级的「外部」数据（旧版数据迁移、日志兜底等）。
    PyInstaller(onedir) 与 Nuitka(standalone) 下 ``sys.executable`` 都指向
    本程序自己的 exe，可统一取其父目录。
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # 开发：本文件位于 app/ 下，项目根是上一级
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """随包只读资源的根目录。

    - PyInstaller：解压目录 ``_MEIPASS``
    - Nuitka standalone：exe 同目录
    - 开发：项目根
    """
    if is_pyinstaller():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return app_dir()


def resource(*parts: str) -> Path:
    """定位随包资源，例如 ``resource("app", "inject.js")``。"""
    return resource_dir().joinpath(*parts)


def documents_dir() -> Path:
    """用户文档目录（可写数据根），不存在则回退到 home。"""
    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    docs = home / "Documents"
    return docs if docs.exists() else home
