import json
import logging
import shutil
import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.paths import app_dir, documents_dir, resource
from app.api import ApiClient
from app.diag import DiagDialog
from app.patterns_sync import PatternsLibrary
from app.dsl import steps_to_dsl
from app.excel import (collect_columns, collect_sample_row,
                       generate_template, count_rows)
from app.recorder import Recorder
from app.rules import load_rules, update_from_server
from app.runner import Runner, load_dsl
from app.sanitize import sanitize_steps, sanitize_dsl
from app.serial import get_serial

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

# ── 数据目录：从「用户文档」读，旧版本数据自动迁移 ──
def _resolve_data_dir() -> Path:
    """
    新数据位置：%USERPROFILE%/Documents/好办法自动化/
    旧数据位置（v1.0）：exe 同目录
    启动时检测旧位置，把 flows/、patterns.json、rules.json 迁移到新位置
    """
    old_dir = app_dir()

    # 用户文档目录（不存在则回退 home，见 app.paths.documents_dir）
    try:
        documents = documents_dir()
    except Exception:
        documents = old_dir

    new_dir = documents / "好办法自动化"
    new_dir.mkdir(parents=True, exist_ok=True)

    # 迁移旧数据
    if old_dir != new_dir:
        import shutil
        for item in ["flows", "patterns.json", "rules.json"]:
            src = old_dir / item
            dst = new_dir / item
            if src.exists() and not dst.exists():
                try:
                    if src.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                except Exception:
                    pass  # 迁移失败不影响主流程

    return new_dir


DATA_DIR = _resolve_data_dir()
FLOWS_DIR = DATA_DIR / "flows"
FLOWS_DIR.mkdir(exist_ok=True)

# ⭐ 聚水潭专区独立存储（流程和 profile 都跟普通模式分开）
JST_FLOWS_DIR = DATA_DIR / "flows_jst"
JST_FLOWS_DIR.mkdir(exist_ok=True)
JST_PROFILE_DIR = DATA_DIR / "edge_jst_profile"

WECHAT = "18033086531"
TUTORIAL_URL = "https://tools.haobanfa.online/tutorial"
MAX_STEPS = 50              # 步数上限
SOFTWARE_VERSION = "2.0 BETA-6"  # 软件版本（大改时手动 +）

log = logging.getLogger(__name__)

# ── 配色 ──
C_BG     = "#f0f0f0"
C_CARD   = "#ffffff"
C_BORDER = "#c8c8c8"
C_GREEN  = "#16a34a"
C_GREEN_H= "#15803d"
C_RED    = "#dc2626"
C_ORANGE = "#c2410c"
C_BLUE   = "#2563eb"
C_TEXT   = "#000000"
C_TEXT2  = "#333333"
C_TEXT3  = "#555555"

FN = "Microsoft YaHei"
F_BODY = (FN, 14, "bold")
F_SM   = (FN, 13)
F_SMB  = (FN, 13, "bold")
F_MONO = ("Consolas", 16, "bold")
F_NUM  = (FN, 28, "bold")
F_BTN  = (FN, 14, "bold")

# 侧边栏配色
C_SIDEBAR     = "#ffffff"   # 侧边栏背景
C_SIDE_ACTIVE = "#fef2f2"   # 选中项底色（淡红，呼应 logo）
C_SIDE_BARTOP = "#ffffff"   # 顶栏背景


class _SidebarTabs(ctk.CTkFrame):
    """左侧边栏导航 —— 接口兼容 CTkTabview。

    设计目标：完全替换 CTkTabview，但对外暴露相同的方法
    （add / set / tab / pack），这样原有 6 个 _build_xxx 页面方法
    和所有切页逻辑（self.tabs.set / self.tabs.tab）一行都不用改。

    布局：左边一条固定宽度的导航栏（每个 page 一个按钮），
    右边一个内容区，同一时刻只 pack 当前选中的 page frame。
    """

    def __init__(self, master, width_side: int = 188, **kwargs):
        super().__init__(master, fg_color=C_BG, corner_radius=0, **kwargs)
        self._width_side = width_side
        self._pages: dict[str, ctk.CTkFrame] = {}   # name -> 内容 frame
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._order: list[str] = []
        self._current: str | None = None
        self._footer_widgets: list = []

        # 左侧导航栏（固定宽度，自带分隔线）
        self._side = ctk.CTkFrame(self, width=width_side, corner_radius=0,
                                  fg_color=C_SIDEBAR, border_width=0)
        self._side.pack(side="left", fill="y")
        self._side.pack_propagate(False)

        # 右侧 1px 分隔线，让边栏和内容区分明
        sep = ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=C_BORDER)
        sep.pack(side="left", fill="y")

        # 导航按钮容器（顶部）
        self._nav = ctk.CTkFrame(self._side, fg_color="transparent")
        self._nav.pack(side="top", fill="x", padx=10, pady=(14, 0))

        # 边栏底部留给"附加操作"（如重新登录），由外部 add_footer_button 填
        self._side_footer = ctk.CTkFrame(self._side, fg_color="transparent")
        self._side_footer.pack(side="bottom", fill="x", padx=10, pady=12)

        # 右侧内容区
        self._content = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

    # ── 兼容 CTkTabview 的接口 ──
    def add(self, name: str) -> ctk.CTkFrame:
        """新增一个页面，返回可往里填东西的 frame（已存在则直接返回）。"""
        if name in self._pages:
            return self._pages[name]
        page = ctk.CTkFrame(self._content, fg_color=C_BG, corner_radius=0)
        self._pages[name] = page
        self._order.append(name)

        # 导航按钮
        label, icon = self._split_icon(name)
        btn = ctk.CTkButton(
            self._nav, text=f"  {icon}  {label}", anchor="w",
            height=42, corner_radius=8, font=(FN, 14, "bold"),
            fg_color="transparent", text_color=C_TEXT2,
            hover_color="#f3f4f6",
            command=lambda n=name: self.set(n),
        )
        btn.pack(fill="x", pady=3)
        self._buttons[name] = btn

        # 第一个页面默认选中
        if self._current is None:
            self.set(name)
        return page

    def tab(self, name: str) -> ctk.CTkFrame:
        """取已存在页面的 frame（兼容 CTkTabview.tab）。"""
        if name not in self._pages:
            return self.add(name)
        return self._pages[name]

    def set(self, name: str):
        """切换到某页。"""
        if name not in self._pages:
            return
        if self._current == name:
            return
        # 隐藏旧页
        if self._current and self._current in self._pages:
            try:
                self._pages[self._current].pack_forget()
            except Exception:
                pass
            self._style_button(self._current, active=False)
        # 显示新页
        self._current = name
        self._pages[name].pack(fill="both", expand=True, padx=16, pady=12)
        self._style_button(name, active=True)

    def get(self) -> str:
        return self._current or ""

    # ── 边栏底部附加按钮（重新登录等）──
    def add_footer_button(self, text: str, command, text_color: str = C_TEXT3):
        btn = ctk.CTkButton(
            self._side_footer, text=text, anchor="w",
            height=36, corner_radius=8, font=F_SM,
            fg_color="transparent", text_color=text_color,
            hover_color="#f3f4f6", command=command,
        )
        btn.pack(fill="x", pady=2)
        self._footer_widgets.append(btn)
        return btn

    # ── 内部辅助 ──
    @staticmethod
    def _split_icon(name: str):
        """把 '🛒 聚水潭' 拆成 (文字, 图标)；没有图标就给默认。"""
        default_icons = {
            "首页": "🏠", "录制": "⏺", "整理": "🗂",
            "我的流程": "📁", "功能预告": "🔮",
        }
        parts = name.split(" ", 1)
        if len(parts) == 2 and not parts[0].isascii():
            return parts[1], parts[0]
        return name, default_icons.get(name, "•")

    def _style_button(self, name: str, active: bool):
        btn = self._buttons.get(name)
        if not btn:
            return
        if active:
            btn.configure(fg_color=C_SIDE_ACTIVE, text_color=C_RED,
                          hover_color=C_SIDE_ACTIVE)
        else:
            btn.configure(fg_color="transparent", text_color=C_TEXT2,
                          hover_color="#f3f4f6")


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("好办法自动化")
        # 还原（非最大化）时的尺寸，居中
        self.geometry("1180x760")
        self.minsize(1000, 660)
        self.configure(fg_color=C_BG)
        try:
            self.update_idletasks()
            sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
            w, h = 1180, 760
            x = max(0, (sw - w) // 2); y = max(0, (sh - h) // 2 - 20)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
        # 默认最大化启动：聚水潭卡片网格需要完整宽度才铺得开
        try:
            self.after(0, lambda: self.state("zoomed"))
        except Exception:
            pass

        self.serial = get_serial()
        self.api = ApiClient(self.serial)
        self.rules = load_rules(DATA_DIR)
        self.patterns_lib = PatternsLibrary(DATA_DIR)
        self.recorder = Recorder(
            on_step=self._on_step,
            on_done=self._on_done,
            on_error=self._on_error,
            rules=self.rules,
        )
        self.runner = Runner(rules=self.rules)
        self._browser_ok = False
        self._active_recording_dir: Path | None = None
        self._review_data = None  # 整理页数据

        # ─── 多次录制状态 ───
        self._target_sessions = 1       # 用户选了几次（1 / 3 / 5）
        self._current_session = 1       # 正在录第几次
        self._session_records = []      # 每次录完的 steps 备份: [{session_index, steps: [...], step_count: N}]
        self._recording_url = ""        # 本批次的目标 URL（每个 session 共享）

        self._build_ui()
        self.after(300, self._init_login)
        self.after(800, self._bg_check_browser)

    # ════════════════════════════════════════
    #  UI 框架
    # ════════════════════════════════════════

    def _build_ui(self):
        # ── 顶栏：logo + 标题 + 右侧版本/检查更新/看教程 ──
        top = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=C_SIDE_BARTOP)
        top.pack(fill="x"); top.pack_propagate(False)
        # logo 红块 + 名称
        logo = ctk.CTkFrame(top, width=34, height=34, corner_radius=8, fg_color=C_RED)
        logo.pack(side="left", padx=(16, 8), pady=11); logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="好", font=(FN, 16, "bold"),
                     text_color="#fff").pack(expand=True)
        ctk.CTkLabel(top, text="好办法自动化", font=(FN, 17, "bold"),
                     text_color=C_TEXT).pack(side="left")
        # 顶栏底部 1px 分隔线
        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=C_BORDER).pack(fill="x")

        ctk.CTkButton(top, text="📖 查看教程", width=104, height=34,
                      font=F_SM, corner_radius=8,
                      fg_color="#f3f4f6", hover_color="#e5e7eb",
                      text_color=C_TEXT2, border_width=1, border_color=C_BORDER,
                      command=self._open_tutorial).pack(side="right", padx=(6, 16), pady=11)
        ctk.CTkButton(top, text="🔄 检查更新", width=104, height=34,
                      font=F_SM, corner_radius=8,
                      fg_color="#f3f4f6", hover_color="#e5e7eb",
                      text_color=C_TEXT2, border_width=1, border_color=C_BORDER,
                      command=self._manual_check_update).pack(side="right", padx=6, pady=11)
        ctk.CTkLabel(top, text=f"v{SOFTWARE_VERSION}", font=F_SM,
                     text_color=C_TEXT3).pack(side="right", padx=10)

        # ── 主体：左侧边栏 + 右侧内容区（接口兼容老 CTkTabview）──
        self.tabs = _SidebarTabs(self)
        self.tabs.pack(fill="both", expand=True)

        self._build_home()
        self._build_record()
        self._build_review()
        self._build_flows()
        self._build_jst_workspace()  # 🛒 聚水潭专区
        self._build_roadmap()
        self.tabs.set("首页")

        # 注：「重新登录(清除登录态)」是聚水潭专属功能（清的是 Edge 里聚水潭的登录态，
        #     不是本软件登录），放在边栏会让人误以为软件要登录，所以只放在聚水潭页里。

        # 底部状态栏
        self._build_footer()

    def _manual_check_update(self):
        """顶栏「检查更新」：后台拉取知识库/经验库版本并提示。"""
        try:
            if hasattr(self, "_refresh_kb_text"):
                self._refresh_kb_text()
            messagebox.showinfo("检查更新", "正在后台同步最新经验库，稍候片刻～")
        except Exception:
            pass

    # ── 公告相关方法保留为安全空操作 ──
    #    旧版顶部有每 80ms 重绘的滚动公告条，是界面卡顿的主因，已移除。
    #    保留以下方法名（其它地方仍会调用），但不再做任何重绘。
    def _build_announcement_bar(self):
        self._announcements = []
        self._ann_text_id = None

    def _ann_load_and_start(self):
        pass

    def _ann_start_scroll(self):
        pass

    def _ann_tick(self):
        pass

    def _build_footer(self):
        """底部状态栏：左侧状态 + 右侧版本/日期 + 官网链接"""
        footer = tk.Frame(self, bg="#f8f8f8", height=30)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Frame(self, bg=C_BORDER, height=1).pack(fill="x", side="bottom")

        self.status_label = tk.Label(
            footer, text="● 状态：就绪", font=(FN, 11),
            bg="#f8f8f8", fg=C_GREEN)
        self.status_label.pack(side="left", padx=14)

        link = tk.Label(footer, text="🌐 tools.haobanfa.online   ·   客服微信：18033086531",
                       font=(FN, 11), bg="#f8f8f8", fg="#64748b", cursor="hand2")
        link.pack(side="left", padx=14)
        def open_site(e):
            webbrowser.open(TUTORIAL_URL.replace("/tutorial", ""))
        link.bind("<Button-1>", open_site)

        tk.Label(footer, text=f"版本 v{SOFTWARE_VERSION}", font=(FN, 10),
                 bg="#f8f8f8", fg="#94a3b8").pack(side="right", padx=14)

    # ════════════════════════════════════════
    #  首页
    # ════════════════════════════════════════

    def _build_home(self):
        tab = self.tabs.add("首页")
        tab.configure(fg_color=C_BG)

        scroll = ctk.CTkScrollableFrame(tab, fg_color=C_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True)

        # 序列号 + 昵称（合并为一张紧凑信息卡，省出主区域空间）
        info = self._card(scroll); info.pack(fill="x", pady=(4, 10))
        row = ctk.CTkFrame(info, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(12, 2))

        # 左：序列号
        ctk.CTkLabel(row, text="设备序列号", font=F_SMB,
                     text_color=C_TEXT2).pack(side="left")
        ctk.CTkLabel(row, text=self.serial, font=(FN, 14, "bold"),
                     text_color=C_TEXT).pack(side="left", padx=(8, 6))
        ctk.CTkButton(row, text="复制", width=48, height=26, font=F_SM,
                      corner_radius=5, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self._copy_serial).pack(side="left")

        # 右：昵称（从右往左排：按钮 → 值 → 标签）
        self.nickname_btn = ctk.CTkButton(row, text="修改昵称",
                                           width=84, height=26, font=F_SM,
                                           corner_radius=5, fg_color=C_GREEN,
                                           hover_color=C_GREEN_H,
                                           command=self._edit_nickname)
        self.nickname_btn.pack(side="right")
        self.nickname_label = ctk.CTkLabel(row, text="(未设置)",
                                            font=(FN, 14, "bold"),
                                            text_color=C_TEXT2)
        self.nickname_label.pack(side="right", padx=(0, 8))
        ctk.CTkLabel(row, text="👤 昵称", font=F_SMB,
                     text_color=C_TEXT2).pack(side="right", padx=(0, 6))

        # 第二行小字说明（nickname_hint 供 _show_profile 动态更新）
        sub = ctk.CTkFrame(info, fg_color="transparent")
        sub.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(sub, text="续费时把序列号提供给客服　·　",
                     font=F_SM, text_color=C_TEXT3).pack(side="left")
        self.nickname_hint = ctk.CTkLabel(sub, text="设置昵称方便客服识别你",
                                          font=F_SM, text_color=C_TEXT3)
        self.nickname_hint.pack(side="left")

        # 次数（初始给有意义的默认值，避免登录前显示空的 "-" 让用户以为坏了）
        st = self._card(scroll); st.pack(fill="x", pady=(0, 10))
        row = ctk.CTkFrame(st, fg_color="transparent"); row.pack(fill="x", padx=10, pady=18)
        self.free_val = self._stat(row, "免费次数", "5")
        self.paid_val = self._stat(row, "付费次数", "0")
        self.total_val = self._stat(row, "可用总计", "5")

        # 环境
        env = self._card(scroll); env.pack(fill="x", pady=(0, 10))
        er = ctk.CTkFrame(env, fg_color="transparent"); er.pack(fill="x", padx=18, pady=14)
        el = ctk.CTkFrame(er, fg_color="transparent"); el.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(el, text="运行环境（系统 Edge）", font=F_BODY, text_color=C_TEXT).pack(anchor="w")
        self.env_status = ctk.CTkLabel(el, text="检测中...", font=F_SM, text_color=C_TEXT3,
                                        justify="left")
        self.env_status.pack(anchor="w", pady=(2, 0))
        self.env_btn = ctk.CTkButton(er, text="重新检测", width=110, height=34,
                                     font=F_BTN, corner_radius=7,
                                     fg_color=C_GREEN, hover_color=C_GREEN_H,
                                     command=self._setup_env)
        self.env_btn.pack(side="right")

        # 版本信息（软件 + 经验库）
        kb = self._card(scroll); kb.pack(fill="x", pady=(0, 10))
        kr = ctk.CTkFrame(kb, fg_color="transparent"); kr.pack(fill="x", padx=18, pady=14)
        kl = ctk.CTkFrame(kr, fg_color="transparent"); kl.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(kl, text="📦 软件版本", font=F_BODY,
                     text_color=C_TEXT).pack(anchor="w")
        self.sw_ver_label = ctk.CTkLabel(kl, text=f"V{SOFTWARE_VERSION}",
            font=(FN, 16, "bold"), text_color=C_GREEN)
        self.sw_ver_label.pack(anchor="w", pady=(2, 8))

        ctk.CTkLabel(kl, text="🧠 经验库版本（AI 识别能力，服务器自动更新）",
                     font=F_BODY, text_color=C_TEXT).pack(anchor="w")
        self.kb_ver_label = ctk.CTkLabel(kl, text="加载中...",
            font=(FN, 16, "bold"), text_color=C_BLUE)
        self.kb_ver_label.pack(anchor="w", pady=(2, 2))

        # 已掌握经验数 + 查看按钮
        kb_local = ctk.CTkFrame(kl, fg_color="transparent")
        kb_local.pack(anchor="w", fill="x")
        self.kb_local_label = ctk.CTkLabel(kb_local,
            text=f"💡 本地已掌握 {self.patterns_lib.count} 条经验",
            font=F_SM, text_color=C_TEXT2)
        self.kb_local_label.pack(side="left")
        ctk.CTkButton(kb_local, text="查看经验列表",
            width=110, height=24, font=F_SM, corner_radius=5,
            fg_color="transparent", border_width=1,
            border_color=C_BORDER, text_color=C_TEXT2,
            hover_color="#e0e0e0",
            command=self._show_patterns_list).pack(side="left", padx=(8, 0))

        self.kb_status = ctk.CTkLabel(kl, text="",
            font=F_SM, text_color=C_TEXT3,
            wraplength=400, justify="left")
        self.kb_status.pack(anchor="w", pady=(2, 0))

        kb_btns = ctk.CTkFrame(kr, fg_color="transparent")
        kb_btns.pack(side="right")
        self.diag_btn = ctk.CTkButton(kb_btns, text="🔧 通讯诊断", width=110, height=34,
                                       font=F_BTN, corner_radius=7,
                                       fg_color="#f97316", hover_color="#ea580c",
                                       command=self._open_diag)
        self.diag_btn.pack(side="left", padx=(0, 6))
        self.kb_btn = ctk.CTkButton(kb_btns, text="检查更新", width=110, height=34,
                                    font=F_BTN, corner_radius=7,
                                    fg_color=C_BLUE, hover_color="#1d4ed8",
                                    command=self._update_kb)
        self.kb_btn.pack(side="left")

        # 充值续费（支付宝收款码 + 序列号后 8 位备注）
        self._build_pay_card(scroll)

        # 微信
        wx = self._card(scroll); wx.pack(fill="x", pady=(0, 10))
        wr = ctk.CTkFrame(wx, fg_color="transparent"); wr.pack(fill="x", padx=18, pady=14)
        wl = ctk.CTkFrame(wr, fg_color="transparent"); wl.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(wl, text="💬 联系作者", font=F_BODY,
                     text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(wl, text=f"微信：{WECHAT}（备注：自动化软件用户）",
                     font=F_SM, text_color=C_TEXT2).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(wl, text="遇到问题、续费、定制需求请加微信",
                     font=F_SM, text_color=C_TEXT3).pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(wr, text="复制微信", width=92, height=34, font=F_BTN,
                      corner_radius=7, fg_color=C_GREEN,
                      hover_color=C_GREEN_H,
                      command=self._copy_wechat).pack(side="right")

        # 连接状态
        br = ctk.CTkFrame(scroll, fg_color="transparent")
        br.pack(fill="x", pady=(0, 4))
        self.conn_dot = ctk.CTkLabel(br, text="●", font=("", 10), text_color=C_TEXT3)
        self.conn_dot.pack(side="left")
        self.conn_label = ctk.CTkLabel(br, text=" 正在连接...", font=F_SM, text_color=C_TEXT3)
        self.conn_label.pack(side="left")
        ctk.CTkButton(br, text="刷新", width=56, height=26, font=F_SM,
                      corner_radius=5, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self._refresh).pack(side="right")

    def _stat(self, parent, title, value):
        f = ctk.CTkFrame(parent, fg_color="transparent"); f.pack(side="left", expand=True)
        lbl = ctk.CTkLabel(f, text=value, font=F_NUM, text_color=C_GREEN); lbl.pack()
        ctk.CTkLabel(f, text=title, font=F_SM, text_color=C_TEXT3).pack()
        f._v = lbl
        return f

    # ════════════════════════════════════════
    #  录制
    # ════════════════════════════════════════

    def _build_record(self):
        tab = self.tabs.add("录制")
        tab.configure(fg_color=C_BG)

        # URL
        c1 = self._card(tab); c1.pack(fill="x", pady=(6, 10))
        ctk.CTkLabel(c1, text="目标网址", font=F_BODY,
                     text_color=C_TEXT).pack(anchor="w", padx=18, pady=(14, 5))
        r = ctk.CTkFrame(c1, fg_color="transparent"); r.pack(fill="x", padx=18, pady=(0, 8))
        self.url_input = ctk.CTkEntry(r, placeholder_text="https://example.com",
                                       height=38, font=F_SM, corner_radius=7,
                                       fg_color="#fafafa", border_color=C_BORDER,
                                       border_width=1)
        self.url_input.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # 录制次数下拉（多次录制 → AI 学到更稳的选择器）
        self.recording_count_var = ctk.StringVar(value="1 次")
        self.recording_count_menu = ctk.CTkOptionMenu(
            r,
            variable=self.recording_count_var,
            values=["1 次", "3 次", "5 次"],
            width=82, height=38, font=F_BTN, corner_radius=7,
            fg_color="#1f2937", button_color="#374151",
            button_hover_color="#4b5563",
        )
        self.recording_count_menu.pack(side="right", padx=(0, 8))

        self.rec_btn = ctk.CTkButton(r, text="开始录制", width=100, height=38,
                                     font=F_BTN, corner_radius=7,
                                     fg_color=C_GREEN, hover_color=C_GREEN_H,
                                     command=self._start_rec)
        self.rec_btn.pack(side="right")

        ctk.CTkLabel(
            c1,
            text="💡 录制超过 10 步或涉及上传文件 / 图片时，建议选「3 次」或「5 次」让 AI 学到更稳的脚本。Ctrl+Shift+X 可对鼠标当前位置截图。",
            font=F_SM,
            text_color=C_ORANGE,
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        # 实时操作
        c2 = self._card(tab); c2.pack(fill="both", expand=True, pady=(0, 10))
        hr = ctk.CTkFrame(c2, fg_color="transparent")
        hr.pack(fill="x", padx=18, pady=(12, 4))
        ctk.CTkLabel(hr, text="实时操作流", font=F_BODY,
                     text_color=C_TEXT).pack(side="left")
        self.step_count_label = ctk.CTkLabel(hr, text=f"目标 {MAX_STEPS} 步以内",
                                             font=F_SM, text_color=C_TEXT3)
        self.step_count_label.pack(side="right")

        # 实时操作流：可编辑行列表（每行带备注输入框）
        # 性能考量：用原生 tk.Frame 行 + CTkScrollableFrame 容器
        self.steps_box = ctk.CTkScrollableFrame(c2,
                                                 corner_radius=7, fg_color="#fafafa",
                                                 border_color=C_BORDER, border_width=1)
        self.steps_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        # 记录每行的备注 Entry 引用，结束录制时回写到 step["user_note"]
        self._step_note_entries: dict[int, tk.Entry] = {}

        # 底部
        br = ctk.CTkFrame(tab, fg_color="transparent"); br.pack(fill="x")
        self.rec_status = ctk.CTkLabel(br, text="点击「开始录制」打开浏览器，浏览器内点击「完成」后进入整理页",
                                       font=F_SM, text_color=C_TEXT3)
        self.rec_status.pack(side="left")

    # ════════════════════════════════════════
    #  整理（核心新功能）
    # ════════════════════════════════════════

    def _build_review(self):
        tab = self.tabs.add("整理")
        tab.configure(fg_color=C_BG)

        # 顶部提示
        tip = ctk.CTkFrame(tab, fg_color="#dbeafe", corner_radius=8,
                          border_color="#93c5fd", border_width=1)
        tip.pack(fill="x", pady=(6, 8))
        ctk.CTkLabel(tip, text=(
            "ℹ️  此脚本会被反复循环执行（每行 Excel 数据 = 一次循环）\n"
            "    登录、注册等一次性操作请取消勾选，否则每次循环都会重复执行"
        ), font=F_SM, text_color="#1e40af",
           justify="left").pack(anchor="w", padx=14, pady=10)

        # 计数 + 操作按钮
        hr = ctk.CTkFrame(tab, fg_color="transparent"); hr.pack(fill="x", pady=(0, 6))
        self.review_count = ctk.CTkLabel(hr, text=f"已选 0 / {MAX_STEPS} 步",
                                          font=F_BODY, text_color=C_TEXT)
        self.review_count.pack(side="left")
        ctk.CTkButton(hr, text="全选", width=60, height=28, font=F_SM,
                      corner_radius=5, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=lambda: self._toggle_all(True)
                      ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(hr, text="全不选", width=64, height=28, font=F_SM,
                      corner_radius=5, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=lambda: self._toggle_all(False)
                      ).pack(side="right", padx=(4, 0))

        # 列表
        self.review_list = ctk.CTkScrollableFrame(
            tab, corner_radius=10, fg_color=C_CARD,
            border_color=C_BORDER, border_width=1)
        self.review_list.pack(fill="both", expand=True, pady=(0, 8))

        # 底部
        br = ctk.CTkFrame(tab, fg_color="transparent"); br.pack(fill="x")
        self.review_status = ctk.CTkLabel(br, text="", font=F_SM, text_color=C_TEXT3)
        self.review_status.pack(side="left")

        # 生成按钮（右）
        self.gen_btn = ctk.CTkButton(br, text="生成脚本 + Excel 模板",
                                     width=200, height=40, font=F_BTN,
                                     corner_radius=7, state="disabled",
                                     fg_color=C_GREEN, hover_color=C_GREEN_H,
                                     command=self._gen_script)
        self.gen_btn.pack(side="right")

        # AI 模型档位（生成按钮左侧）
        # 映射：显示名 → backend model_key
        self._model_key_map = {
            "代码生成（默认）": "code",
            "平衡（带视觉）": "balanced",
            "强档（慢/贵）": "strong",
            "快速（便宜）": "fast",
            "视觉专用": "vision",
        }
        self.model_picker = ctk.CTkOptionMenu(
            br,
            values=list(self._model_key_map.keys()),
            width=160, height=40, font=F_BTN, corner_radius=7,
            fg_color="#1f2937", button_color="#374151",
            button_hover_color="#4b5563",
        )
        self.model_picker.set("代码生成（默认）")
        self.model_picker.pack(side="right", padx=(0, 10))
        ctk.CTkLabel(br, text="AI 模型档位：", font=F_SM,
                     text_color=C_TEXT3).pack(side="right", padx=(0, 6))

        # 默认空状态
        self._show_review_empty()

    def _show_review_empty(self):
        for w in self.review_list.winfo_children():
            w.destroy()
        empty = ctk.CTkFrame(self.review_list, fg_color="transparent")
        empty.pack(fill="both", expand=True, pady=60)
        ctk.CTkLabel(empty, text="暂无录制数据", font=F_BODY,
                     text_color=C_TEXT3).pack()
        ctk.CTkLabel(empty, text="去「录制」标签页录制操作后会自动跳转到这里",
                     font=F_SM, text_color=C_TEXT3).pack(pady=(4, 0))

    def _show_review(self, data: list):
        self._review_data = data
        for w in self.review_list.winfo_children():
            w.destroy()

        if not data:
            self._show_review_empty()
            self.gen_btn.configure(state="disabled")
            return

        for idx, item in enumerate(data):
            self._review_row(idx, item)

        self._update_review_count()

    def _review_row(self, idx: int, item: dict):
        # 使用纯原生 tk 控件以提升性能（50+ 行不卡）
        card = tk.Frame(self.review_list, bg=C_CARD,
                        highlightthickness=1, highlightbackground=C_BORDER,
                        bd=0)
        card.pack(fill="x", padx=6, pady=(0, 5))
        item["_card"] = card

        # 顶行：复选框 + 类型标签 + 步骤号 + 摘要
        head = tk.Frame(card, bg=C_CARD)
        head.pack(fill="x", padx=10, pady=(8, 2))

        var = tk.BooleanVar(value=item["selected"])
        item["_var"] = var

        cb = tk.Checkbutton(head, variable=var, bg=C_CARD,
                           activebackground=C_CARD,
                           selectcolor="#fff",
                           command=lambda i=idx: self._on_toggle(i))
        cb.pack(side="left")

        at = item["action_type"]
        label_color = {
            "input":  "#2563eb", "select": "#7c3aed",
            "check":  "#0891b2", "upload": "#ea580c",
            "click":  "#16a34a",
            "scroll": "#0c4a6e",
        }.get(at, "#64748b")

        tk.Label(head, text=f" {item['action_label']} ",
                 font=F_SM, fg="#fff", bg=label_color,
                 padx=4).pack(side="left", padx=(4, 4))
        tk.Label(head, text=f"第 {item['step_index']} 步",
                 font=F_SM, fg=C_TEXT3, bg=C_CARD).pack(side="left")

        # 摘要
        main = self._step_summary(item)
        tk.Label(card, text=main, font=F_SMB,
                 fg=C_TEXT, bg=C_CARD, justify="left",
                 wraplength=620, anchor="w").pack(anchor="w", padx=10, pady=(2, 4))

        # 字段名称 (输入类 + 下拉菜单 + 上传)
        if at in ("input", "select", "select_option", "upload"):
            er = tk.Frame(card, bg=C_CARD)
            er.pack(fill="x", padx=10, pady=(0, 4))
            tk.Label(er, text="字段名称:", font=F_SM,
                     fg=C_TEXT2, bg=C_CARD, width=10,
                     anchor="w").pack(side="left")
            ex_entry = tk.Entry(er, font=F_SM,
                               bg="#fafafa", fg=C_TEXT,
                               relief="solid", bd=1,
                               highlightthickness=0,
                               insertbackground=C_TEXT)
            ex_entry.insert(0, item.get("excel_column", ""))
            ex_entry.pack(side="left", fill="x", expand=True, ipady=4)
            item["_excel_entry"] = ex_entry
            # 不同类型的提示
            if at == "select_option":
                hint = " → 下拉选项文字（Excel 列）"
                hint_color = C_BLUE
            elif at == "upload":
                hint = " → 文件 / 文件夹路径（Excel 填本地路径）"
                hint_color = "#ea580c"
            else:
                hint = " → 出现在 Excel 表"
                hint_color = C_TEXT3
            tk.Label(er, text=hint,
                     font=(FN, 10), fg=hint_color, bg=C_CARD
                     ).pack(side="left", padx=(4, 0))

            # 显示录制时的原值（让用户知道这条记录的是什么）
            recorded = item.get("value") or item.get("text") or ""
            recorded = str(recorded).strip()
            if recorded:
                if item.get("input_type") == "password":
                    recorded = "******"
                if len(recorded) > 40:
                    recorded = recorded[:40] + "..."
                rec_row = tk.Frame(card, bg=C_CARD)
                rec_row.pack(fill="x", padx=10, pady=(0, 4))
                tk.Label(rec_row, text=" ", bg=C_CARD,
                         width=10).pack(side="left")
                tk.Label(rec_row,
                         text=f"📝 录制时选的/填的：{recorded}",
                         font=(FN, 10), fg="#78350F",
                         bg="#FEF3C7", padx=8, pady=2,
                         anchor="w").pack(side="left", fill="x", expand=True)

            # 上传类型额外提示
            if at == "upload":
                # 如果是从 input[type=file].change 自动识别的，加个绿色徽章
                raw = item.get("_raw") or {}
                auto_detected = bool(raw.get("triggers_file_chooser"))
                files_count = raw.get("files_count_recorded", 0)

                if auto_detected:
                    badge_row = tk.Frame(card, bg=C_CARD)
                    badge_row.pack(fill="x", padx=10, pady=(0, 4))
                    tk.Label(badge_row, text=" ", bg=C_CARD,
                             width=10).pack(side="left")
                    badge_text = "✓ 自动识别：点这一步会打开资源管理器"
                    if files_count:
                        badge_text += f"（录制时选了 {files_count} 个文件）"
                    tk.Label(badge_row,
                             text=badge_text,
                             font=(FN, 10, "bold"), fg="#fff",
                             bg="#16a34a", padx=8, pady=3,
                             anchor="w").pack(side="left")

                up_row = tk.Frame(card, bg=C_CARD)
                up_row.pack(fill="x", padx=10, pady=(0, 4))
                tk.Label(up_row, text=" ", bg=C_CARD,
                         width=10).pack(side="left")
                tk.Label(up_row,
                         text='💡 单文件填路径 D:\\图片\\商品1.jpg；填文件夹 D:\\图片\\sku001 会自动上传里面所有图片',
                         font=(FN, 10), fg="#ea580c",
                         bg="#fff7ed", padx=8, pady=2,
                         anchor="w").pack(side="left", fill="x", expand=True)

        # 解释/描述
        dr = tk.Frame(card, bg=C_CARD)
        dr.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(dr, text="解释:", font=F_SM,
                 fg=C_TEXT2, bg=C_CARD, width=10,
                 anchor="w").pack(side="left")
        d_entry = tk.Entry(dr, font=F_SM,
                          bg="#fafafa", fg=C_TEXT,
                          relief="solid", bd=1,
                          highlightthickness=0,
                          insertbackground=C_TEXT)
        d_entry.insert(0, item.get("description", ""))
        d_entry.pack(side="left", fill="x", expand=True, ipady=4)
        d_count = tk.Label(dr, text=f"{len(item.get('description', ''))}/140",
                          font=(FN, 10), fg=C_TEXT3, bg=C_CARD, width=8)
        d_count.pack(side="left", padx=(4, 0))
        item["_desc_entry"] = d_entry
        item["_desc_count"] = d_count

        def on_desc_change(event=None):
            v = d_entry.get()
            if len(v) > 140:
                d_entry.delete(140, "end")
                v = d_entry.get()
            d_count.configure(text=f"{len(v)}/140")

        d_entry.bind("<KeyRelease>", on_desc_change)

        self._apply_card_state(item)

    def _step_summary(self, item: dict) -> str:
        at = item["action_type"]
        label = item.get("label", "").strip()
        text = item.get("text", "").strip()
        val = str(item.get("value", ""))
        if at == "input":
            t = label or "字段"
            show = val if item.get("input_type") != "password" else "*" * len(val)
            return f"在「{t}」输入  →  {show}"
        if at == "select":
            t = label or "下拉框"
            return f"在「{t}」选择  →  {val or text}"
        if at == "select_option":
            t = text or label or "选项"
            return f"选择菜单项  →  {t}"
        if at == "check":
            t = label or text or "复选框"
            return f"勾选「{t}」"
        if at == "upload":
            t = label or "上传框"
            return f"在「{t}」上传文件"
        if at == "scroll":
            delta = item.get("_raw", {}).get("scroll_delta", {})
            dy = delta.get("y", 0)
            dx = delta.get("x", 0)
            if abs(dy) >= abs(dx):
                d = "↓" if dy > 0 else "↑"
                return f"滚动  {d}  {abs(dy)}px"
            else:
                d = "→" if dx > 0 else "←"
                return f"滚动  {d}  {abs(dx)}px"
        # click
        t = text or label or "元素"
        if len(t) > 30: t = t[:30] + "..."
        return f"点击  →  {t}"

    def _apply_card_state(self, item: dict):
        card = item.get("_card")
        if not card:
            return
        if item["_var"].get():
            card.configure(bg=C_CARD, highlightbackground=C_BORDER)
            for w in card.winfo_children():
                self._recolor_bg(w, C_CARD)
        else:
            card.configure(bg="#ececec", highlightbackground="#dcdcdc")
            for w in card.winfo_children():
                self._recolor_bg(w, "#ececec")

    def _recolor_bg(self, widget, bg: str):
        try:
            cls = widget.winfo_class()
            if cls in ("Frame", "Label", "Checkbutton"):
                widget.configure(bg=bg)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._recolor_bg(child, bg)

    def _on_toggle(self, idx: int):
        item = self._review_data[idx]
        item["selected"] = item["_var"].get()
        self._apply_card_state(item)
        self._update_review_count()

    def _toggle_all(self, on: bool):
        if not self._review_data:
            return
        for item in self._review_data:
            item["selected"] = on
            item["_var"].set(on)
            self._apply_card_state(item)
        self._update_review_count()

    def _update_review_count(self):
        if not self._review_data:
            return
        n = sum(1 for x in self._review_data if x["_var"].get())
        if n > MAX_STEPS:
            self.review_count.configure(
                text=f"已选 {n} / {MAX_STEPS} 步  ❌ 超出 {n-MAX_STEPS} 步",
                text_color=C_RED)
            self.gen_btn.configure(state="disabled")
            self.review_status.configure(
                text=f"请再取消 {n-MAX_STEPS} 步才能生成",
                text_color=C_RED)
        elif n == 0:
            self.review_count.configure(text=f"已选 0 / {MAX_STEPS} 步",
                                         text_color=C_TEXT3)
            self.gen_btn.configure(state="disabled")
            self.review_status.configure(text="至少选择一步", text_color=C_TEXT3)
        else:
            self.review_count.configure(text=f"已选 {n} / {MAX_STEPS} 步  ✓",
                                         text_color=C_GREEN)
            self.gen_btn.configure(state="normal")
            cols = sum(1 for x in self._review_data
                      if x["_var"].get() and (x.get("_excel_entry")
                      and x["_excel_entry"].get().strip()))
            self.review_status.configure(
                text=f"将生成 {n} 条指令" + (f"，{cols} 个 Excel 列" if cols else ""),
                text_color=C_TEXT3)

    # ════════════════════════════════════════
    #  我的流程
    # ════════════════════════════════════════

    def _build_roadmap(self):
        """功能预告页（画饼）"""
        tab = self.tabs.add("功能预告")
        tab.configure(fg_color=C_BG)

        scroll = ctk.CTkScrollableFrame(tab, fg_color=C_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="🚀 软件正在持续进化",
                     font=(FN, 18, "bold"), text_color=C_TEXT
                     ).pack(anchor="w", pady=(6, 4))
        ctk.CTkLabel(scroll,
            text="未来将支持更多办公场景的自动化，让重复劳动一键完成",
            font=F_SM, text_color=C_TEXT3
            ).pack(anchor="w", pady=(0, 14))

        # 已上线
        self._roadmap_section(scroll, "✅ 已上线", [
            ("浏览器自动化", "录制网页操作 → AI 生成脚本 → Excel 批量执行",
             "live", "100%"),
        ])

        # 开发中
        self._roadmap_section(scroll, "🛠️ 当前开发中", [
            ("Excel 自动化", "批量处理 Excel 表格、合并、拆分、公式计算、数据清洗",
             "dev", "60%"),
            ("Word 自动化", "批量生成合同/报告、模板替换、文档合并、PDF 转换",
             "dev", "40%"),
            ("PDF 自动化", "PDF 提取文字/表格、批量加水印、合并拆分、OCR 识别",
             "dev", "30%"),
            ("PPT 自动化", "批量制作演示文稿、模板换皮、内容自动填充",
             "dev", "20%"),
        ])

        # 规划中
        self._roadmap_section(scroll, "📋 规划中", [
            ("微信自动化", "微信群发、好友筛选、朋友圈批量管理（合规版）",
             "planned", "10%"),
            ("钉钉/飞书集成", "审批流自动化、会议纪要、考勤数据导出",
             "planned", "5%"),
            ("数据爬虫", "网页数据采集、定时抓取、结构化导出",
             "planned", "5%"),
            ("AI 助手集成", "Claude / GPT / 通义千问等模型批量调用、prompt 模板管理",
             "planned", "5%"),
        ])

        # CTA
        cta = self._card(scroll); cta.pack(fill="x", pady=(20, 10))
        cta_inner = ctk.CTkFrame(cta, fg_color="transparent")
        cta_inner.pack(fill="x", padx=20, pady=16)
        ctk.CTkLabel(cta_inner, text="💡 想第一时间用上新功能？",
                     font=F_BODY, text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(cta_inner,
            text=f"加微信 {WECHAT}（备注「自动化软件用户」）了解最新进展，新功能上线优先通知",
            font=F_SM, text_color=C_TEXT2).pack(anchor="w", pady=(4, 0))

    def _roadmap_section(self, parent, title: str, items: list):
        ctk.CTkLabel(parent, text=title, font=(FN, 14, "bold"),
                     text_color=C_TEXT).pack(anchor="w", pady=(12, 6))
        for name, desc, status, progress in items:
            card = self._card(parent); card.pack(fill="x", pady=(0, 8))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=12)

            head = ctk.CTkFrame(inner, fg_color="transparent")
            head.pack(fill="x")
            ctk.CTkLabel(head, text=name, font=(FN, 14, "bold"),
                         text_color=C_TEXT).pack(side="left")

            badge_text, badge_bg = {
                "live": ("已上线", "#16a34a"),
                "dev":  ("开发中", "#f97316"),
                "planned": ("规划中", "#94a3b8"),
            }.get(status, ("规划中", "#94a3b8"))
            ctk.CTkLabel(head, text=f" {badge_text} ",
                         font=F_SM, text_color="#fff",
                         fg_color=badge_bg, corner_radius=4
                         ).pack(side="left", padx=(8, 0))
            ctk.CTkLabel(head, text=progress, font=F_SM,
                         text_color=C_TEXT3).pack(side="right")

            ctk.CTkLabel(inner, text=desc, font=F_SM,
                         text_color=C_TEXT3, wraplength=600, justify="left"
                         ).pack(anchor="w", pady=(4, 0))

    # ════════════════════════════════════════════════════════════════
    #  🛒 聚水潭专区 —— 按业务模块拆分的直达入口
    #     - 独立 tab，独立 profile，独立 flows 目录（flows_jst/<模块>/）
    #     - 用 CDP 附加到用户真实 Edge，绕过自动化检测
    #     - 每个模块直达真正的子应用 URL，绕开工作台菜单导航
    # ════════════════════════════════════════════════════════════════
    JST_TARGET_URL = "https://www.erp321.com/epaas"  # 工作台兜底入口

    # ⭐ 模块配置：每个模块独立 URL + flows 子目录
    # 添加新模块只需在这里加一项
    JST_MODULES = [
        {
            "key": "goods",
            "label": "📦 商品管理",
            "desc": "商品上架、改价、调库存、信息维护",
            "url": "https://src.erp321.com/erp-web-group/erp-scm-goods/goodsInventoryManagement?tabAllow=camera&_c=jst-epaas&epaas=true",
            "ready": True,
            "color": "#16a34a",
        },
        {
            "key": "purchase",
            "label": "🛒 采购管理",
            "desc": "采购单、入库单、采购对账",
            "url": None,  # 待探查
            "ready": False,
            "color": "#0284c7",
        },
        {
            "key": "inventory",
            "label": "📊 库存管理",
            "desc": "盘点、调拨、入出库、库存查询",
            "url": None,
            "ready": False,
            "color": "#9333ea",
        },
        {
            "key": "orders",
            "label": "📋 订单管理",
            "desc": "订单查询、改物流、批量发货",
            "url": None,
            "ready": False,
            "color": "#f59e0b",
        },
        {
            "key": "finance",
            "label": "💰 财务管理",
            "desc": "对账、收支查询、报表",
            "url": None,
            "ready": False,
            "color": "#dc2626",
        },
        {
            "key": "other",
            "label": "🧪 其他 / 探查模式",
            "desc": "从工作台进入，手动导航到任意模块",
            "url": "https://www.erp321.com/epaas",
            "ready": True,
            "color": "#64748b",
        },
    ]

    def _build_jst_workspace(self):
        tab = self.tabs.add("🛒 聚水潭")
        tab.configure(fg_color=C_BG)
        # 加载持久化的 URL 覆盖（探查到的真实 URL）
        try:
            self._apply_jst_module_overrides()
        except Exception:
            pass
        self._render_jst_workspace_body(tab)

    def _render_jst_workspace_body(self, tab):
        """渲染聚水潭 tab 的内容（卡片 / 按钮 / 列表）—— 可被多次调用做刷新"""
        # ─── 顶部介绍卡片 ───
        intro = self._card(tab)
        intro.pack(fill="x", pady=(6, 10))
        ctk.CTkLabel(
            intro,
            text="🛒 聚水潭批量自动化专区",
            font=(FN, 18, "bold"),
            text_color="#0c4a6e",
        ).pack(anchor="w", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            intro,
            text=("这里专门针对聚水潭（erp321.com/epaas）的批量操作优化。"
                  "由于聚水潭会检测自动化浏览器，本专区使用你电脑上的真实 Edge "
                  "（独立 profile，不影响日常浏览），并自动注入 stealth 反检测脚本。"),
            font=F_SM,
            text_color=C_TEXT2,
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 8))
        ctk.CTkLabel(
            intro,
            text=("⚠ 首次进入需要在打开的 Edge 里手动登录聚水潭。"
                  "登录态会保存在专用 profile 里，之后免登录。"),
            font=F_SM,
            text_color="#9a3412",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        # ─── 业务模块卡片网格 ───
        mods_label = ctk.CTkLabel(
            tab,
            text="📂 选择业务模块直达录制",
            font=F_BODY,
            text_color=C_TEXT,
        )
        mods_label.pack(anchor="w", padx=4, pady=(0, 6))

        mods_grid = ctk.CTkFrame(tab, fg_color="transparent")
        mods_grid.pack(fill="x", pady=(0, 10))

        # 2 列 × N 行布局
        col_count = 2
        for idx, mod in enumerate(self.JST_MODULES):
            r, c = divmod(idx, col_count)
            self._build_jst_module_card(mods_grid, mod, r, c)
        for c in range(col_count):
            mods_grid.grid_columnconfigure(c, weight=1, uniform="modcol")

        # ─── 辅助操作（仅打开 Edge + 刷新） ───
        actions = ctk.CTkFrame(tab, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(
            actions,
            text="🌐 仅打开 Edge（不录制）",
            width=200, height=38,
            font=F_BTN,
            corner_radius=8,
            fg_color="#0369a1", hover_color="#075985",
            command=self._open_jst_browser_only,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="🔄 刷新流程列表",
            width=130, height=38,
            font=F_SM,
            corner_radius=8,
            fg_color="#e2e8f0", hover_color="#cbd5e1",
            text_color=C_TEXT,
            command=self._reload_jst_flows,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="🔓 重新登录（清除登录态）",
            width=180, height=38,
            font=F_SM,
            corner_radius=8,
            fg_color="#fef2f2", hover_color="#fee2e2",
            text_color="#991b1b",
            command=self._jst_reset_login,
        ).pack(side="left")

        # ─── 状态栏 ───
        self.jst_status = ctk.CTkLabel(
            tab,
            text="",
            font=F_SM,
            text_color=C_TEXT3,
            anchor="w",
        )
        self.jst_status.pack(fill="x", padx=4, pady=(0, 8))

        # ─── 聚水潭流程列表区 ───
        listc = self._card(tab)
        listc.pack(fill="both", expand=True)
        ctk.CTkLabel(
            listc,
            text="📋 已保存的聚水潭流程",
            font=F_BODY,
            text_color=C_TEXT,
        ).pack(anchor="w", padx=18, pady=(14, 8))

        self.jst_flows_box = ctk.CTkScrollableFrame(
            listc,
            corner_radius=7,
            fg_color="#fafafa",
            border_color=C_BORDER,
            border_width=1,
        )
        self.jst_flows_box.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # 初始加载一次
        self.after(500, self._reload_jst_flows)

    def _build_jst_module_card(self, parent, mod: dict, row: int, col: int):
        """构建一个模块卡片"""
        card = tk.Frame(parent, bg="white", highlightbackground=C_BORDER, highlightthickness=1)
        card.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)

        inner = tk.Frame(card, bg="white")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        # 顶部：标题 + 状态徽章
        head = tk.Frame(inner, bg="white")
        head.pack(fill="x")
        tk.Label(head, text=mod["label"], font=(FN, 13, "bold"),
                 fg=mod.get("color", C_TEXT), bg="white").pack(side="left")
        if mod["ready"]:
            tk.Label(head, text=" 已就绪 ", font=(FN, 9, "bold"),
                     fg="#fff", bg="#16a34a", padx=4).pack(side="right")
        else:
            tk.Label(head, text=" 待探查 ", font=(FN, 9, "bold"),
                     fg="#fff", bg="#94a3b8", padx=4).pack(side="right")

        # 描述
        tk.Label(inner, text=mod["desc"], font=(FN, 10),
                 fg=C_TEXT3, bg="white", anchor="w", justify="left",
                 wraplength=380).pack(anchor="w", pady=(4, 6))

        # URL（已就绪的模块显示部分 URL）
        if mod["ready"] and mod.get("url"):
            display_url = mod["url"]
            if len(display_url) > 75:
                display_url = display_url[:72] + "..."
            tk.Label(inner, text=display_url, font=("Consolas", 9),
                     fg="#94a3b8", bg="white", anchor="w",
                     wraplength=400).pack(anchor="w", pady=(0, 8))

        # 按钮区
        btns = tk.Frame(inner, bg="white")
        btns.pack(fill="x", pady=(4, 0))
        if mod["ready"]:
            tk.Button(
                btns, text="🎬 录制此模块流程",
                font=(FN, 10, "bold"), fg="#fff",
                bg=mod.get("color", "#16a34a"), bd=0,
                padx=12, pady=6, cursor="hand2",
                command=lambda m=mod: self._start_jst_module_recording(m)
            ).pack(side="left", padx=(0, 6))
            count = self._count_jst_module_flows(mod["key"])
            tk.Button(
                btns, text=f"📋 查看流程 ({count})",
                font=(FN, 10), fg=C_TEXT,
                bg="#f1f5f9", bd=0,
                padx=10, pady=6, cursor="hand2",
                command=lambda m=mod: self._show_jst_module_flows(m)
            ).pack(side="left")
        else:
            tk.Button(
                btns, text="🔍 探查此模块的真实 URL",
                font=(FN, 10), fg="#fff",
                bg="#0284c7", bd=0,
                padx=12, pady=6, cursor="hand2",
                command=lambda m=mod: self._discover_jst_module_url(m)
            ).pack(side="left")

    def _count_jst_module_flows(self, mod_key: str) -> int:
        """统计某模块下已录制的流程数"""
        try:
            d = JST_FLOWS_DIR / mod_key
            if not d.exists():
                return 0
            return sum(1 for p in d.iterdir() if p.is_dir())
        except Exception:
            return 0

    def _show_jst_module_flows(self, mod: dict):
        """筛选显示某模块的流程列表"""
        self._jst_filter_module = mod["key"]
        self._reload_jst_flows()
        self.jst_status.configure(
            text=f"📋 当前显示「{mod['label']}」模块的流程（共 {self._count_jst_module_flows(mod['key'])} 个）",
            text_color=C_TEXT2,
        )

    def _start_jst_module_recording(self, mod: dict):
        """从模块卡片启动录制 —— 直达该模块真实 URL"""
        if not mod.get("url"):
            messagebox.showinfo("待探查", f"「{mod['label']}」的真实入口 URL 还没探查，先点「🔍 探查此模块」")
            return
        self._jst_current_module = mod
        self._start_jst_recording_with_url(mod["url"], mod["key"], mod["label"])

    # ─── 模块 URL 持久化（探查到的 URL 存到 DATA_DIR/jst_modules.json） ───
    JST_MODULES_OVERRIDE_FILE = "jst_modules.json"

    def _load_jst_module_overrides(self) -> dict:
        try:
            f = DATA_DIR / self.JST_MODULES_OVERRIDE_FILE
            if f.exists():
                return json.loads(f.read_text(encoding="utf-8")) or {}
        except Exception:
            log.debug("load jst module overrides failed", exc_info=True)
        return {}

    def _save_jst_module_overrides(self, data: dict) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / self.JST_MODULES_OVERRIDE_FILE).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            log.debug("save jst module overrides failed", exc_info=True)

    def _apply_jst_module_overrides(self):
        """加载持久化的 URL 覆盖到 JST_MODULES（运行时合并）"""
        ovr = self._load_jst_module_overrides()
        for mod in self.JST_MODULES:
            if mod["key"] in ovr:
                url = ovr[mod["key"]].get("url")
                if url:
                    mod["url"] = url
                    mod["ready"] = True

    def _discover_jst_module_url(self, mod: dict):
        """探查模式：打开 Edge → 用户导航到目标页 → 粘 URL 回来 → 软件持久化"""
        proceed = messagebox.askokcancel(
            f"🔍 探查「{mod['label']}」入口",
            f"步骤：\n\n"
            f"1. 软件马上启动 Edge，落在聚水潭工作台\n"
            f"2. 你在 Edge 里手动导航到「{mod['label']}」页面\n"
            f"   （等页面完全加载，能看到主要功能）\n"
            f"3. 从 Edge 地址栏复制完整 URL\n"
            f"4. 关掉 Edge，回到本软件\n"
            f"5. 弹出对话框，把 URL 粘进去保存\n\n"
            f"点确定开始。"
        )
        if not proceed:
            return

        # 启动 Edge（不录制），关浏览器后弹 URL 输入框
        def _launch_then_ask():
            try:
                from playwright.sync_api import sync_playwright
                from app.browser import launch_cdp_attached_context

                pw = sync_playwright().start()
                edge_proc = None
                try:
                    self.after(0, lambda: self.jst_status.configure(
                        text="🚀 启动 Edge，请去导航到目标页面...", text_color=C_GREEN))
                    context, browser, edge_proc = launch_cdp_attached_context(
                        pw,
                        edge_profile_dir=JST_PROFILE_DIR,
                        initial_url=self.JST_TARGET_URL,
                    )
                    # 等用户关闭浏览器（关掉 = 探查完成）
                    last_known_url = ""
                    pages = context.pages
                    if pages:
                        try:
                            while not pages[0].is_closed():
                                try:
                                    last_known_url = pages[0].url or last_known_url
                                except Exception:
                                    pass
                                pages[0].wait_for_timeout(800)
                        except Exception:
                            pass

                    # 浏览器关了 → 弹输入框让用户粘 URL
                    # （把最后看到的 URL 作为默认值方便用户校对）
                    default_url = last_known_url
                    self.after(0, lambda u=default_url, m=mod: self._ask_save_module_url(m, u))
                except Exception as e:
                    self.after(0, lambda err=str(e): messagebox.showerror(
                        "探查启动失败", err))
                finally:
                    try: pw.stop()
                    except Exception: pass
                    self.after(0, lambda: self.jst_status.configure(
                        text="", text_color=C_TEXT3))
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror(
                    "探查启动失败", err))

        threading.Thread(target=_launch_then_ask, daemon=True).start()

    def _ask_save_module_url(self, mod: dict, default_url: str = ""):
        """弹个对话框让用户确认/编辑 URL 并保存"""
        dlg = tk.Toplevel(self)
        dlg.title(f"🔍 保存「{mod['label']}」入口 URL")
        dlg.geometry("780x300")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg="#f8fafc")

        tk.Label(dlg, text=f"🔍 保存「{mod['label']}」的真实入口 URL",
                 font=(FN, 14, "bold"), fg="#0c4a6e",
                 bg="#f8fafc").pack(anchor="w", padx=20, pady=(18, 4))

        tk.Label(dlg, text="把 Edge 地址栏的完整 URL 粘到下面（已自动填入最后看到的 URL）：",
                 font=(FN, 11), fg="#475569", bg="#f8fafc", wraplength=720,
                 justify="left").pack(anchor="w", padx=20, pady=(4, 10))

        # URL 输入框（多行，便于看长 URL）
        txt = tk.Text(dlg, height=5, width=90, font=("Consolas", 10),
                      bg="#fff", relief="solid", bd=1, wrap="word")
        txt.pack(padx=20, pady=(0, 10))
        if default_url:
            txt.insert("1.0", default_url)

        tk.Label(dlg,
                 text="💡 提示：URL 应该以 https://src.erp321.com/... 开头（聚水潭子应用），"
                      "不要保存 www.erp321.com/epaas 工作台 URL。",
                 font=(FN, 9), fg="#9a3412", bg="#f8fafc",
                 wraplength=720, justify="left"
                 ).pack(anchor="w", padx=20, pady=(0, 8))

        btn_row = tk.Frame(dlg, bg="#f8fafc")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        def _save():
            url = txt.get("1.0", "end").strip()
            if not url:
                messagebox.showwarning("URL 为空", "请输入 URL 再保存")
                return
            if not url.startswith("http"):
                messagebox.showwarning("URL 格式不对", "URL 必须以 http(s):// 开头")
                return
            # 持久化
            ovr = self._load_jst_module_overrides()
            ovr[mod["key"]] = {"url": url, "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            self._save_jst_module_overrides(ovr)
            # 内存里 JST_MODULES 也更新
            for m in self.JST_MODULES:
                if m["key"] == mod["key"]:
                    m["url"] = url
                    m["ready"] = True
                    break
            dlg.destroy()
            messagebox.showinfo(
                "✓ 已保存",
                f"「{mod['label']}」入口已保存：\n{url}\n\n"
                "聚水潭专区 tab 重新打开就能看到该模块变为「已就绪」。"
            )
            # 重建 JST tab UI 让卡片更新
            try:
                self._rebuild_jst_tab()
            except Exception:
                pass

        def _cancel():
            dlg.destroy()

        tk.Button(btn_row, text="取消", font=(FN, 10),
                  fg=C_TEXT, bg="#e2e8f0", bd=0,
                  padx=18, pady=8, cursor="hand2",
                  command=_cancel).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="✓ 保存为该模块入口", font=(FN, 11, "bold"),
                  fg="#fff", bg="#16a34a", bd=0,
                  padx=20, pady=8, cursor="hand2",
                  command=_save).pack(side="right")

    def _rebuild_jst_tab(self):
        """聚水潭 tab 模块卡片刷新（清空 + 重建）"""
        try:
            tab = self.tabs.tab("🛒 聚水潭")
            for w in tab.winfo_children():
                w.destroy()
            # 重建：把 _build_jst_workspace 里 tab 创建之后的逻辑摘出来重跑
            # 简单做法：把所有渲染逻辑放到内部辅助，由 _build_jst_workspace 和这里共用
            self._render_jst_workspace_body(tab)
        except Exception:
            log.debug("rebuild jst tab failed", exc_info=True)

    def _jst_reset_login(self):
        """清除聚水潭专用 profile（强制重新登录）"""
        confirm = messagebox.askyesno(
            "确认重新登录",
            f"将清除聚水潭专用浏览器 profile：\n  {JST_PROFILE_DIR}\n\n"
            "下次录制 / 运行需要重新登录聚水潭。\n\n"
            "确认清除？"
        )
        if not confirm:
            return
        try:
            if JST_PROFILE_DIR.exists():
                import shutil
                shutil.rmtree(JST_PROFILE_DIR, ignore_errors=True)
            messagebox.showinfo("已清除", "登录态已清除，下次录制 / 运行需重新登录。")
        except Exception as e:
            messagebox.showerror("清除失败", str(e))

    def _start_jst_recording(self):
        """启动通用聚水潭录制（从工作台入口） — 兼容旧入口，转到 _start_jst_recording_with_url"""
        self._start_jst_recording_with_url(self.JST_TARGET_URL, "other", "工作台 / 通用")

    def _start_jst_recording_with_url(self, target_url: str, module_key: str, module_label: str):
        """启动聚水潭录制：CDP 模式 + stealth + 直达指定模块 URL"""
        if self.recorder._running:
            messagebox.showwarning("已在录制", "已经有一个录制任务在跑了，先点完成再来。")
            return

        # 提示用户
        proceed = messagebox.askokcancel(
            f"🛒 启动「{module_label}」录制",
            f"即将启动真实 Edge 浏览器（防检测模式），直达：\n"
            f"  {target_url[:90]}{'...' if len(target_url) > 90 else ''}\n\n"
            "✅ 使用独立 profile，不影响你日常的 Edge\n"
            "✅ 登录态保留，再次录制 / 运行免登录\n"
            "✅ 录制目录：flows_jst/" + module_key + "/\n\n"
            "⚠ 启动前请先关闭使用相同 profile 的旧 Edge 窗口（如有）\n\n"
            "点确定开始。"
        )
        if not proceed:
            return

        # 清空旧录制 UI
        for w in self.steps_box.winfo_children():
            w.destroy()
        self._step_note_entries.clear()
        self.step_count_label.configure(text="0 步")

        # 多 session 状态初始化
        self._target_sessions = 1
        self._current_session = 1
        self._session_records = []
        self._recording_url = target_url

        # ⭐ 创建模块专属流程目录：flows_jst/<module_key>/录制_xxx/
        record_name = "录制_" + datetime.now().strftime("%m%d_%H%M%S")
        module_dir = JST_FLOWS_DIR / module_key
        module_dir.mkdir(parents=True, exist_ok=True)
        self._active_recording_dir = module_dir / record_name
        self._active_recording_dir.mkdir(parents=True, exist_ok=True)

        # 标记 JST + 模块信息（用于生成时元数据）
        self._current_recording_is_jst = True
        self._current_jst_module_key = module_key
        self._current_jst_module_label = module_label

        capture_dir = self._active_recording_dir / "screenshots"
        capture_dir.mkdir(parents=True, exist_ok=True)

        self.rec_btn.configure(state="disabled", text="录制中...")
        self.jst_status.configure(
            text=f"🎬 正在启动真实 Edge 直达「{module_label}」...",
            text_color=C_GREEN,
        )

        # 启动录制（防检测模式）
        self.recorder.start(
            target_url,
            capture_dir=capture_dir,
            browser_mode="stealth_cdp",
            cdp_profile_dir=Recorder.JST_PROFILE_DIR,
        )

        # 切到录制 tab 看实时步骤
        try:
            self.tabs.set("录制")
            self.rec_status.configure(
                text=f"🎬 「{module_label}」录制中。在真实 Edge 里操作；完成时点 ✅ 完成。",
                text_color=C_GREEN,
            )
        except Exception:
            pass

    def _open_jst_browser_only(self):
        """只开浏览器，不录制 —— 用于让用户先登录 / 探查页面结构"""
        proceed = messagebox.askokcancel(
            "🌐 仅打开 Edge",
            "将启动一个真实 Edge（带防检测）打开聚水潭，但不录制。\n\n"
            "用途：\n"
            "  • 首次登录聚水潭账号\n"
            "  • 手动探查页面结构 / 测试反爬是否绕过\n\n"
            "关闭浏览器即可结束。点确定开始。"
        )
        if not proceed:
            return

        # 用线程异步启动，避免阻塞 UI
        def _launch():
            try:
                from playwright.sync_api import sync_playwright
                from app.browser import launch_cdp_attached_context

                pw = sync_playwright().start()
                try:
                    self.after(0, lambda: self.jst_status.configure(
                        text="🚀 启动 Edge...", text_color=C_GREEN))
                    context, browser, edge_proc = launch_cdp_attached_context(
                        pw,
                        edge_profile_dir=JST_PROFILE_DIR,
                        initial_url=self.JST_TARGET_URL,
                    )
                    self.after(0, lambda: self.jst_status.configure(
                        text="✓ Edge 已打开。关闭浏览器窗口可结束。",
                        text_color=C_GREEN))

                    # 等用户关浏览器
                    pages = context.pages
                    if pages:
                        try:
                            while not pages[0].is_closed():
                                pages[0].wait_for_timeout(1000)
                        except Exception:
                            pass
                except Exception as e:
                    self.after(0, lambda e=e: messagebox.showerror(
                        "启动失败", f"无法启动 Edge：{e}"))
                finally:
                    try: pw.stop()
                    except Exception: pass
                    self.after(0, lambda: self.jst_status.configure(
                        text="", text_color=C_TEXT3))
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror(
                    "启动失败", f"{type(e).__name__}: {e}"))

        threading.Thread(target=_launch, daemon=True).start()

    def _reload_jst_flows(self):
        """重新加载聚水潭流程列表（按模块子目录扫描，并允许按模块过滤）"""
        for w in self.jst_flows_box.winfo_children():
            w.destroy()

        if not JST_FLOWS_DIR.exists():
            ctk.CTkLabel(
                self.jst_flows_box,
                text="📭 还没有聚水潭流程。点上面任意「🎬 录制此模块流程」开始。",
                font=F_SM,
                text_color=C_TEXT3,
            ).pack(anchor="w", padx=14, pady=14)
            return

        # 当前过滤模块（点「查看流程」时设置）
        filter_mod = getattr(self, "_jst_filter_module", None)

        # 收集所有模块下的流程：flows_jst/<module_key>/<录制目录>
        # 同时兼容老格式：flows_jst/<录制目录>（不在模块子目录下）
        all_flows = []  # [(flow_dir, module_key), ...]
        for entry in JST_FLOWS_DIR.iterdir():
            if not entry.is_dir():
                continue
            # 检查是否是模块目录（名字在 JST_MODULES 里）
            mod_keys = [m["key"] for m in self.JST_MODULES]
            if entry.name in mod_keys:
                # 模块目录：扫描下面的流程
                for sub in entry.iterdir():
                    if sub.is_dir():
                        all_flows.append((sub, entry.name))
            else:
                # 老格式：直接是流程目录
                all_flows.append((entry, ""))

        # 应用过滤
        if filter_mod:
            all_flows = [(d, k) for (d, k) in all_flows if k == filter_mod]

        # 按时间排序
        all_flows.sort(key=lambda t: t[0].stat().st_mtime, reverse=True)

        if not all_flows:
            tip = "📭 该模块下还没有流程，点对应模块的「🎬 录制此模块流程」开始。" \
                  if filter_mod else \
                  "📭 还没有聚水潭流程。"
            ctk.CTkLabel(
                self.jst_flows_box,
                text=tip,
                font=F_SM,
                text_color=C_TEXT3,
            ).pack(anchor="w", padx=14, pady=14)
            return

        # 如果有过滤，加个"显示全部"按钮
        if filter_mod:
            clear = tk.Frame(self.jst_flows_box, bg="#fef3c7")
            clear.pack(fill="x", padx=4, pady=4)
            tk.Label(clear, text=f"🔍 当前只看「{filter_mod}」模块",
                     font=(FN, 10), fg="#78350f", bg="#fef3c7"
                     ).pack(side="left", padx=8, pady=5)
            tk.Button(
                clear, text="清除过滤",
                font=(FN, 9), fg="#78350f", bg="#fde68a", bd=0,
                padx=8, pady=2, cursor="hand2",
                command=lambda: (setattr(self, "_jst_filter_module", None),
                                 self._reload_jst_flows())
            ).pack(side="right", padx=8, pady=4)

        for flow_dir, mod_key in all_flows:
            self._render_jst_flow_row(flow_dir, module_key=mod_key)

    def _rename_jst_flow(self, flow_dir: Path, cur_name: str):
        """给聚水潭流程改名：只改 meta.json 的 name（目录名保持不变，避免路径问题）。"""
        from tkinter import simpledialog
        new_name = simpledialog.askstring(
            "重命名流程", "请输入新的流程名称：",
            initialvalue=cur_name, parent=self)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name or new_name == cur_name:
            return
        meta_path = flow_dir / "meta.json"
        try:
            meta = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["name"] = new_name
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self._reload_jst_flows()
        except Exception as e:
            messagebox.showerror("改名失败", f"无法保存新名称：\n{e}")

    def _delete_jst_flow(self, flow_dir: Path, name: str):
        """删除聚水潭流程（整个目录），删前二次确认。"""
        if not messagebox.askyesno(
                "确认删除",
                f"确定删除流程「{name}」吗？\n\n此操作会删除整个流程文件夹，无法恢复。"):
            return
        try:
            shutil.rmtree(flow_dir)
            self._reload_jst_flows()
        except Exception as e:
            messagebox.showerror("删除失败", f"无法删除该流程：\n{e}")

    def _render_jst_flow_row(self, flow_dir: Path, module_key: str = ""):
        """渲染一行聚水潭流程卡片"""
        meta_path = flow_dir / "meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}

        name = meta.get("name") or flow_dir.name
        step_count = meta.get("step_count") or "?"
        created = meta.get("created") or ""
        # 模块信息（优先 meta.jst_module_key，其次 module_key 参数）
        mk = meta.get("jst_module_key") or module_key
        ml = meta.get("jst_module_label") or ""
        if not ml and mk:
            for m in self.JST_MODULES:
                if m["key"] == mk:
                    ml = m["label"]
                    break

        row = ctk.CTkFrame(self.jst_flows_box, fg_color="white", corner_radius=7)
        row.pack(fill="x", padx=4, pady=4)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        # 标题 + 模块徽章
        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=name, font=(FN, 13, "bold"),
                     text_color=C_TEXT, anchor="w").pack(side="left")
        if ml:
            # 查找模块颜色
            mod_color = "#94a3b8"
            for m in self.JST_MODULES:
                if m["key"] == mk:
                    mod_color = m.get("color", "#94a3b8")
                    break
            tk.Label(title_row, text=f" {ml} ",
                     font=(FN, 9, "bold"), fg="#fff",
                     bg=mod_color, padx=6
                     ).pack(side="left", padx=(8, 0))

        meta_str = f"{step_count} 步"
        if created:
            meta_str += f" · {created}"
        ctk.CTkLabel(left, text=meta_str, font=F_SM,
                     text_color=C_TEXT3, anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", padx=10, pady=8)
        ctk.CTkButton(
            right, text="▶ 运行", width=72, height=30,
            font=F_SM, corner_radius=6,
            fg_color="#16a34a", hover_color="#15803d",
            command=lambda fd=flow_dir: self._run_jst_flow(fd),
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            right, text="📂 文件夹", width=76, height=30,
            font=F_SM, corner_radius=6,
            fg_color="#e2e8f0", hover_color="#cbd5e1",
            text_color=C_TEXT,
            command=lambda fd=flow_dir: self._open_dir(fd),
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            right, text="✏️ 改名", width=66, height=30,
            font=F_SM, corner_radius=6,
            fg_color="#e2e8f0", hover_color="#cbd5e1",
            text_color=C_TEXT,
            command=lambda fd=flow_dir, nm=name: self._rename_jst_flow(fd, nm),
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            right, text="🗑 删除", width=66, height=30,
            font=F_SM, corner_radius=6,
            fg_color="#fee2e2", hover_color="#fecaca",
            text_color=C_RED,
            command=lambda fd=flow_dir, nm=name: self._delete_jst_flow(fd, nm),
        ).pack(side="right", padx=(6, 0))

    def _run_jst_flow(self, flow_dir: Path):
        """运行一个聚水潭流程（防检测模式）
        _run_flow 内部会根据 flow_dir 路径（含 flows_jst）或 meta.is_jst
        自动选择 stealth_cdp 浏览器模式，所以这里直接转发即可。"""
        if not (flow_dir / "dsl.json").exists():
            messagebox.showerror("无法运行", f"找不到 dsl.json：{flow_dir.name}")
            return
        # 把流程状态条切到聚水潭 tab 之外的"我的流程"页同款 status bar 上去显示
        try:
            self._run_flow(flow_dir)
        except Exception as e:
            log.error(f"_run_jst_flow 调用 _run_flow 异常: {e}", exc_info=True)
            messagebox.showerror("运行出错", f"{type(e).__name__}: {e}")

    def _build_flows(self):
        tab = self.tabs.add("我的流程")
        tab.configure(fg_color=C_BG)

        tr = ctk.CTkFrame(tab, fg_color="transparent"); tr.pack(fill="x", pady=(6, 8))
        ctk.CTkLabel(tr, text="保存的自动化流程", font=F_BODY,
                     text_color=C_TEXT).pack(side="left")
        ctk.CTkButton(tr, text="刷新", width=56, height=26, font=F_SM,
                      corner_radius=5, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self._load_flows).pack(side="right")

        # ⭐ 搜索框：按名称/URL 即时过滤
        sr = ctk.CTkFrame(tab, fg_color="transparent"); sr.pack(fill="x", pady=(0, 6))
        self._flow_search = ""
        self.flow_search_entry = ctk.CTkEntry(sr, placeholder_text="🔍 搜索流程名 / 网址",
                                              height=30, font=F_SM,
                                              corner_radius=6,
                                              border_color=C_BORDER, border_width=1)
        self.flow_search_entry.pack(fill="x", padx=0)
        def on_search(_e=None):
            self._flow_search = self.flow_search_entry.get().strip().lower()
            self._load_flows()
        self.flow_search_entry.bind("<KeyRelease>", on_search)

        # 分类筛选条
        self._flow_filter = "all"
        filt_row = ctk.CTkFrame(tab, fg_color="transparent")
        filt_row.pack(fill="x", pady=(0, 6))
        self._flow_filter_btns = {}
        for key, label in [
            ("all", "全部"), ("browser", "🌐 浏览器"),
            ("excel", "📊 Excel"), ("word", "📝 Word"),
            ("ps", "🎨 PS"), ("pdf", "📄 PDF"),
        ]:
            b = ctk.CTkButton(filt_row, text=label, width=72, height=26,
                              font=F_SM, corner_radius=4,
                              fg_color=C_GREEN if key == "all" else "#e0e0e0",
                              hover_color=C_GREEN_H if key == "all" else "#d0d0d0",
                              text_color="#fff" if key == "all" else C_TEXT2,
                              command=lambda k=key: self._set_flow_filter(k))
            b.pack(side="left", padx=(0, 4))
            self._flow_filter_btns[key] = b

        self.flow_list = ctk.CTkScrollableFrame(
            tab, corner_radius=10, fg_color=C_CARD,
            border_color=C_BORDER, border_width=1)
        self.flow_list.pack(fill="both", expand=True, pady=(0, 8))

        self.flow_status = ctk.CTkLabel(tab, text="", font=F_SM, text_color=C_TEXT3)
        self.flow_status.pack(anchor="w")
        self.after(500, self._load_flows)

    def _set_flow_filter(self, key: str):
        self._flow_filter = key
        for k, b in self._flow_filter_btns.items():
            active = (k == key)
            b.configure(
                fg_color=C_GREEN if active else "#e0e0e0",
                hover_color=C_GREEN_H if active else "#d0d0d0",
                text_color="#fff" if active else C_TEXT2,
            )
        self._load_flows()

    def _load_flows(self):
        # ⚡ 性能优化：批量构建期间不要让 tk 一直刷新
        # 1) 把容器临时取消 pack，避免每张卡都触发祖先重新布局
        # 2) 构建完成后再 pack 回来 → 一次性 layout
        try:
            self.flow_list.pack_forget()
        except Exception:
            pass

        for w in self.flow_list.winfo_children():
            w.destroy()
        dirs = [d for d in FLOWS_DIR.iterdir() if d.is_dir()]
        dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

        flt = getattr(self, "_flow_filter", "all")
        search = getattr(self, "_flow_search", "").strip().lower()
        cards = []
        for d in dirs:
            try:
                meta_p = d / "meta.json"
                if not meta_p.exists():
                    continue
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                cat = meta.get("category", "browser")
                if flt != "all" and cat != flt:
                    continue
                # 搜索过滤：流程名 / URL / 备注 任一匹配即可
                if search:
                    hay = " ".join([
                        str(meta.get("name", "")),
                        str(meta.get("url", "")),
                        str(meta.get("note", "")),
                        d.name,
                    ]).lower()
                    if search not in hay:
                        continue
                cards.append((d, meta))
            except Exception:
                continue

        try:
            if not cards:
                tip = "暂无流程\n去「录制」页创建一个" if flt == "all" else f"该分类下暂无流程"
                ctk.CTkLabel(self.flow_list, text=tip,
                             font=F_BODY, text_color=C_TEXT3).pack(pady=40)
                return

            for d, meta in cards:
                self._flow_card(d, meta)
        finally:
            # 不管成功失败都要把 flow_list 显示回来（参数和初始化时一致）
            try:
                self.flow_list.pack(fill="both", expand=True, pady=(0, 8))
            except Exception:
                pass

    def _flow_card(self, flow_dir: Path, meta: dict):
        card = ctk.CTkFrame(self.flow_list, corner_radius=8,
                            fg_color=C_CARD, border_color=C_BORDER,
                            border_width=1)
        card.pack(fill="x", padx=4, pady=(0, 6))

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        name = meta.get("name", flow_dir.name)
        steps = meta.get("step_count", 0)
        url = meta.get("url", "")
        created = meta.get("created", "")
        has_excel = (flow_dir / "数据模板.xlsx").exists()
        category = meta.get("category", "browser")
        category_label = meta.get("category_label", "浏览器")

        # 标题行：分类徽章 + 名称
        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(fill="x")
        cat_colors = {
            "browser": ("#dbeafe", "#1e40af"),
            "excel": ("#dcfce7", "#166534"),
            "word": ("#e0e7ff", "#3730a3"),
            "ps": ("#fce7f3", "#9d174d"),
            "pdf": ("#fee2e2", "#991b1b"),
        }
        bg, fg = cat_colors.get(category, ("#f3f4f6", "#374151"))
        ctk.CTkLabel(title_row, text=f" {category_label} ", font=F_SM,
                     text_color=fg, fg_color=bg, corner_radius=4
                     ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(title_row, text=name, font=(FN, 13, "bold"),
                     text_color=C_TEXT).pack(side="left")

        parts = [f"{steps}步"]
        if has_excel:
            parts.append("📊 含 Excel 数据")
        if url:
            parts.append(url[:30] + ("..." if len(url) > 30 else ""))
        if created:
            parts.append(created)
        # 软件版本
        if meta.get("software_version"):
            parts.append(f"v{meta['software_version']} 创建")
        ctk.CTkLabel(left, text=" · ".join(parts), font=F_SM,
                     text_color=C_TEXT3).pack(anchor="w", pady=(2, 0))

        # 用原生 tk.Button 替代 CTkButton（创建快 5-10 倍，肉眼无差别）
        btns = tk.Frame(card, bg=C_CARD)
        btns.pack(side="right", padx=10, pady=10)

        tk.Button(btns, text="运行", width=6, font=F_SM,
                  relief="flat", bd=0, cursor="hand2",
                  bg=C_GREEN, fg="#fff", activebackground=C_GREEN_H,
                  command=lambda p=flow_dir: self._run_flow(p)
                  ).pack(side="left", padx=(0, 4), ipady=2)
        # 重新生成: 用最新经验包重新生成 DSL,扣减 1 次次数
        tk.Button(btns, text="重新生成", width=8, font=F_SM,
                  relief="flat", bd=0, cursor="hand2",
                  bg="#bfdbfe", fg="#1e40af", activebackground="#93c5fd",
                  command=lambda p=flow_dir: self._regenerate_flow(p)
                  ).pack(side="left", padx=(0, 4), ipady=2)
        tk.Button(btns, text="改名", width=5, font=F_SM,
                  relief="flat", bd=0, cursor="hand2",
                  bg="#e0e0e0", fg=C_TEXT2, activebackground="#d0d0d0",
                  command=lambda p=flow_dir: self._rename_flow(p)
                  ).pack(side="left", padx=(0, 4), ipady=2)
        tk.Button(btns, text="打开目录", width=8, font=F_SM,
                  relief="flat", bd=0, cursor="hand2",
                  bg="#e0e0e0", fg=C_TEXT2, activebackground="#d0d0d0",
                  command=lambda p=flow_dir: self._open_dir(p)
                  ).pack(side="left", padx=(0, 4), ipady=2)

        is_paid = self.api.is_paid
        tk.Button(btns, text="反馈", width=5, font=F_SM,
                  relief="flat", bd=0, cursor="hand2" if is_paid else "arrow",
                  bg="#fef3c7" if is_paid else "#f0f0f0",
                  fg="#78350f" if is_paid else C_TEXT3,
                  activebackground="#fde68a" if is_paid else "#f0f0f0",
                  state="normal" if is_paid else "disabled",
                  command=lambda p=flow_dir: self._feedback(p)
                  ).pack(side="left", padx=(0, 4), ipady=2)

        tk.Button(btns, text="删除", width=5, font=F_SM,
                  relief="flat", bd=0, cursor="hand2",
                  bg="#f5f5f5", fg=C_RED, activebackground="#e5e5e5",
                  command=lambda p=flow_dir: self._del_flow(p)
                  ).pack(side="left", ipady=2)

    def _open_dir(self, flow_dir: Path):
        try:
            subprocess.Popen(["explorer", str(flow_dir)])
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def _rename_flow(self, flow_dir: Path):
        """重命名流程：改文件夹名 + 改 meta.json 里的 name"""
        from tkinter import simpledialog
        meta_p = flow_dir / "meta.json"
        old_name = flow_dir.name
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
        except Exception:
            meta = {}
        display_name = meta.get("name") or old_name

        new_name = simpledialog.askstring(
            "改名",
            f"给「{display_name}」起个新名字\n（只能用字母数字和中文，别加 / \\ : 这些）",
            initialvalue=display_name,
            parent=self,
        )
        if not new_name:
            return
        new_name = new_name.strip()
        # 清理非法字符
        import re
        new_name = re.sub(r'[\\/:*?"<>|]', '', new_name)
        if not new_name or new_name == display_name:
            return

        # 改 meta（这个一定改）
        meta["name"] = new_name
        try:
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        except Exception as e:
            messagebox.showerror("保存失败", f"meta.json 写入失败：{e}")
            return

        # 尝试改文件夹名（重名时给后缀）
        new_dir = flow_dir.parent / new_name
        i = 1
        while new_dir.exists() and new_dir != flow_dir:
            i += 1
            new_dir = flow_dir.parent / f"{new_name}_{i}"
        try:
            if new_dir != flow_dir:
                flow_dir.rename(new_dir)
        except Exception as e:
            # 文件夹名改不了不影响显示（meta.name 已改）
            log.info(f"文件夹改名失败（但 meta 已改）: {e}")

        self._load_flows()

    def _del_flow(self, flow_dir: Path):
        if not messagebox.askyesno("确认", f"确定删除「{flow_dir.name}」？"):
            return
        try:
            import shutil
            shutil.rmtree(flow_dir)
        except Exception as e:
            messagebox.showerror("删除失败", str(e))
        self._load_flows()

    def _run_flow(self, flow_dir: Path):
        try:
            dsl = load_dsl(flow_dir / "dsl.json")
            meta_p = flow_dir / "meta.json"
            meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
            init_url = meta.get("url", "")
        except Exception as e:
            messagebox.showerror("读取失败", f"无法加载流程：{e}")
            return

        # 判断流程类型
        needs_excel = any(
            ("from_excel" in a) for a in dsl.get("actions", [])
        )
        excel_path = None
        loop_count = 1
        loop_interval_ms = 2000

        if needs_excel:
            # 数据驱动模式：选 Excel
            tpl = flow_dir / "数据模板.xlsx"
            answer = messagebox.askyesnocancel(
                "选择数据文件",
                "此流程需要 Excel 数据文件。\n\n"
                "「是」=选择文件\n"
                "「否」=使用流程目录里的「数据模板.xlsx」\n"
                "「取消」=不运行"
            )
            if answer is None:
                return
            if answer:
                pth = filedialog.askopenfilename(
                    title="选择 Excel 数据文件",
                    filetypes=[("Excel 文件", "*.xlsx *.xls")])
                if not pth:
                    return
                excel_path = Path(pth)
            else:
                if not tpl.exists():
                    messagebox.showerror("找不到文件", "流程目录里没有「数据模板.xlsx」")
                    return
                excel_path = tpl

            try:
                rows = count_rows(excel_path)
            except Exception as e:
                messagebox.showerror("Excel 读取失败", str(e))
                return
            if rows == 0:
                messagebox.showwarning("没有数据",
                    "Excel 没有有效数据行，请在第 2 行起填写数据。")
                return
            if not messagebox.askyesno("确认运行",
                f"将循环执行 {rows} 行数据，是否继续？"):
                return
        else:
            # 纯操作模式（点击/截图/复制等不需要 Excel）：选运行次数
            dlg = RunOptionsDialog(self)
            self.wait_window(dlg)
            if dlg.cancelled:
                return
            loop_count = dlg.loop_count
            loop_interval_ms = dlg.interval_ms

        self.flow_status.configure(
            text="启动中，浏览器打开后请先完成登录/导航，再点浮层「开始工作」按钮",
            text_color=C_BLUE)

        def on_err(e):
            self.after(0, lambda: self.flow_status.configure(
                text=f"出错：{e}", text_color=C_RED))
            # 自动弹出错误反馈窗
            self.after(300, lambda: AutoErrorDialog(
                self, flow_dir, str(e), self.api).grab_set())

        # 全局默认用真实 Edge（CDP，无自动化痕迹）；聚水潭用独立 profile
        is_jst_flow = bool(meta.get("is_jst")) or str(flow_dir.resolve()).find("flows_jst") >= 0
        browser_mode = "stealth_cdp"
        cdp_profile_dir = Recorder.JST_PROFILE_DIR if is_jst_flow else None
        if is_jst_flow:
            self.flow_status.configure(
                text="🛒 聚水潭模式：将启动真实 Edge（防检测），请稍候...",
                text_color="#0c4a6e")

        self.runner.run(
            dsl, excel_path=excel_path, init_url=init_url,
            loop_count=loop_count, loop_interval_ms=loop_interval_ms,
            on_log=lambda s: self.after(0,
                lambda m=s: self.flow_status.configure(text=m, text_color=C_TEXT2)),
            on_done=lambda: self.after(0,
                lambda: self.flow_status.configure(text="✓ 运行完成！",
                                                    text_color=C_GREEN)),
            on_error=on_err,
            flow_dir=flow_dir,  # 人工接管时样本会存到这里
            browser_mode=browser_mode,  # 全局真实 Edge（无自动化痕迹）
            cdp_profile_dir=cdp_profile_dir,
        )

    # ════════════════════════════════════════
    #  重新生成流程 (用最新经验包重新生成 DSL,扣减 1 次次数)
    # ════════════════════════════════════════

    def _regenerate_flow(self, flow_dir: Path):
        """用最新经验包重新生成 DSL + Excel 模板,steps.json 保留不变。

        适用场景: 后端经验包升级后,旧的 dsl.json 跑不通,
        用户不想重新录制,直接基于原 steps.json 让 AI 用新经验重新生成。
        """
        steps_path = flow_dir / "steps.json"
        meta_path = flow_dir / "meta.json"
        if not steps_path.exists():
            messagebox.showerror(
                "无法重新生成",
                f"流程「{flow_dir.name}」缺少 steps.json,无法重新生成。\n"
                f"请用新版软件重新录制一次。"
            )
            return

        # 读取原 steps 和 meta
        try:
            steps = json.loads(steps_path.read_text(encoding="utf-8"))
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取流程数据:\n{e}")
            return

        # 当前只支持浏览器自动化
        category = meta.get("category", "browser")
        if category != "browser":
            messagebox.showerror(
                "暂不支持",
                f"该流程是「{meta.get('category_label', category)}」类型,\n"
                f"当前重新生成功能只支持「浏览器自动化」流程。"
            )
            return

        # 确认对话框
        if not messagebox.askyesno(
            "重新生成流程",
            f"将用最新经验包重新生成「{flow_dir.name}」的 DSL。\n\n"
            f"⚠️ 此操作会:\n"
            f"  · 扣减 1 次生成次数\n"
            f"  · 覆盖原有的 dsl.json 和 数据模板.xlsx\n"
            f"  · 保留原 steps.json (录制数据不变)\n\n"
            f"确定继续吗?"
        ):
            return

        flow_name = meta.get("name", flow_dir.name)
        init_url = meta.get("url", "")

        # 进度对话框
        dlg = ProgressDialog(self, "重新生成", "正在准备...")

        def worker():
            heartbeat_done = threading.Event()
            try:
                dlg.set_progress(10, "正在分析步骤...")
                selected_steps = [s for s in steps if s.get("selected", True)]
                if not selected_steps:
                    self.after(0, dlg.destroy)
                    self.after(100, lambda: messagebox.showerror(
                        "无步骤", "steps.json 里没有勾选的步骤,无法重新生成。"))
                    return
                api_steps = [self._step_for_api(s) for s in selected_steps]

                # 心跳进度条
                import time as _t
                start_ts = _t.time()

                def heartbeat():
                    while not heartbeat_done.is_set():
                        elapsed = _t.time() - start_ts
                        if elapsed < 60:
                            pct = 25 + int(elapsed / 60 * 50)
                        else:
                            pct = min(90, 75 + int((elapsed - 60) / 30 * 15))
                        try:
                            dlg.set_progress(pct, f"AI 推理中 · 已用 {int(elapsed)}s")
                        except Exception:
                            break
                        if heartbeat_done.wait(1):
                            break

                threading.Thread(target=heartbeat, daemon=True).start()

                def api_progress(stage_name, elapsed, detail):
                    try:
                        dlg.add_log(f"[{elapsed:5.1f}s] {stage_name}")
                    except Exception:
                        pass

                dlg.set_progress(25, "调用 AI(后台模型)...")
                dlg.add_log(f"━━━ 重新生成「{flow_name}」━━━")
                dlg.add_log(f"步骤数: {len(api_steps)}")
                dlg.add_log(f"经验包: 服务器最新版")

                try:
                    self.api.ensure_logged_in()
                except Exception:
                    pass

                # 重新生成沿用上次档位（如果有），否则默认 code
                try:
                    picked_label = self.model_picker.get()
                    model_key = self._model_key_map.get(picked_label, "code")
                except Exception:
                    model_key = "code"

                result = self.api.generate_script(
                    flow_name, api_steps,
                    notes=init_url,
                    category="browser",
                    model_key=model_key,
                    on_progress=api_progress
                )
                heartbeat_done.set()

                # 网络错误
                if result.get("_error"):
                    self.after(0, dlg.destroy)
                    msg = result.get("_message", "未知错误")
                    self.after(100, lambda m=msg: messagebox.showerror("生成失败", m))
                    return

                # HTTP 错误
                if result.get("_http_error"):
                    self.after(0, dlg.destroy)
                    status = result.get("_status", "?")
                    body = result.get("_body", {})
                    msg = f"服务器返回 HTTP {status}"
                    if isinstance(body, dict):
                        msg += f"\n{body.get('message', '')}"
                    self.after(100, lambda m=msg: messagebox.showerror("服务器拒绝", m))
                    return

                # 解析 DSL
                job = result.get("job", {})
                raw_result = job.get("result_script", "") or job.get("result", "")
                dsl_obj = None
                if raw_result:
                    try:
                        if isinstance(raw_result, str):
                            txt = raw_result.strip()
                            if txt.startswith("```"):
                                txt = txt.strip("`")
                                if txt.startswith("json"):
                                    txt = txt[4:].strip()
                            dsl_obj = json.loads(txt)
                        else:
                            dsl_obj = raw_result
                        if not isinstance(dsl_obj, dict) or "actions" not in dsl_obj:
                            dsl_obj = None
                    except Exception as e:
                        log.warning(f"AI 输出 JSON 解析失败: {e}")
                        dsl_obj = None

                if not dsl_obj:
                    self.after(0, dlg.destroy)
                    err = job.get("error_message") or "AI 返回的内容不是有效 JSON DSL"
                    self.after(100, lambda e=err: messagebox.showerror(
                        "AI 输出无效",
                        f"无法解析 AI 返回:\n{e}\n\n建议重新录制或联系客服"))
                    return

                dlg.set_progress(75, "保存新版 DSL 和 Excel 模板...")
                dlg.add_log("✓ AI 已返回有效 DSL")

                # 覆盖保存 dsl.json
                (flow_dir / "dsl.json").write_text(
                    json.dumps(dsl_obj, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                dlg.add_log(f"✓ dsl.json 已覆盖")

                # Excel 表头只按用户整理页最终保留的录制步骤顺序生成。
                cols = collect_columns(selected_steps)
                if cols:
                    sample = collect_sample_row(selected_steps, cols)
                    generate_template(flow_dir / "数据模板.xlsx", cols, sample)
                    dlg.add_log(f"✓ 数据模板.xlsx 已覆盖 ({len(cols)} 列)")
                else:
                    dlg.add_log("⊝ 录制步骤没有需要 Excel 参数化的字段,不生成模板")

                # 更新 meta.json
                meta["excel_columns"] = cols
                meta["has_excel"] = bool(cols)
                meta["regenerated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                (flow_dir / "meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                dlg.add_log(f"✓ meta.json 已更新 (regenerated_at)")

                dlg.set_progress(100, "完成!")
                self.after(0, dlg.destroy)
                self.after(100, lambda: self._after_regen(flow_dir.name))
            except Exception as e:
                heartbeat_done.set()
                detail = str(e)
                log.error(f"重新生成失败: {detail}", exc_info=True)
                self.after(0, dlg.destroy)
                self.after(100, lambda d=detail: messagebox.showerror("重新生成失败", d))

        threading.Thread(target=worker, daemon=True).start()

    def _after_regen(self, flow_name: str):
        """重新生成完成后回调"""
        self._load_flows()
        self._refresh()
        messagebox.showinfo(
            "重新生成成功",
            f"流程「{flow_name}」已用最新经验包重新生成。\n\n"
            f"  · dsl.json: 已覆盖\n"
            f"  · 数据模板.xlsx: 已覆盖\n"
            f"  · steps.json: 保留(录制数据不变)\n\n"
            f"如果之前的 Excel 已填好数据,记得对照新模板看下列名是否变化。"
        )

    # ════════════════════════════════════════
    #  反馈
    # ════════════════════════════════════════

    def _feedback(self, flow_dir: Path):
        if not self.api.is_paid:
            messagebox.showinfo("付费功能", "「反馈」是付费用户专属功能。\n请联系客服升级。")
            return

        dlg = FeedbackDialog(self, flow_dir, self.api)
        dlg.grab_set()

    # ════════════════════════════════════════
    #  工具
    # ════════════════════════════════════════

    def _card(self, parent):
        return ctk.CTkFrame(parent, corner_radius=10, fg_color=C_CARD,
                            border_color=C_BORDER, border_width=1)

    def _copy_serial(self):
        self.clipboard_clear(); self.clipboard_append(self.serial)
        messagebox.showinfo("已复制", "序列号已复制到剪贴板")

    def _serial_tail8(self) -> str:
        """序列号去掉分隔符后的后 8 位（充值备注用，20 位太长）。"""
        s = "".join(ch for ch in (self.serial or "") if ch.isalnum())
        return s[-8:] if len(s) >= 8 else s

    def _copy_pay_note(self):
        tail = self._serial_tail8()
        self.clipboard_clear(); self.clipboard_append(tail)
        messagebox.showinfo("已复制", f"备注内容「{tail}」已复制\n\n转账时请粘贴到「备注/留言」里")

    def _resolve_pay_qr(self):
        """找收款码图片路径，按优先级：
        1) 用户数据目录（可不重新打包就替换）  2) 打包内置  3) 源码同级
        找不到返回 None。"""
        candidates = []
        try:
            candidates.append(DATA_DIR / "pay_qr.png")
        except Exception:
            pass
        candidates.append(resource("app", "pay_qr.png"))
        for p in candidates:
            try:
                if p and p.exists():
                    return p
            except Exception:
                continue
        return None

    def _build_pay_card(self, parent):
        """充值续费卡片：左侧支付宝收款码，右侧序列号后 8 位备注提示。"""
        card = self._card(parent); card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card, text="💰 充值续费", font=F_BODY,
                     text_color=C_TEXT).pack(anchor="w", padx=18, pady=(14, 4))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=18, pady=(0, 14))

        # 左：收款码图片
        qr_path = self._resolve_pay_qr()
        qr_box = ctk.CTkFrame(body, fg_color="#f8fafc", corner_radius=8,
                              border_color=C_BORDER, border_width=1,
                              width=180, height=180)
        qr_box.pack(side="left")
        qr_box.pack_propagate(False)
        self._pay_qr_img = None
        if qr_path is not None:
            try:
                from PIL import Image
                img = Image.open(qr_path)
                self._pay_qr_img = ctk.CTkImage(light_image=img, size=(164, 164))
                ctk.CTkLabel(qr_box, text="", image=self._pay_qr_img).pack(expand=True)
            except Exception:
                self._pay_qr_img = None
        if self._pay_qr_img is None:
            ctk.CTkLabel(qr_box, text="收款码未配置\n（把 pay_qr.png 放到\n数据目录即可）",
                         font=F_SM, text_color=C_TEXT3, justify="center").pack(expand=True)

        # 右：充值说明 + 备注
        rt = ctk.CTkFrame(body, fg_color="transparent")
        rt.pack(side="left", fill="both", expand=True, padx=(18, 0))
        ctk.CTkLabel(rt, text="支付宝扫码转账，到账后联系客服为你充值",
                     font=F_SMB, text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(rt, text="⚠️ 转账时务必在「备注 / 留言」里填写下面的编号，方便核对到账：",
                     font=F_SM, text_color=C_ORANGE, justify="left",
                     wraplength=520).pack(anchor="w", pady=(10, 6))

        noterow = ctk.CTkFrame(rt, fg_color="#fef9c3", corner_radius=8)
        noterow.pack(anchor="w", fill="x", pady=(0, 8))
        ctk.CTkLabel(noterow, text="备注内容：", font=F_SM,
                     text_color=C_TEXT2).pack(side="left", padx=(12, 4), pady=10)
        ctk.CTkLabel(noterow, text=self._serial_tail8(),
                     font=("Consolas", 20, "bold"), text_color=C_RED).pack(side="left", pady=10)
        ctk.CTkButton(noterow, text="复制备注", width=84, height=30, font=F_SM,
                      corner_radius=6, fg_color=C_GREEN, hover_color=C_GREEN_H,
                      command=self._copy_pay_note).pack(side="right", padx=12, pady=8)

        ctk.CTkLabel(rt, text="（这是你序列号的后 8 位；充值、续费、定制需求也可直接加客服微信）",
                     font=F_SM, text_color=C_TEXT3, justify="left",
                     wraplength=520).pack(anchor="w")

    def _copy_wechat(self):
        self.clipboard_clear(); self.clipboard_append(WECHAT)
        messagebox.showinfo("已复制", f"微信号 {WECHAT} 已复制\n\n打开微信→搜索→粘贴")

    def _open_tutorial(self):
        try:
            webbrowser.open(TUTORIAL_URL)
        except Exception:
            self.clipboard_clear(); self.clipboard_append(TUTORIAL_URL)
            messagebox.showinfo("教程地址", f"已复制到剪贴板：\n{TUTORIAL_URL}")

    def _open_diag(self):
        """打开 AI 通讯诊断对话框"""
        DiagDialog(self, self.serial)

    def _update_kb(self):
        self.kb_btn.configure(state="disabled", text="检查中...")
        self.kb_status.configure(text="连接服务器...", text_color=C_TEXT3)
        threading.Thread(target=self._do_update_kb, daemon=True).start()

    def _do_update_kb(self):
        # 1. 拉客户端识别规则（inject.js / 选择器规则）
        ok, msg = update_from_server(DATA_DIR, self.api.token)
        if ok:
            self.rules = load_rules(DATA_DIR)
            self.recorder.rules = self.rules
            self.runner.rules = self.rules

        # 2. 增量同步 AI 经验库（细粒度经验）
        sync_ok, sync_msg, stats = self.patterns_lib.sync_incremental()

        # 3. 拉经验库版本号显示
        kb_info = self.api.get_kb_version()
        if kb_info and kb_info.get("ok"):
            self.after(0, lambda d=kb_info: self._show_kb_version(d))

        # 4. 刷新本地数量显示
        self.after(0, lambda: self.kb_local_label.configure(
            text=f"💡 本地已掌握 {self.patterns_lib.count} 条经验"))

        # 5. 状态提示
        if sync_ok:
            color = C_GREEN
            tip = f"✓ {sync_msg}"
        else:
            color = C_ORANGE
            tip = f"⚠ {sync_msg}"
        self.after(0, lambda c=color, t=tip: self.kb_status.configure(
            text=t, text_color=c))

    def _show_patterns_list(self):
        """弹窗展示所有本地经验"""
        PatternsListDialog(self, self.patterns_lib)
        self.after(0, lambda: self.kb_btn.configure(
            state="normal", text="检查更新"))
        self.after(3000, self._refresh_kb_text)

    def _refresh_kb_text(self):
        self.kb_status.configure(
            text=f"当前版本：v{self.rules.get('version', '1.0.0')}（{self.rules.get('updated_at', '')}）",
            text_color=C_TEXT2)

    # ════════════════════════════════════════
    #  环境
    # ════════════════════════════════════════

    def _bg_check_browser(self):
        threading.Thread(target=self._do_check_browser, daemon=True).start()

    def _do_check_browser(self):
        # 新策略：用系统 Edge（Win10/11 自带），不再依赖 Playwright 下载的 Chromium
        # 检测就是查文件存不存在，0.01 秒搞定
        from app.browser import detect_browser
        channel, exe_path = detect_browser()
        self._browser_ok = (channel != "chromium")  # chromium 是没装的兜底

        if channel == "msedge":
            tip = f"✓ 已就绪：系统 Edge\n   {exe_path}"
            self.after(0, lambda: self.env_status.configure(text=tip, text_color=C_GREEN))
            self.after(0, lambda: self.env_btn.configure(
                text="已就绪", fg_color="#e0e0e0",
                text_color=C_TEXT3, hover_color="#d0d0d0"))
        elif channel == "chrome":
            tip = f"✓ 已就绪：Google Chrome\n   {exe_path}"
            self.after(0, lambda: self.env_status.configure(text=tip, text_color=C_GREEN))
            self.after(0, lambda: self.env_btn.configure(
                text="已就绪", fg_color="#e0e0e0",
                text_color=C_TEXT3, hover_color="#d0d0d0"))
        else:
            # 极端情况：用户既没装 Edge 也没装 Chrome（很罕见）
            tip = "未检测到 Edge / Chrome。\nWin10/11 应该自带 Edge，请尝试重启电脑或重装 Edge。"
            self.after(0, lambda: self.env_status.configure(text=tip, text_color=C_ORANGE))
            self.after(0, lambda: self.env_btn.configure(text="重新检测"))

    def _is_browser_ready(self):
        """保留这个接口，给外部调用用"""
        from app.browser import detect_browser
        channel, _ = detect_browser()
        return channel != "chromium"  # msedge 或 chrome 都算 ok

    def _setup_env(self):
        # 用 Edge 后，已经不需要"安装浏览器"了，按钮变成"重新检测"
        self.env_btn.configure(state="disabled", text="检测中...")
        self.env_status.configure(text="正在检测系统浏览器...", text_color=C_ORANGE)
        threading.Thread(target=self._do_setup_env, daemon=True).start()

    def _do_setup_env(self):
        # 直接重新跑检测逻辑
        try:
            self._do_check_browser()
            self.after(0, lambda: self.env_btn.configure(state="normal"))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self.env_status.configure(
                text=f"检测失败：{err}", text_color=C_RED))
            self.after(0, lambda: self.env_btn.configure(state="normal", text="重试"))

    # ════════════════════════════════════════
    #  网络
    # ════════════════════════════════════════

    def _init_login(self):
        threading.Thread(target=self._do_login, daemon=True).start()

    def _do_login(self):
        try:
            self.api.ensure_logged_in()
            usage = self.api.get_usage()
            self.after(0, lambda: self._show_usage(usage))
            self.after(0, lambda: self._set_conn(True))
            self.after(0, self._load_flows)  # 刷新付费状态后重绘
            # 拉昵称
            profile = self.api.get_profile()
            if profile and profile.get("ok"):
                self.after(0, lambda p=profile: self._show_profile(p))
            # 顺便拉一下经验库版本
            kb_info = self.api.get_kb_version()
            if kb_info and kb_info.get("ok"):
                self.after(0, lambda d=kb_info: self._show_kb_version(d))

            # 启动时静默尝试同步经验库
            try:
                sync_ok, sync_msg, _ = self.patterns_lib.sync_incremental()
                self.after(0, lambda: self.kb_local_label.configure(
                    text=f"💡 本地已掌握 {self.patterns_lib.count} 条经验"))
                # 启动时同步失败不显眼提示，等用户手动点检查更新
                if sync_ok:
                    self.after(0, lambda m=sync_msg: self.kb_status.configure(
                        text=f"✓ {m}", text_color=C_GREEN))
            except Exception:
                pass
        except Exception as e:
            self.after(0, lambda e=e: self._set_conn(False, str(e)))

    def _show_profile(self, data: dict):
        """更新首页的昵称显示"""
        nickname = data.get("nickname") or ""
        remaining = int(data.get("nickname_remaining_edits", 3))
        locked = bool(data.get("nickname_locked", False))
        try:
            if nickname:
                self.nickname_label.configure(text=nickname, text_color=C_TEXT)
            else:
                self.nickname_label.configure(text="(未设置)", text_color=C_TEXT3)
            if locked:
                self.nickname_hint.configure(
                    text="🔒 昵称已锁定（已修改 3 次，无法再改）",
                    text_color=C_ORANGE)
                self.nickname_btn.configure(state="disabled", text="已锁定",
                                            fg_color="#e0e0e0", text_color=C_TEXT3,
                                            hover_color="#e0e0e0")
            else:
                self.nickname_hint.configure(
                    text=f"还可修改 {remaining} 次（共 3 次）",
                    text_color=C_TEXT3)
                self.nickname_btn.configure(
                    state="normal",
                    text="设置昵称" if not nickname else "修改昵称")
        except Exception:
            pass

    def _edit_nickname(self):
        """弹窗修改昵称"""
        EditNicknameDialog(self, self.api, on_saved=self._on_nickname_saved)

    def _on_nickname_saved(self, profile: dict):
        self._show_profile(profile)

    def _show_kb_version(self, data: dict):
        """更新首页的版本号显示"""
        kb_ver = data.get("kb_version", "1.0.0")
        kb_change = data.get("kb_latest_change") or ""
        kb_count = data.get("kb_patterns_count", 0)
        kb_time = data.get("kb_updated_at", "")
        if kb_time:
            kb_time = str(kb_time)[:10]  # 截 yyyy-mm-dd
        try:
            self.kb_ver_label.configure(text=f"V{kb_ver}")
            status_parts = [f"含 {kb_count} 条经验"]
            if kb_time:
                status_parts.append(f"更新于 {kb_time}")
            if kb_change:
                status_parts.append(f"最近：{kb_change[:40]}")
            self.kb_status.configure(text="  ·  ".join(status_parts))
        except Exception:
            pass

    def _set_conn(self, ok, err=""):
        if ok:
            self.conn_dot.configure(text_color=C_GREEN)
            self.conn_label.configure(text=" 已连接", text_color=C_GREEN)
        else:
            self.conn_dot.configure(text_color=C_RED)
            short = err[:36] + "..." if len(err) > 36 else err
            self.conn_label.configure(text=f" 连接失败：{short}", text_color=C_RED)

    def _refresh(self):
        self.conn_dot.configure(text_color=C_TEXT3)
        self.conn_label.configure(text=" 刷新中...", text_color=C_TEXT3)
        threading.Thread(target=self._do_login, daemon=True).start()

    def _show_usage(self, data):
        # 免费次数默认 5（服务器没返回时按 5 显示）
        free = data.get("free_generations", 5)
        paid = data.get("paid_generations", 0)
        total = data.get("available_generations", free + paid)
        try:
            self.free_val._v.configure(text=str(free))
            self.paid_val._v.configure(text=str(paid))
            self.total_val._v.configure(text=str(total))
        except Exception:
            pass

    # ════════════════════════════════════════
    #  录制流程
    # ════════════════════════════════════════

    def _start_rec(self):
        url = self.url_input.get().strip()
        if not url:
            self.rec_status.configure(text="请先输入网址", text_color=C_RED)
            return
        if not url.startswith("http"):
            url = "https://" + url

        if not self._browser_ok:
            self.rec_status.configure(
                text="请先到首页点击「检查并配置」安装浏览器组件",
                text_color=C_ORANGE)
            return

        # ─── 起步提醒：让用户主动确认录制次数（除非已勾选「不再提示」）───
        if not self._should_skip_count_prompt():
            picked = self._ask_recording_count()
            if picked is None:
                # 用户关掉对话框 → 取消录制
                return
            # picked 是用户选的次数，更新下拉显示
            self.recording_count_var.set(f"{picked} 次")

        # ─── 解析多次录制 ───
        try:
            self._target_sessions = int(self.recording_count_var.get().rstrip("次").strip())
        except Exception:
            self._target_sessions = 1
        self._target_sessions = max(1, min(self._target_sessions, 10))
        self._current_session = 1
        self._session_records = []
        self._recording_url = url

        # 多次录制开始前提示一下
        if self._target_sessions > 1:
            messagebox.showinfo(
                "📚 多次录制",
                f"将连续录制 {self._target_sessions} 次同一个流程。\n\n"
                "✅ 请尽量保持每次操作顺序一致\n"
                "✅ 可以小幅变化（不同的下拉项、不同的图片）\n"
                "✅ AI 会自动找出每次都做的步骤，"
                "用更稳的选择器生成脚本\n\n"
                f"现在开始第 1 / {self._target_sessions} 次录制。"
            )

        # 给整个批次创建一个流程目录
        record_name = "recording_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        if self._target_sessions > 1:
            record_name += f"_x{self._target_sessions}"
        self._active_recording_dir = FLOWS_DIR / record_name
        self._active_recording_dir.mkdir(parents=True, exist_ok=True)

        self._start_one_session()

    # ─── 起步选择对话框 ───
    PREFS_FILE_NAME = "preferences.json"

    def _load_prefs(self) -> dict:
        try:
            p = DATA_DIR / self.PREFS_FILE_NAME
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_prefs(self, prefs: dict) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / self.PREFS_FILE_NAME).write_text(
                json.dumps(prefs, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            log.debug("save prefs failed", exc_info=True)

    def _should_skip_count_prompt(self) -> bool:
        prefs = self._load_prefs()
        return bool(prefs.get("skip_recording_count_prompt", False))

    def _ask_recording_count(self) -> int | None:
        """
        起步对话框：让用户主动选择录制次数。
        返回用户选择的次数（1/3/5），或 None 表示取消。
        """
        dlg = tk.Toplevel(self)
        dlg.title("📚 选择录制次数")
        dlg.geometry("540x460")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        # 居中
        try:
            self.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - 540) // 2
            y = self.winfo_y() + (self.winfo_height() - 460) // 2
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass

        result = {"value": None}

        # 标题
        tk.Label(dlg, text="📚 你要录制几次同一个流程？",
                 font=("Microsoft YaHei", 14, "bold"),
                 fg="#1f2937", bg="#f8fafc").pack(fill="x", pady=(20, 6))
        tk.Label(dlg,
                 text="多次录制能让 AI 学到更稳的脚本，运行时不容易出错",
                 font=("Microsoft YaHei", 10),
                 fg="#64748b", bg="#f8fafc").pack(fill="x", pady=(0, 14))

        dlg.configure(bg="#f8fafc")

        opt_frame = tk.Frame(dlg, bg="#f8fafc")
        opt_frame.pack(fill="both", expand=True, padx=24, pady=4)

        def choose(n: int):
            result["value"] = n
            # 保存"不再提示"偏好（如果勾上）
            if skip_var.get():
                prefs = self._load_prefs()
                prefs["skip_recording_count_prompt"] = True
                self._save_prefs(prefs)
            dlg.destroy()

        # 3 个选项卡片
        options = [
            (1, "1 次（快速）", "简单流程（≤ 10 步），无文件上传",
             "适合：登录、查询、简单填表", "#94a3b8"),
            (3, "3 次（推荐）", "中等复杂度，10-30 步",
             "适合：商品上架、多字段填表、有上传", "#16a34a"),
            (5, "5 次（最稳）", "复杂流程，含素材库 / 网络相册",
             "适合：网络相册选图、多级菜单、需要批量跑 100+ 次", "#2563eb"),
        ]
        for n, title, desc, suit, color in options:
            card = tk.Frame(opt_frame, bg="white",
                            highlightbackground=color, highlightthickness=2)
            card.pack(fill="x", pady=4)
            inner = tk.Frame(card, bg="white")
            inner.pack(fill="both", expand=True, padx=12, pady=10)
            head = tk.Frame(inner, bg="white")
            head.pack(fill="x")
            tk.Label(head, text=title,
                     font=("Microsoft YaHei", 13, "bold"),
                     fg=color, bg="white").pack(side="left")
            tk.Button(head, text="选这个 →",
                      font=("Microsoft YaHei", 10, "bold"),
                      fg="white", bg=color, bd=0, padx=14, pady=4,
                      cursor="hand2",
                      command=lambda nn=n: choose(nn)
                      ).pack(side="right")
            tk.Label(inner, text=desc,
                     font=("Microsoft YaHei", 10),
                     fg="#374151", bg="white", anchor="w"
                     ).pack(fill="x", pady=(4, 0))
            tk.Label(inner, text=suit,
                     font=("Microsoft YaHei", 9),
                     fg="#64748b", bg="white", anchor="w"
                     ).pack(fill="x", pady=(2, 0))

        # 底部 - 不再提示
        skip_var = tk.BooleanVar(value=False)
        bottom = tk.Frame(dlg, bg="#f8fafc")
        bottom.pack(fill="x", padx=24, pady=(12, 16))
        tk.Checkbutton(
            bottom, text="不再提示，下次直接使用「录制」按钮旁的下拉框选择",
            variable=skip_var, bg="#f8fafc",
            font=("Microsoft YaHei", 9), fg="#64748b",
            anchor="w"
        ).pack(side="left")

        # 等待用户操作
        self.wait_window(dlg)
        return result["value"]

    def _start_one_session(self):
        """启动当前编号的 session（self._current_session）"""
        # 清空旧的行列表 + 备注引用
        for w in self.steps_box.winfo_children():
            w.destroy()
        self._step_note_entries.clear()
        self.step_count_label.configure(text="0 步")

        self.rec_btn.configure(state="disabled", text="录制中...")
        if self._target_sessions > 1:
            self.rec_status.configure(
                text=f"🎬 第 {self._current_session} / {self._target_sessions} 次录制中。"
                     "动作间隔 3-5 秒更准确；Ctrl+Shift+X 截图。",
                text_color=C_GREEN)
        else:
            self.rec_status.configure(
                text="浏览器已打开：动作间隔 3-5 秒更准确；"
                     "截图请先悬停目标按 Ctrl+Shift+X，再点击同一目标。",
                text_color=C_GREEN)

        # 每个 session 用独立的截图子目录（避免 step_index 冲突覆盖）
        if self._target_sessions > 1:
            capture_dir = self._active_recording_dir / "sessions" / f"session_{self._current_session}" / "screenshots"
        else:
            capture_dir = self._active_recording_dir / "screenshots"
        capture_dir.mkdir(parents=True, exist_ok=True)
        self.recorder.start(self._recording_url, capture_dir=capture_dir,
                            browser_mode="stealth_cdp")

    def _on_step(self, step):
        if step.get("_undo"):
            # 用户点了撤销，重绘整个步骤列表
            self.after(0, self._redraw_steps)
            return
        idx = step.get("step_index", "?")
        label = step.get("action_label", "操作")
        summary = self._brief_step(step)
        line = f"  {idx}.  [{label}]  {summary}\n"
        self.after(0, lambda: self._add_step(line))

    def _redraw_steps(self):
        """撤销后重绘录制实时列表（含备注）"""
        # 先把现有备注存起来（按 step_index）
        existing_notes = {}
        for idx, entry in self._step_note_entries.items():
            try:
                existing_notes[idx] = entry.get()
            except Exception:
                pass

        # 清空所有行
        for w in self.steps_box.winfo_children():
            w.destroy()
        self._step_note_entries.clear()

        # 重绘
        for s in self.recorder.steps:
            note = existing_notes.get(s.get("step_index"), s.get("user_note", ""))
            self._render_step_row(s, prefilled_note=note)
        self._update_step_count()

    def _render_step_row(self, step: dict, prefilled_note: str = ""):
        """渲染一行：[序号] [类型] [描述] [📝 备注]"""
        idx = step.get("step_index", "?")
        action_label = step.get("action_label", "操作")
        summary = self._brief_step(step)

        # 类型对应颜色
        type_colors = {
            "点击":     ("#dbeafe", "#1e40af"),
            "打开下拉": ("#fef3c7", "#92400e"),
            "选择菜单": ("#fed7aa", "#9a3412"),
            "输入":     ("#dcfce7", "#166534"),
            "勾选":     ("#e0e7ff", "#3730a3"),
            "选择":     ("#fed7aa", "#9a3412"),
            "滚动页面": ("#f0f9ff", "#0c4a6e"),
        }
        bg, fg = type_colors.get(action_label, ("#f3f4f6", "#475569"))

        row = tk.Frame(self.steps_box, bg="#fafafa")
        row.pack(fill="x", padx=4, pady=1)

        # 序号
        tk.Label(row, text=str(idx), font=(FN, 11, "bold"),
                 fg=C_TEXT3, bg="#fafafa", width=3, anchor="e"
                 ).pack(side="left", padx=(2, 4))

        # 类型徽章
        tk.Label(row, text=f" {action_label} ", font=(FN, 10),
                 fg=fg, bg=bg, padx=4
                 ).pack(side="left", padx=(0, 6))

        # 摘要（左对齐，可截断）
        tk.Label(row, text=summary, font=(FN, 11),
                 fg=C_TEXT, bg="#fafafa",
                 anchor="w", wraplength=300, justify="left"
                 ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        # 备注输入框（淡色，placeholder 风格）
        note_entry = tk.Entry(row, font=(FN, 10), bd=1, relief="solid",
                              bg="#fff", fg=C_TEXT,
                              highlightthickness=0)
        note_entry.pack(side="right", padx=(4, 2), ipady=2)
        # Entry 宽度（字符数）—— 不要太大
        note_entry.configure(width=22)
        if prefilled_note:
            note_entry.insert(0, prefilled_note)
        else:
            # placeholder 效果
            note_entry.insert(0, "📝 备注这步是干啥（可选）")
            note_entry.configure(fg=C_TEXT3)
            def on_focus_in(e, ent=note_entry):
                if ent.get() == "📝 备注这步是干啥（可选）":
                    ent.delete(0, "end")
                    ent.configure(fg=C_TEXT)
            def on_focus_out(e, ent=note_entry):
                if not ent.get().strip():
                    ent.insert(0, "📝 备注这步是干啥（可选）")
                    ent.configure(fg=C_TEXT3)
            note_entry.bind("<FocusIn>", on_focus_in)
            note_entry.bind("<FocusOut>", on_focus_out)

        # 实时写回 step（避免最后才收集时数据丢失）
        step_index = step.get("step_index")
        if step_index is not None:
            self._step_note_entries[step_index] = note_entry
            def on_change(*args, si=step_index, ent=note_entry):
                v = ent.get().strip()
                if v.startswith("📝"):  # placeholder
                    v = ""
                # 写入 recorder.steps 对应 step
                for s in self.recorder.steps:
                    if s.get("step_index") == si:
                        s["user_note"] = v
                        break
            note_entry.bind("<KeyRelease>", on_change)

    def _update_step_count(self):
        n = self.recorder.step_count
        if n > MAX_STEPS:
            self.step_count_label.configure(text=f"{n} 步  ⚠️ 超过上限", text_color=C_RED)
        elif n >= MAX_STEPS - 10:
            self.step_count_label.configure(text=f"{n} 步", text_color=C_ORANGE)
        else:
            self.step_count_label.configure(text=f"{n} 步", text_color=C_TEXT3)

    def _brief_step(self, s: dict) -> str:
        at = s.get("action_type", "")
        label = s.get("label", "").strip()
        text = s.get("text", "").strip()
        val = str(s.get("value", ""))
        if at == "input":
            show = val if s.get("input_type") != "password" else "*" * len(val)
            return f"{label or '字段'} = \"{show}\""
        if at == "select":
            return f"{label or '下拉框'} = {val}"
        if at == "check":
            return f"{label or text or '复选框'}"
        if at == "scroll":
            delta = s.get("scroll_delta", {})
            dy = delta.get("y", 0)
            dx = delta.get("x", 0)
            d = "↓" if dy > 0 else "↑" if dy < 0 else ("→" if dx > 0 else "←")
            px = abs(dy) if abs(dy) >= abs(dx) else abs(dx)
            return f"滚动 {d} {px}px"
        return (text or label or "元素")[:30]

    def _add_step(self, text: str):
        # 新版：text 参数已不用（直接从 recorder.steps 取最后一步渲染）
        # 保留参数签名向后兼容（_on_step 还在传 line 字符串）
        if self.recorder.steps:
            last = self.recorder.steps[-1]
            self._render_step_row(last)
            try:
                # 自动滚到底
                self.steps_box._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass
        self._update_step_count()

    def _on_done(self, steps):
        self.after(0, self._after_record)

    def _on_error(self, msg):
        self.after(0, lambda: self._after_record(error=msg))

    def _after_record(self, error=""):
        self.rec_btn.configure(state="normal", text="开始录制")
        if error:
            self.rec_status.configure(text=f"出错：{error}", text_color=C_RED)
            return
        if self.recorder.step_count == 0:
            self.rec_status.configure(text="未录制到任何操作", text_color=C_TEXT3)
            return

        # ─── 保存当前 session 的 steps ───
        current_session_steps = list(self.recorder.steps)
        self._session_records.append({
            "session_index": self._current_session,
            "step_count": len(current_session_steps),
            "steps": current_session_steps,
        })

        # 多次录制：把当前 session 的 steps.json 写到 sessions/session_N/
        if self._target_sessions > 1 and self._active_recording_dir:
            try:
                sess_dir = self._active_recording_dir / "sessions" / f"session_{self._current_session}"
                sess_dir.mkdir(parents=True, exist_ok=True)
                (sess_dir / "steps.json").write_text(
                    json.dumps(current_session_steps, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception:
                log.debug("save session steps failed", exc_info=True)

        # ─── 判断是否还要继续录下一次 ───
        if self._current_session < self._target_sessions:
            self._show_session_progress_and_continue()
            return

        # ─── 单次录制结束：智能提醒「要不要再录几次」───
        if self._target_sessions == 1:
            should_suggest_multi = (
                self.recorder.step_count > 10 or
                any(s.get("action_type") in ("upload", "upload_folder_to_library")
                    for s in current_session_steps)
            )
            if should_suggest_multi:
                if self._ask_continue_multi_session(current_session_steps):
                    return  # 继续录下一次，函数已经处理好了

        # ─── 所有 session 录完，进入整理页 ───
        self._finalize_all_sessions()

    def _show_session_progress_and_continue(self):
        """录完一次（不是最后一次）后，弹个对话框提示用户开始下一次"""
        done = self._current_session
        total = self._target_sessions
        # 计算每次 step 数
        rows = []
        for r in self._session_records:
            rows.append(f"  • 第 {r['session_index']} 次：{r['step_count']} 步")
        msg = (
            f"✅ 第 {done} / {total} 次录制完成\n\n"
            "📊 录制对比：\n"
            + "\n".join(rows) + "\n\n"
            f"👉 准备开始第 {done + 1} / {total} 次录制\n\n"
            "✅ 请尽量按相同顺序操作\n"
        )
        proceed = messagebox.askyesno(
            f"📚 录制进度 {done} / {total}",
            msg + "\n点「是」开始下一次，点「否」用现有录制提前结束。"
        )
        if proceed:
            self._current_session += 1
            self._start_one_session()
        else:
            # 用户提前结束
            self._target_sessions = self._current_session  # 锁定为已录的次数
            self._finalize_all_sessions()

    def _ask_continue_multi_session(self, current_steps: list) -> bool:
        """单次录制结束后，因为流程复杂，问要不要再录几次。
        返回 True 表示用户选择了继续录制（已经启动下一个 session）。"""
        n_steps = len(current_steps)
        uploads = sum(1 for s in current_steps if s.get("action_type") in ("upload", "upload_folder_to_library"))
        reason_parts = []
        if n_steps > 10:
            reason_parts.append(f"步骤数较多（{n_steps} 步）")
        if uploads:
            reason_parts.append(f"涉及文件 / 图片上传（{uploads} 处）")
        reason = "、".join(reason_parts)

        msg = (
            f"📊 本次录制 {n_steps} 步\n\n"
            f"💡 我们发现：{reason}\n\n"
            "对于这类流程，建议再录 1-2 次。\n"
            "AI 会自动找出每次都做的步骤，用更稳的选择器，"
            "运行时不容易出错。\n\n"
            "是否再录一次（共 2 次）？"
        )
        choose_yes = messagebox.askyesno("💡 建议多次录制", msg)
        if not choose_yes:
            return False
        # 用户决定再录一次：升级到 2 次
        self._target_sessions = 2
        self._current_session = 2
        self._start_one_session()
        return True

    def _finalize_all_sessions(self):
        """所有 session 录完，进入整理页"""
        n_done = len(self._session_records)
        total_steps = sum(r["step_count"] for r in self._session_records)

        if self._target_sessions > 1:
            # 多次录制：保存 sessions 元数据
            try:
                if self._active_recording_dir:
                    sessions_meta = {
                        "session_count": n_done,
                        "sessions": [
                            {"session_index": r["session_index"], "step_count": r["step_count"]}
                            for r in self._session_records
                        ],
                    }
                    (self._active_recording_dir / "sessions_meta.json").write_text(
                        json.dumps(sessions_meta, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
            except Exception:
                log.debug("save sessions_meta failed", exc_info=True)

            self.rec_status.configure(
                text=f"✓ 共完成 {n_done} 次录制（{total_steps} 步合计），已跳转到「整理」",
                text_color=C_GREEN)
        else:
            self.rec_status.configure(
                text=f"✓ 录制完成 {self.recorder.step_count} 步，已跳转到「整理」",
                text_color=C_GREEN)

        # 整理页使用第 1 次的录制作为基准展示
        # （AI 调用时会带上全部 sessions 给后台融合）
        if self._active_recording_dir and self._active_recording_dir.exists():
            try:
                self._open_dir(self._active_recording_dir)
            except Exception:
                log.debug("open recording review folder failed", exc_info=True)

        # 用第一次 session 的 build_review_data
        # （recorder.steps 当前是最后一次 session 的；要重置为第一次的）
        if self._target_sessions > 1 and self._session_records:
            # 临时把 recorder.steps 指向第 1 次的，让 build_review_data 用它
            primary_steps = self._session_records[0]["steps"]
            self.recorder.steps = primary_steps
        data = self.recorder.build_review_data()
        self._show_review(data)
        self.tabs.set("整理")

    # ════════════════════════════════════════
    #  生成脚本
    # ════════════════════════════════════════

    def _gen_script(self):
        # 强诊断日志（全部写到 error.log）
        log.error("=" * 50)
        log.error("[GEN] _gen_script 入口")
        log.error(f"[GEN] _review_data is None? {self._review_data is None}")

        if not self._review_data:
            log.error("[GEN] 没有 _review_data，直接返回")
            messagebox.showerror("无法生成", "没有可整理的步骤，请先录制流程")
            return

        log.error(f"[GEN] _review_data 长度: {len(self._review_data)}")

        # 收集最终数据
        try:
            steps = []
            for idx, it in enumerate(self._review_data):
                try:
                    selected = it["_var"].get()
                    ex = ""
                    if it.get("_excel_entry"):
                        ex = it["_excel_entry"].get().strip()
                    desc = it.get("_desc_entry").get().strip() if it.get("_desc_entry") else ""
                    # user_note：录制时实时备注的原始内容（用于调试 AI 为啥理解错了）
                    raw_user_note = ""
                    if it.get("_raw"):
                        raw_user_note = (it["_raw"].get("user_note") or "").strip()
                    steps.append({
                        "selected": selected,
                        "step_index": it["step_index"],
                        "action_type": it["action_type"],
                        "action_label": it["action_label"],
                        "selector": it["selector"],
                        "xpath": it.get("xpath", ""),
                        "scoped_selector": it.get("scoped_selector", ""),
                        "label": it["label"],
                        "value": it["value"],
                        "text": it["text"],
                        "tag": it["tag"],
                        "input_type": it.get("input_type", ""),
                        "url": it["url"],
                        "target_box": it.get("target_box"),
                        "viewport": it.get("viewport"),
                        "click_x": it.get("click_x"),
                        "click_y": it.get("click_y"),
                        "screenshot_file": it.get("screenshot_file", ""),
                        "screenshot_focus": it.get("screenshot_focus"),
                        "screenshot_kind": it.get("screenshot_kind", ""),
                        "screenshot_match": it.get("screenshot_match"),
                        "screenshot_width": it.get("screenshot_width"),
                        "screenshot_height": it.get("screenshot_height"),
                        "dom_context": it.get("dom_context"),
                        "scroll_from": it.get("scroll_from"),
                        "scroll_to": it.get("scroll_to"),
                        "scroll_delta": it.get("scroll_delta"),
                        "scroll_container": it.get("scroll_container"),
                        "excel_column": ex,
                        "description": desc,
                        # 调试用：录制时用户的原始备注（跟 description 区分；description 可能被整理页二次编辑）
                        "user_note": raw_user_note,
                    })
                except Exception as e:
                    log.error(f"[GEN] 收集第 {idx} 步异常: {e}", exc_info=True)
                    raise
            log.error(f"[GEN] 步骤收集完成，共 {len(steps)} 条")
        except Exception as e:
            log.error(f"[GEN] 步骤收集整体异常: {e}", exc_info=True)
            messagebox.showerror("收集步骤失败", f"{type(e).__name__}: {e}\n\n请把 error.log 发给作者")
            return

        # 进度对话框
        try:
            log.error("[GEN] 创建 ProgressDialog")
            dlg = ProgressDialog(self, "生成脚本", "正在准备...")
            log.error("[GEN] ProgressDialog 创建完成")
            dlg.update_idletasks()
            log.error("[GEN] update_idletasks 完成")
        except Exception as e:
            log.error(f"[GEN] ProgressDialog 创建异常: {e}", exc_info=True)
            messagebox.showerror("UI 错误", f"对话框创建失败：{e}")
            return

        def worker():
            log.error("[WORKER] >>> 线程入口 <<<")
            nonlocal dlg  # 关键：声明使用外层 dlg，避免 worker 内的赋值变成新局部变量
            heartbeat_done = threading.Event()
            try:
                log.error("[WORKER] 调用 dlg.add_log")
                dlg.add_log("✓ worker 线程启动成功")
                log.error("[WORKER] add_log 完成")
                dlg.set_progress(10, "正在分析步骤...")
                log.error("[WORKER] set_progress(10) 完成")
                init_url = self.recorder.init_url or (
                    self._review_data[0].get("url", "") if self._review_data else "")
                now = datetime.now()
                flow_name = f"录制_{now.strftime('%m%d_%H%M%S')}"

                # 仅发选中的步骤给 AI
                selected_steps = [s for s in steps if s["selected"]]
                api_steps = [self._step_for_api(s) for s in selected_steps]
                image_steps = [s for s in selected_steps if s.get("screenshot_file")]
                if image_steps:
                    total_images = len(image_steps)
                    dlg.set_image_progress(3, f"图片上传：发现 {total_images} 张辅助截图，正在上传...")
                    for img_idx, step in enumerate(image_steps, 1):
                        name = step.get("screenshot_file", "")
                        attached, upload_error = self._upload_image_for_api_step(step, api_steps, flow_name)
                        pct = int(img_idx / total_images * 100)
                        if attached:
                            dlg.set_image_progress(pct, f"图片 {img_idx}/{total_images} 已上传：{name}")
                            dlg.add_log(f"图片 {img_idx}/{total_images}: 已上传 {name}")
                        else:
                            dlg.set_image_progress(pct, f"图片 {img_idx}/{total_images} 上传失败：{name}")
                            dlg.add_log(f"图片 {img_idx}/{total_images}: 上传失败 {upload_error}")
                            raise RuntimeError(f"图片上传失败：{name}\n{upload_error}")
                    dlg.set_image_progress(100, f"图片上传：{total_images} 张辅助截图上传完成")
                else:
                    dlg.set_image_progress(100, "图片上传：本次没有辅助截图，跳过")

                # ── 模拟的"AI 思考过程"分阶段 ──
                # 基于实测：高推理模型在 reasoning_effort=high 下平均 40-60s
                steps_n = len(api_steps)
                thinking_timeline = [
                    (0,  "📥 接收用户的录制数据..."),
                    (2,  f"   → 共 {steps_n} 个操作步骤"),
                    (4,  "🔍 解析每一步的语义和上下文..."),
                    (7,  "   → 识别按钮、输入框、下拉菜单等元素类型"),
                    (10, "🎯 评估每个元素的选择器稳定性..."),
                    (13, "   → 优先级：scoped_selector > text= > xpath"),
                    (16, "🧩 构建 JSON 指令结构..."),
                    (20, "   → 决定每步的 action type（fill/click/select_option/check）"),
                    (24, "📝 为每个 input 步骤生成 fill action..."),
                    (28, "   → excel_column 非空 → 用 from_excel 绑定 Excel 数据"),
                    (32, "📝 为每个 click 步骤生成 click action..."),
                    (36, "   → 估算 wait_after（触发弹窗的 click 设 800ms）"),
                    (40, "📝 为每个菜单项生成 select_option..."),
                    (44, "   → 用 text='...' 精确匹配可见选项"),
                    (48, "🔧 优化指令顺序，处理依赖关系..."),
                    (52, "✨ 校验整个 JSON 是否符合 schema..."),
                    (56, "📤 准备返回响应..."),
                    (62, "⏳ 数据传输中..."),
                    (75, "🐌 比预期慢，AI 可能在做深度推理..."),
                    (85, "⚠️ 接近超时（90s），请稍等..."),
                ]

                import time as _t
                start_ts = _t.time()
                shown_idx = [-1]  # 已展示到第几条阶段日志

                def heartbeat():
                    while not heartbeat_done.is_set():
                        elapsed = _t.time() - start_ts
                        # 进度条按时间走（25% → 90%）
                        if elapsed < 60:
                            pct = 25 + int(elapsed / 60 * 50)
                        else:
                            pct = min(90, 75 + int((elapsed - 60) / 30 * 15))

                        # 推进"思考过程"日志
                        for i, (when, text) in enumerate(thinking_timeline):
                            if elapsed >= when and i > shown_idx[0]:
                                try:
                                    dlg.add_log(f"[{int(elapsed):3d}s] {text}")
                                except Exception:
                                    pass
                                shown_idx[0] = i

                        # 顶部文字按时间变化
                        if elapsed < 10:
                            stage = "📡 已发送请求，等待后台模型响应..."
                        elif elapsed < 30:
                            stage = "🧠 大模型推理中（reasoning_effort=high 通常 30-60s）"
                        elif elapsed < 60:
                            stage = "✍️  生成 JSON 指令中..."
                        else:
                            stage = "⏳ 即将完成..."

                        try:
                            dlg.set_progress(pct, f"{stage}  ·  已用 {int(elapsed)}s")
                        except Exception:
                            break
                        if heartbeat_done.wait(1):
                            break
                threading.Thread(target=heartbeat, daemon=True).start()

                # 进度回调，把 API 的每个阶段写到日志框
                def api_progress(stage_name, elapsed, detail):
                    line = f"[{elapsed:5.1f}s] {stage_name}"
                    if detail:
                        # detail 多行的话只取第一行+长度
                        first = detail.split("\n")[0][:80]
                        line += f"  ·  {first}"
                    try:
                        dlg.add_log(line)
                    except Exception:
                        pass

                # 读取用户选的模型档位
                try:
                    picked_label = self.model_picker.get()
                    model_key = self._model_key_map.get(picked_label, "code")
                except Exception:
                    picked_label = "代码生成（默认）"
                    model_key = "code"

                # ─── 多次录制：组装所有 sessions 的 steps（精简版，给 AI 融合用）───
                # primary session（第 1 次）= 现在的 api_steps（已含截图绑定）
                # 其他 sessions：用录制时保存的原始 steps
                multi_sessions = None
                if len(self._session_records) > 1:
                    multi_sessions = []
                    for r in self._session_records:
                        sess_idx = r["session_index"]
                        if sess_idx == 1:
                            # 用已经处理好的 api_steps（含图片 URL 绑定）
                            multi_sessions.append({
                                "session_index": 1,
                                "step_count": len(api_steps),
                                "steps": api_steps,
                            })
                        else:
                            # 其他 session 简化处理（不上传图片，只发原始步骤）
                            other_review = self._build_review_from_raw_steps(r["steps"])
                            other_api_steps = [self._step_for_api(s) for s in other_review if s.get("selected", True)]
                            multi_sessions.append({
                                "session_index": sess_idx,
                                "step_count": len(other_api_steps),
                                "steps": other_api_steps,
                            })
                    dlg.add_log(f"📚 多次录制：共 {len(multi_sessions)} 次")
                    for ms in multi_sessions:
                        dlg.add_log(f"   • 第 {ms['session_index']} 次：{ms['step_count']} 步")

                dlg.set_progress(25, f"调用阿里云 ({picked_label})...")
                dlg.add_log(f"━━━ 开始 ━━━")
                dlg.add_log(f"流程名: {flow_name}")
                dlg.add_log(f"步骤数: {len(api_steps)}（基准）")
                dlg.add_log(f"目标: {init_url}")
                dlg.add_log(f"模型档位: {picked_label}  (model_key={model_key})")

                # 生成前先确保 token 有效（防止长时间录制后 token 过期导致 401）
                try:
                    self.api.ensure_logged_in()
                except Exception:
                    pass

                # 客户端只发最关键信息 - prompt 由服务器统一维护（format=json_dsl_v1）
                # category 决定服务器加载哪类经验包：
                #   browser = 通用浏览器自动化
                #   jst     = 聚水潭专属（erp321.com/epaas，会用 jst 专属经验包）
                category = "jst" if getattr(self, "_current_recording_is_jst", False) else "browser"
                result = self.api.generate_script(
                    flow_name, api_steps,
                    notes=init_url,  # 只发初始 URL
                    category=category,
                    model_key=model_key,
                    sessions=multi_sessions,  # 多次录制时带上全部 sessions
                    on_progress=api_progress)
                heartbeat_done.set()

                # ── 检查通讯/网络错误 ──
                if result.get("_error"):
                    self.after(0, dlg.destroy)
                    kind = result.get("_kind", "unknown")
                    msg = result.get("_message", "未知错误")
                    hint = result.get("_hint", "")
                    diag = result.get("_diag", {})
                    tb = result.get("_traceback", "")

                    # 构造完整诊断文本
                    diag_text = [
                        f"=== 好办法自动化 - 调用错误诊断 ===",
                        f"错误类型: {kind}",
                        f"错误信息: {msg}",
                    ]
                    if hint:
                        diag_text.append(f"可能原因: {hint}")
                    diag_text.append("")
                    diag_text.append(f"--- 请求信息 ---")
                    diag_text.append(f"URL: {diag.get('url', '')}")
                    diag_text.append(f"方法: {diag.get('method', '')}")
                    diag_text.append(f"数据大小: {diag.get('payload_size_bytes', 0)} 字节")
                    diag_text.append(f"步骤数: {diag.get('steps_count', 0)}")
                    diag_text.append(f"开始时间: {diag.get('started_at', '')}")
                    diag_text.append("")
                    diag_text.append(f"--- 阶段日志 ---")
                    for s in diag.get("stages", []):
                        diag_text.append(
                            f"[{s.get('elapsed_s', 0):5.1f}s] {s.get('stage', '')}"
                            + (f"\n         {s.get('detail', '')}" if s.get('detail') else "")
                        )
                    if tb:
                        diag_text.append("")
                        diag_text.append(f"--- Python 堆栈 ---")
                        diag_text.append(tb)
                    diag_text.append("")
                    diag_text.append(f"=== END ===")

                    full = "\n".join(diag_text)
                    self.after(100, lambda: ErrorDiagDialog(
                        self, f"AI 调用失败（{kind}）", msg, full
                    ).grab_set())
                    return

                # ── 检查 HTTP 错误 ──
                if result.get("_http_error"):
                    self.after(0, dlg.destroy)
                    status = result.get("_status")
                    body = result.get("_body", {})
                    diag = result.get("_diag", {})

                    # 特殊处理：AI模型服务繁忙（503/too busy）
                    body_msg = body.get("message", "") if isinstance(body, dict) else ""

                    # 🟡 阿里云账户欠费
                    if "欠费" in body_msg or "Arrearage" in body_msg or "overdue-payment" in body_msg:
                        friendly = (
                            "🪙 阿里云账户欠费\n\n"
                            "服务器配置的阿里云 API Key 对应的账户余额不足或欠费，"
                            "百炼 API 已拒绝调用。\n\n"
                            "请联系管理员：\n"
                            "  • 进 https://bailian.console.aliyun.com/\n"
                            "  • 进 https://billing.console.aliyun.com/ 检查欠款\n"
                            "  • 充值后重试\n\n"
                            "你的本次次数没有被扣除。"
                        )
                        self.after(100, lambda: messagebox.showwarning(
                            "🪙 阿里云账户欠费", friendly))
                        return

                    # 🟡 阿里云 API Key 无效
                    if "API Key 无效" in body_msg or "InvalidApiKey" in body_msg:
                        friendly = (
                            "🔑 阿里云 API Key 无效\n\n"
                            "服务器 .env 的 DASHSCOPE_API_KEY 失效或被禁用。\n\n"
                            "请联系管理员检查并更新 API Key。"
                        )
                        self.after(100, lambda: messagebox.showwarning(
                            "🔑 API Key 无效", friendly))
                        return

                    # 🟡 限流
                    if "限流" in body_msg or "RateLimit" in body_msg or "Throttling" in body_msg:
                        friendly = (
                            "⏱️ 阿里云接口限流\n\n"
                            "请求过于频繁，请等 30 秒后重试。\n"
                            "如果一直限流，让管理员去百炼控制台提额。"
                        )
                        self.after(100, lambda: messagebox.showwarning(
                            "⏱️ 接口限流", friendly))
                        return

                    if (status == 500 and (
                            "Service is too busy" in body_msg
                            or "service_unavailable" in body_msg
                            or "503" in body_msg)):
                        friendly = (
                            "当前模型服务正在过载（不是软件问题）。\n\n"
                            "建议：\n"
                            "  • 等 5-10 分钟再试\n"
                            "  • 或去 admin 后台「模型配置」换用 OpenAI 兼容模型\n\n"
                            "你的次数没有被扣除。"
                        )
                        self.after(100, lambda: messagebox.showwarning(
                            "⚠️ AI 服务繁忙", friendly))
                        return

                    diag_text = [
                        f"=== 好办法自动化 - HTTP 错误诊断 ===",
                        f"HTTP 状态码: {status}",
                        f"",
                        f"--- 服务器响应 ---",
                        json.dumps(body, ensure_ascii=False, indent=2),
                        f"",
                        f"--- 请求信息 ---",
                        f"URL: {diag.get('url', '')}",
                        f"步骤数: {diag.get('steps_count', 0)}",
                        f"数据大小: {diag.get('payload_size_bytes', 0)} 字节",
                        f"",
                        f"--- 阶段日志 ---",
                    ]
                    for s in diag.get("stages", []):
                        diag_text.append(
                            f"[{s.get('elapsed_s', 0):5.1f}s] {s.get('stage', '')}"
                            + (f" · {s.get('detail', '')}" if s.get('detail') else "")
                        )
                    diag_text.append("")
                    diag_text.append(f"=== END ===")

                    full = "\n".join(diag_text)
                    msg = f"服务器返回 HTTP {status}"
                    if isinstance(body, dict):
                        msg += f"\n{body.get('message', '')}"
                    self.after(100, lambda m=msg, f=full: ErrorDiagDialog(
                        self, f"服务器拒绝请求", m, f
                    ).grab_set())
                    return

                # AI 真的响应了
                job = result.get("job", {})
                used_model = job.get("used_model") or job.get("used_provider", "")
                usage = job.get("usage") or {}
                err_msg = job.get("error_message")
                reasoning_content = job.get("reasoning_content", "")  # 真实思考内容（如服务器返回）

                dlg.set_progress(70, f"✓ AI 已响应（{used_model}）" if used_model else "✓ AI 已响应")
                dlg.add_log("")
                dlg.add_log("━━━ AI 响应到达 ━━━")
                dlg.add_log(f"使用模型: {used_model or '(未知)'}")

                # 展示 token 用量（含思考 token）
                if usage:
                    total = usage.get("total_tokens", "?")
                    prompt = usage.get("prompt_tokens", "?")
                    completion = usage.get("completion_tokens", "?")
                    reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                    dlg.add_log(f"输入 token: {prompt}  ·  输出 token: {completion}  ·  总计: {total}")
                    if reasoning:
                        dlg.add_log(f"🧠 思考 token: {reasoning}（AI 真的做了深度推理）")

                # 如果服务器返回了思考内容，展示前 500 字
                if reasoning_content:
                    dlg.add_log("")
                    dlg.add_log("━━━ AI 思考过程（前 500 字）━━━")
                    preview = reasoning_content[:500].replace("\n", "\n         ")
                    dlg.add_log(f"         {preview}")
                    if len(reasoning_content) > 500:
                        dlg.add_log(f"         ... (共 {len(reasoning_content)} 字)")

                dsl_obj = None
                ai_succeeded = False

                # 尝试从返回里解析 DSL
                raw_result = job.get("result_script", "") or job.get("result", "")
                if raw_result:
                    try:
                        if isinstance(raw_result, str):
                            txt = raw_result.strip()
                            # 兼容 ```json ... ``` 包裹
                            if txt.startswith("```"):
                                txt = txt.strip("`")
                                if txt.startswith("json"):
                                    txt = txt[4:].strip()
                            dsl_obj = json.loads(txt)
                        else:
                            dsl_obj = raw_result
                        if not isinstance(dsl_obj, dict) or "actions" not in dsl_obj:
                            dsl_obj = None
                        else:
                            ai_succeeded = True
                    except Exception as e:
                        log.warning(f"AI 输出 JSON 解析失败: {e}, 原始: {raw_result[:200]}")
                        dsl_obj = None

                # AI 没返回有效 DSL → 弹窗告知，让用户选择
                if not dsl_obj:
                    self.after(0, dlg.destroy)
                    reason = err_msg or "AI 返回内容不是有效的 JSON DSL"
                    preview = (raw_result[:500] + "...") if len(str(raw_result)) > 500 else raw_result
                    # 用 sentinel 值正确等待用户决策
                    decision = {}  # 空，由 ask() 填入
                    def ask():
                        ans = messagebox.askyesno(
                            "AI 输出无效",
                            f"AI 返回的内容无法解析为 JSON DSL。\n\n"
                            f"原因：{reason}\n\n"
                            f"AI 返回片段：\n{preview}\n\n"
                            f"是否使用本地兜底生成简单 DSL？\n"
                            f"（兜底版本质量较低，但可以用作参考）")
                        decision["fallback"] = bool(ans)
                    self.after(0, ask)
                    # 等待用户点击
                    import time as _t2
                    waited = 0
                    while "fallback" not in decision and waited < 300:
                        _t2.sleep(0.1)
                        waited += 0.1
                    if not decision.get("fallback"):
                        return
                    # 用户选择兜底
                    dlg = ProgressDialog(self, "本地生成", "兜底生成中...")
                    dsl_obj = steps_to_dsl(selected_steps, init_url, flow_name)

                dlg.set_progress(75, "生成 Excel 模板...")
                # 保存流程目录（聚水潭流程存到 flows_jst/，其他存到 flows/）
                is_jst = getattr(self, "_current_recording_is_jst", False)
                if is_jst:
                    # 聚水潭流程存到 flows_jst/<module_key>/<flow_name>/
                    mod_key = getattr(self, "_current_jst_module_key", "other")
                    base_dir = JST_FLOWS_DIR / mod_key
                else:
                    base_dir = FLOWS_DIR
                flow_dir = base_dir / flow_name
                flow_dir.mkdir(parents=True, exist_ok=True)
                src_screens = (
                    self._active_recording_dir / "screenshots"
                    if self._active_recording_dir else None
                )
                dst_screens = flow_dir / "screenshots"
                if src_screens and src_screens.exists():
                    shutil.copytree(src_screens, dst_screens, dirs_exist_ok=True)

                # DSL
                (flow_dir / "dsl.json").write_text(
                    json.dumps(dsl_obj, ensure_ascii=False, indent=2),
                    encoding="utf-8")

                # 原始步骤备份
                (flow_dir / "steps.json").write_text(
                    json.dumps(steps, ensure_ascii=False, indent=2),
                    encoding="utf-8")

                # Excel 模板只按用户整理页最终保留的录制步骤顺序生成。
                # 输入、上传、下拉选项等需要参数化的步骤会出现；
                # 普通点击（完成、新增等）没有 excel_column，不进入表头。
                cols = collect_columns(selected_steps)
                if cols:
                    sample = collect_sample_row(selected_steps, cols)
                    generate_template(flow_dir / "数据模板.xlsx", cols, sample)

                dlg.set_progress(95, "保存流程...")

                # 多次录制：拷贝所有 session 的 steps.json 到流程目录
                if multi_sessions and self._active_recording_dir:
                    try:
                        src_sessions = self._active_recording_dir / "sessions"
                        if src_sessions.exists():
                            shutil.copytree(src_sessions, flow_dir / "sessions", dirs_exist_ok=True)
                    except Exception:
                        log.debug("copy sessions failed", exc_info=True)

                # meta
                meta = {
                    "name": flow_name,
                    "url": init_url,
                    "category": category,  # browser / jst
                    "category_label": "聚水潭专属" if category == "jst" else "浏览器自动化",
                    "is_jst": category == "jst",
                    "step_count": len(selected_steps),
                    "has_excel": bool(cols),
                    "excel_columns": cols,
                    "created": now.strftime("%Y-%m-%d %H:%M"),
                    "software_version": SOFTWARE_VERSION,
                    "multi_session": bool(multi_sessions and len(multi_sessions) > 1),
                    "session_count": len(multi_sessions) if multi_sessions else 1,
                }
                # JST 模块信息（如果是从聚水潭模块卡片录制的）
                if category == "jst":
                    meta["jst_module_key"] = getattr(self, "_current_jst_module_key", "other")
                    meta["jst_module_label"] = getattr(self, "_current_jst_module_label", "工作台 / 通用")
                (flow_dir / "meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2),
                    encoding="utf-8")

                dlg.set_progress(100, "完成！")
                self.after(0, dlg.destroy)
                self.after(100, lambda: self._after_gen(flow_name))
            except Exception as e:
                heartbeat_done.set()
                detail = str(e)
                log.error(f"生成失败: {detail}\n" + (e.__class__.__name__))
                self.after(0, dlg.destroy)
                self.after(100, lambda: messagebox.showerror("生成失败", detail))

        log.error("[GEN] 启动 worker 线程")
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        log.error(f"[GEN] worker 线程已启动，alive={t.is_alive()}")

    def _step_for_api(self, s: dict) -> dict:
        """转成发给 AI 的格式 - 精简但保留关键定位字段"""
        out = {
            "step": s["step_index"],
            "action": s["action_type"],
            "selector": s["selector"],
        }
        # 关键兜底字段 - AI 生成 action 时必须保留这些
        if s.get("scoped_selector"):
            out["scoped_selector"] = s["scoped_selector"]
        if s.get("xpath"):
            out["xpath"] = s["xpath"]
        # 业务字段（标签/值等）
        if s.get("label"):
            out["label"] = s["label"]
        if s.get("value") not in (None, ""):
            if s.get("input_type") == "password":
                out["value"] = "***"
            else:
                out["value"] = str(s["value"])[:80]
        if s.get("text"):
            out["text"] = s["text"][:50]
        if s.get("input_type"):
            out["input_type"] = s["input_type"]
        # excel_column 同时填 field_name 兼容旧 validator
        if s.get("excel_column"):
            out["excel_column"] = s["excel_column"]
            out["field_name"] = s["excel_column"]
        if s.get("description"):
            out["description"] = s["description"][:140]
        # user_note 是用户录制时实时备注的原话，比 description 更可靠（description 可能被整理页编辑）
        if s.get("user_note"):
            out["user_note"] = s["user_note"][:140]
        for key in (
            "target_box", "viewport", "click_x", "click_y",
            "screenshot_file", "screenshot_focus", "screenshot_kind", "screenshot_match",
            "screenshot_width", "screenshot_height",
            "dom_context", "scroll_from", "scroll_to", "scroll_delta", "scroll_container",
        ):
            val = s.get(key)
            if val not in (None, "", {}):
                out[key] = val
        return out

    def _build_review_from_raw_steps(self, raw_steps: list[dict]) -> list[dict]:
        """
        把"原始 recorder.steps"转成"整理页 review 格式"。
        用于多次录制时，把 session 2 / 3 / N 的原始数据转成 _step_for_api 能消费的格式。
        简化版：不做 excel_column 推断（让 AI 自己融合时决定），只保留每步核心字段。
        """
        result = []
        for s in raw_steps:
            result.append({
                "_raw": s,
                "selected": True,
                "step_index": s.get("step_index", 0),
                "action_type": s.get("action_type", "click"),
                "action_label": s.get("action_label", ""),
                "selector": s.get("selector", ""),
                "xpath": s.get("xpath", ""),
                "scoped_selector": s.get("scoped_selector", ""),
                "label": s.get("label", ""),
                "value": s.get("value", ""),
                "text": s.get("text", ""),
                "tag": s.get("tag", ""),
                "input_type": s.get("input_type", ""),
                "url": s.get("url", ""),
                "target_box": s.get("target_box"),
                "viewport": s.get("viewport"),
                "click_x": s.get("click_x"),
                "click_y": s.get("click_y"),
                "dom_context": s.get("dom_context"),
                "scroll_from": s.get("scroll_from"),
                "scroll_to": s.get("scroll_to"),
                "scroll_delta": s.get("scroll_delta"),
                "scroll_container": s.get("scroll_container"),
                # 非主 session 不带 excel_column 和截图（只发主 session 的）
                "excel_column": "",
                "description": "",
                "screenshot_file": "",
                "user_note": "",
            })
        return result

    def _upload_image_for_api_step(self, step: dict, api_steps: list[dict], flow_name: str) -> tuple[bool, str]:
        screenshot_file = str(step.get("screenshot_file") or "").strip()
        if not screenshot_file or not self._active_recording_dir:
            return False, "没有截图文件路径或录制目录"
        image_path = self._active_recording_dir / screenshot_file
        if not image_path.exists():
            image_path = self._active_recording_dir / "screenshots" / Path(screenshot_file).name
        if not image_path.exists():
            return False, f"本地图片不存在：{image_path}"
        step_index = step.get("step_index")
        result = self.api.upload_ai_image(image_path, flow_name=flow_name, step_index=step_index)
        if result.get("_error") or result.get("_http_error") or not result.get("ok"):
            log.error(f"图片上传失败: {result}")
            return False, self._format_upload_error(result)
        url = ((result.get("image") or {}).get("url") or "").strip()
        if not url:
            return False, f"后台未返回图片 URL：{result}"
        for api_step in api_steps:
            if api_step.get("step") == step_index:
                api_step["screenshot_url"] = url
                api_step["screenshot_label"] = f"step {step_index} {screenshot_file}"
                return True, ""
        return False, f"没有找到对应 API 步骤：step {step_index}"

    def _format_upload_error(self, result: dict) -> str:
        if result.get("_message"):
            return str(result.get("_message"))
        body = result.get("_body")
        if isinstance(body, dict):
            if body.get("message"):
                return str(body.get("message"))
            if body.get("raw_text"):
                return str(body.get("raw_text"))[:500]
            return json.dumps(body, ensure_ascii=False)[:500]
        if body:
            return str(body)[:500]
        return str(result)[:500]

    def _after_gen(self, flow_name: str):
        self._load_flows()
        self.tabs.set("我的流程")
        self._refresh()
        messagebox.showinfo("生成成功",
            f"流程「{flow_name}」已保存。\n\n如有 Excel 模板，请在「我的流程」中打开目录查看。")


# ════════════════════════════════════════
#  进度对话框
# ════════════════════════════════════════

class RunOptionsDialog(ctk.CTkToplevel):
    """无 Excel 的纯操作流程 - 选运行次数 + 间隔"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("运行选项")
        self.geometry("440x420")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=C_BG)

        self.cancelled = True
        self.loop_count = 1
        self.interval_ms = 2000

        ctk.CTkLabel(self, text="▶ 运行选项",
                     font=(FN, 16, "bold"), text_color=C_TEXT
                     ).pack(pady=(18, 4))
        ctk.CTkLabel(self,
            text="这个流程不需要 Excel 数据（纯点击/选择/截图等）",
            font=F_SM, text_color=C_TEXT3).pack(pady=(0, 14))

        # 模式
        mode_card = ctk.CTkFrame(self, fg_color=C_CARD,
                                  border_color=C_BORDER, border_width=1,
                                  corner_radius=10)
        mode_card.pack(fill="x", padx=22, pady=(0, 10))
        ctk.CTkLabel(mode_card, text="执行次数",
                     font=F_BODY, text_color=C_TEXT
                     ).pack(anchor="w", padx=16, pady=(12, 6))

        self.mode_var = tk.StringVar(value="once")

        r1 = ctk.CTkRadioButton(mode_card, text="运行 1 次（测试用）",
                                 variable=self.mode_var, value="once",
                                 font=F_SM, command=self._on_mode_change)
        r1.pack(anchor="w", padx=20, pady=4)

        r2_row = tk.Frame(mode_card, bg=C_CARD)
        r2_row.pack(anchor="w", padx=20, pady=4, fill="x")
        r2 = ctk.CTkRadioButton(r2_row, text="运行",
                                 variable=self.mode_var, value="fixed",
                                 font=F_SM, command=self._on_mode_change)
        r2.pack(side="left")
        self.count_entry = tk.Entry(r2_row, width=6, font=F_SM,
                                     bg="#fafafa", relief="solid", bd=1)
        self.count_entry.insert(0, "10")
        self.count_entry.pack(side="left", padx=6, ipady=2)
        tk.Label(r2_row, text="次", font=F_SM, bg=C_CARD,
                 fg=C_TEXT).pack(side="left")

        r3 = ctk.CTkRadioButton(mode_card, text="一直运行（关闭浏览器才停止）",
                                 variable=self.mode_var, value="infinite",
                                 font=F_SM, command=self._on_mode_change)
        r3.pack(anchor="w", padx=20, pady=(4, 12))

        # 间隔
        interval_card = ctk.CTkFrame(self, fg_color=C_CARD,
                                      border_color=C_BORDER, border_width=1,
                                      corner_radius=10)
        interval_card.pack(fill="x", padx=22, pady=(0, 10))
        ir = tk.Frame(interval_card, bg=C_CARD)
        ir.pack(fill="x", padx=16, pady=12)
        tk.Label(ir, text="每次循环间隔", font=F_BODY,
                 bg=C_CARD, fg=C_TEXT).pack(side="left")
        self.interval_entry = tk.Entry(ir, width=6, font=F_SM,
                                        bg="#fafafa", relief="solid", bd=1)
        self.interval_entry.insert(0, "2")
        self.interval_entry.pack(side="left", padx=6, ipady=2)
        tk.Label(ir, text="秒（避免操作太快被网站限制）",
                 font=F_SM, bg=C_CARD, fg=C_TEXT3).pack(side="left")

        # 按钮
        br = ctk.CTkFrame(self, fg_color="transparent")
        br.pack(pady=14)
        ctk.CTkButton(br, text="取消", width=100, height=36, font=F_BTN,
                      corner_radius=6, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self._cancel).pack(side="left", padx=6)
        ctk.CTkButton(br, text="开始运行", width=130, height=36, font=F_BTN,
                      corner_radius=6, fg_color=C_GREEN,
                      hover_color=C_GREEN_H,
                      command=self._confirm).pack(side="left", padx=6)

    def _on_mode_change(self):
        # 切到 fixed 自动给输入框焦点
        if self.mode_var.get() == "fixed":
            try:
                self.count_entry.focus_set()
            except Exception:
                pass

    def _cancel(self):
        self.cancelled = True
        self.destroy()

    def _confirm(self):
        mode = self.mode_var.get()
        if mode == "once":
            self.loop_count = 1
        elif mode == "infinite":
            self.loop_count = -1
        else:  # fixed
            try:
                n = int(self.count_entry.get())
                if n < 1 or n > 99999:
                    raise ValueError
                self.loop_count = n
            except Exception:
                messagebox.showwarning("次数无效",
                    "请输入 1-99999 之间的整数")
                return
        try:
            seconds = float(self.interval_entry.get())
            if seconds < 0 or seconds > 600:
                raise ValueError
            self.interval_ms = int(seconds * 1000)
        except Exception:
            messagebox.showwarning("间隔无效",
                "请输入 0-600 之间的秒数")
            return
        self.cancelled = False
        self.destroy()


class ProgressDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, initial_text=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("560x420")
        self.resizable(True, True)
        self.transient(parent)
        self.configure(fg_color=C_BG)

        ctk.CTkLabel(self, text=title, font=(FN, 15, "bold"),
                     text_color=C_TEXT).pack(pady=(16, 8))

        self.image_bar = ctk.CTkProgressBar(self, width=500, height=8,
                                            progress_color=C_BLUE)
        self.image_bar.set(0)
        self.image_bar.pack(pady=(0, 4))
        self.image_txt = ctk.CTkLabel(self, text="图片：等待检查", font=F_SM,
                                      text_color=C_TEXT3)
        self.image_txt.pack(pady=(0, 8))

        self.bar = ctk.CTkProgressBar(self, width=500, height=12,
                                      progress_color=C_GREEN)
        self.bar.set(0)
        self.bar.pack(pady=(0, 6))

        self.txt = ctk.CTkLabel(self, text=initial_text, font=F_SM,
                                text_color=C_TEXT2)
        self.txt.pack(pady=(0, 6))

        # 详细日志框（关键改进）
        ctk.CTkLabel(self, text="📋 执行明细", font=F_SMB,
                     text_color=C_TEXT2).pack(anchor="w", padx=18, pady=(8, 2))
        self.log_box = tk.Text(self, height=12, font=("Consolas", 10),
                               bg="#f8fafc", fg=C_TEXT2,
                               relief="solid", bd=1,
                               wrap="word", highlightthickness=0)
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        self.log_box.config(state="disabled")

        self.tip = ctk.CTkLabel(self,
            text="大模型思考通常 30-90 秒，连接 15 秒内必须建立成功",
            font=F_SM, text_color=C_TEXT3)
        self.tip.pack(pady=(0, 8))

    def set_progress(self, pct: int, text: str = None):
        def upd():
            self.bar.set(pct / 100)
            if text:
                self.txt.configure(text=text)
        try:
            self.after(0, upd)
        except Exception:
            pass

    def set_image_progress(self, pct: int, text: str = None):
        def upd():
            self.image_bar.set(max(0, min(100, pct)) / 100)
            if text:
                self.image_txt.configure(text=text)
        try:
            self.after(0, upd)
        except Exception:
            pass

    def add_log(self, line: str):
        """追加一行明细日志"""
        def upd():
            self.log_box.config(state="normal")
            self.log_box.insert("end", line + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        try:
            self.after(0, upd)
        except Exception:
            pass


# ════════════════════════════════════════
#  错误诊断对话框（带一键复制）
# ════════════════════════════════════════

class ErrorDiagDialog(ctk.CTkToplevel):
    """显示 API 调用错误的完整诊断，带一键复制"""
    def __init__(self, parent, title: str, message: str, diag_text: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("640x540")
        self.transient(parent)
        self.configure(fg_color=C_BG)
        self._diag_text = diag_text

        ctk.CTkLabel(self, text=f"❌ {title}", font=(FN, 16, "bold"),
                     text_color=C_RED).pack(pady=(16, 6))
        ctk.CTkLabel(self, text=message, font=F_SM,
                     text_color=C_TEXT, wraplength=580,
                     justify="left").pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="🔍 完整诊断信息", font=F_SMB,
                     text_color=C_TEXT2).pack(anchor="w", padx=20)

        self.diag_box = tk.Text(self, font=("Consolas", 10),
                                bg="#fef2f2", fg="#7f1d1d",
                                relief="solid", bd=1, wrap="word",
                                highlightthickness=0)
        self.diag_box.pack(fill="both", expand=True, padx=20, pady=(4, 8))
        self.diag_box.insert("1.0", diag_text)
        self.diag_box.config(state="disabled")

        br = ctk.CTkFrame(self, fg_color="transparent")
        br.pack(pady=(0, 14))

        self.copy_btn = ctk.CTkButton(
            br, text="📋 复制全部诊断信息", width=200, height=36,
            font=F_BTN, corner_radius=6,
            fg_color=C_GREEN, hover_color=C_GREEN_H,
            command=self._copy)
        self.copy_btn.pack(side="left", padx=6)

        ctk.CTkButton(
            br, text="关闭", width=100, height=36, font=F_BTN,
            corner_radius=6, fg_color="#e0e0e0",
            hover_color="#d0d0d0", text_color=C_TEXT2,
            command=self.destroy).pack(side="left", padx=6)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._diag_text)
        self.copy_btn.configure(text="✓ 已复制！可粘贴到聊天发给作者")
        self.after(2500, lambda: self.copy_btn.configure(text="📋 复制全部诊断信息"))


# ════════════════════════════════════════
#  反馈对话框
# ════════════════════════════════════════

class FeedbackDialog(ctk.CTkToplevel):
    def __init__(self, parent, flow_dir: Path, api: ApiClient):
        super().__init__(parent)
        self.flow_dir = flow_dir
        self.api = api
        self.title("反馈给作者")
        self.geometry("520x460")
        self.transient(parent)
        self.configure(fg_color=C_BG)

        ctk.CTkLabel(self, text="📧 反馈给作者", font=(FN, 16, "bold"),
                     text_color=C_TEXT).pack(pady=(20, 4))
        ctk.CTkLabel(self,
            text="脚本不能用？把详细情况告诉作者，会优化 AI 帮你修好。",
            font=F_SM, text_color=C_TEXT3).pack(pady=(0, 16))

        ctk.CTkLabel(self, text="问题描述（必填）：", font=F_SMB,
                     text_color=C_TEXT2).pack(anchor="w", padx=24)
        self.note = ctk.CTkTextbox(self, height=140, font=F_SM,
                                    fg_color=C_CARD,
                                    border_color=C_BORDER, border_width=1,
                                    corner_radius=7, text_color=C_TEXT)
        self.note.pack(fill="x", padx=24, pady=(4, 12))
        self.note.insert("1.0", "例如：在第 5 步点击「登录」按钮时报错，浏览器卡住没反应")

        ctk.CTkLabel(self,
            text="提交后会附带：流程的 JSON 数据 + 你的序列号\n（不会包含 Excel 数据）",
            font=F_SM, text_color=C_TEXT3, justify="left"
            ).pack(anchor="w", padx=24, pady=(0, 12))

        self.status = ctk.CTkLabel(self, text="", font=F_SM, text_color=C_TEXT3)
        self.status.pack()

        br = ctk.CTkFrame(self, fg_color="transparent"); br.pack(pady=12)
        ctk.CTkButton(br, text="取消", width=80, height=34, font=F_BTN,
                      corner_radius=6, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self.destroy).pack(side="left", padx=6)
        self.submit_btn = ctk.CTkButton(br, text="提交反馈",
                                        width=140, height=34, font=F_BTN,
                                        corner_radius=6, fg_color=C_GREEN,
                                        hover_color=C_GREEN_H,
                                        command=self._submit)
        self.submit_btn.pack(side="left", padx=6)

    def _submit(self):
        note = self.note.get("1.0", "end").strip()
        if not note or note.startswith("例如："):
            self.status.configure(text="请填写问题描述", text_color=C_RED)
            return
        self.submit_btn.configure(state="disabled", text="提交中...")
        self.status.configure(text="正在上传...", text_color=C_TEXT3)
        threading.Thread(target=self._do_submit, args=(note,), daemon=True).start()

    def _do_submit(self, note):
        try:
            dsl = json.loads((self.flow_dir / "dsl.json").read_text(encoding="utf-8"))
            steps = json.loads((self.flow_dir / "steps.json").read_text(encoding="utf-8"))
            meta = json.loads((self.flow_dir / "meta.json").read_text(encoding="utf-8"))
            payload = {
                "meta": meta,
                "dsl": sanitize_dsl(dsl),
                "steps": sanitize_steps(steps),
            }
            res = self.api.submit_feedback(meta.get("name", ""), payload, note,
                                           source="manual")
            if res.get("ok") or res.get("success"):
                self.after(0, lambda: self.status.configure(
                    text="✓ 已提交，作者收到后会联系你", text_color=C_GREEN))
                self.after(2000, self.destroy)
            else:
                err = res.get("message", "提交失败")
                self.after(0, lambda: self.status.configure(
                    text=f"失败：{err}", text_color=C_RED))
                self.after(0, lambda: self.submit_btn.configure(
                    state="normal", text="重试"))
        except Exception as e:
            self.after(0, lambda e=e: self.status.configure(
                text=f"失败：{e}", text_color=C_RED))
            self.after(0, lambda: self.submit_btn.configure(
                state="normal", text="重试"))


# ════════════════════════════════════════
#  自动错误反馈对话框
# ════════════════════════════════════════

class AutoErrorDialog(ctk.CTkToplevel):
    """脚本运行出错时自动弹出 - 所有用户都能用"""
    def __init__(self, parent, flow_dir: Path, error_msg: str, api: ApiClient):
        super().__init__(parent)
        self.flow_dir = flow_dir
        self.error_msg = error_msg
        self.api = api
        self.title("脚本出错 - 是否反馈作者？")
        self.geometry("580x560")
        self.transient(parent)
        self.configure(fg_color=C_BG)

        # 标题
        ctk.CTkLabel(self, text="😕 脚本运行出错",
                     font=(FN, 17, "bold"), text_color=C_TEXT
                     ).pack(pady=(18, 4))
        # 奖励提示（突出绿色）
        bonus_box = tk.Frame(self, bg="#dcfce7",
                            highlightthickness=1,
                            highlightbackground=C_GREEN)
        bonus_box.pack(fill="x", padx=22, pady=(0, 10))
        tk.Label(bonus_box, text="🎁 反馈即奖励 1 次免费试用机会",
                 font=(FN, 13, "bold"), bg="#dcfce7",
                 fg="#15803d").pack(pady=(8, 2))
        tk.Label(bonus_box,
            text="你的反馈我们会及时处理。\n现在请你忙别的事情吧，或者重试一次（不消耗次数）。",
            font=F_SM, bg="#dcfce7", fg="#166534",
            justify="center").pack(pady=(0, 8))

        # 错误信息
        ctk.CTkLabel(self, text="❌ 错误信息：", font=F_SMB,
                     text_color=C_TEXT2).pack(anchor="w", padx=22)
        err_box = tk.Text(self, height=4, font=("Consolas", 10),
                         bg="#fef2f2", fg=C_RED, relief="solid", bd=1,
                         wrap="word", highlightthickness=0)
        err_box.insert("1.0", error_msg[:500])
        err_box.config(state="disabled")
        err_box.pack(fill="x", padx=22, pady=(4, 12))

        # 隐私提示
        privacy = tk.Frame(self, bg="#fef3c7",
                          highlightthickness=1,
                          highlightbackground="#fbbf24")
        privacy.pack(fill="x", padx=22, pady=(0, 8))
        tk.Label(privacy, text=(
            "🔒 隐私保护说明\n"
            "  •  自动隐藏所有密码字段（password 类型 + 含「密码」标签的输入）\n"
            "  •  会发送：流程步骤、报错信息、序列号、字段名\n"
            "  •  不会发送：你的真实账号密码、Excel 数据、个人文件\n"
            "  •  全程 HTTPS 加密，只有作者本人能看"
        ), font=F_SM, fg="#78350f", bg="#fef3c7",
           justify="left", anchor="w").pack(fill="x", padx=10, pady=8)

        # 补充说明（可选）
        ctk.CTkLabel(self, text="补充说明（可选，方便定位问题）：",
                     font=F_SMB, text_color=C_TEXT2
                     ).pack(anchor="w", padx=22, pady=(8, 2))
        self.note = ctk.CTkTextbox(self, height=70, font=F_SM,
                                    fg_color=C_CARD,
                                    border_color=C_BORDER, border_width=1,
                                    corner_radius=6, text_color=C_TEXT)
        self.note.pack(fill="x", padx=22, pady=(0, 8))
        self.note.insert("1.0", "例如：在录第三步时，下拉框里选了「集采不含运」")

        self.status = ctk.CTkLabel(self, text="", font=F_SM, text_color=C_TEXT3)
        self.status.pack()

        # 按钮区
        br = ctk.CTkFrame(self, fg_color="transparent")
        br.pack(pady=14)
        ctk.CTkButton(br, text="暂不发送", width=110, height=36, font=F_BTN,
                      corner_radius=6, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self.destroy).pack(side="left", padx=6)
        self.send_btn = ctk.CTkButton(br, text="发送给作者", width=140, height=36,
                                       font=F_BTN, corner_radius=6,
                                       fg_color=C_GREEN, hover_color=C_GREEN_H,
                                       command=self._send)
        self.send_btn.pack(side="left", padx=6)

        ctk.CTkLabel(self,
            text="提示：作者收到后会通过微信/邮件联系你",
            font=F_SM, text_color=C_TEXT3).pack(pady=(0, 8))

    def _send(self):
        note = self.note.get("1.0", "end").strip()
        if note.startswith("例如："):
            note = ""
        self.send_btn.configure(state="disabled", text="发送中...")
        self.status.configure(text="正在上传脱敏数据...", text_color=C_TEXT3)
        threading.Thread(target=self._do_send, args=(note,), daemon=True).start()

    def _do_send(self, note):
        try:
            dsl_p = self.flow_dir / "dsl.json"
            steps_p = self.flow_dir / "steps.json"
            meta_p = self.flow_dir / "meta.json"
            dsl = json.loads(dsl_p.read_text(encoding="utf-8")) if dsl_p.exists() else {}
            steps = json.loads(steps_p.read_text(encoding="utf-8")) if steps_p.exists() else []
            meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}

            payload = {
                "meta": meta,
                "dsl": sanitize_dsl(dsl),
                "steps": sanitize_steps(steps),
            }
            res = self.api.submit_feedback(
                meta.get("name", ""), payload, note,
                error_msg=self.error_msg,
                source="auto_error",
            )
            if res.get("ok") or res.get("success"):
                bonus = res.get("bonus_generations", 0)
                server_msg = res.get("message", "")
                if bonus and bonus > 0:
                    msg = f"✓ 已发送！奖励 {bonus} 次免费试用 🎁"
                else:
                    msg = "✓ 已发送，感谢反馈！"
                if server_msg:
                    msg += f"\n{server_msg}"
                self.after(0, lambda m=msg: self.status.configure(
                    text=m, text_color=C_GREEN))
                self.after(2800, self.destroy)
            else:
                err = res.get("message", "服务器拒绝接收")
                self.after(0, lambda: self.status.configure(
                    text=f"失败：{err}", text_color=C_RED))
                self.after(0, lambda: self.send_btn.configure(
                    state="normal", text="重试"))
        except Exception as e:
            self.after(0, lambda e=e: self.status.configure(
                text=f"失败：{e}", text_color=C_RED))
            self.after(0, lambda: self.send_btn.configure(
                state="normal", text="重试"))


# ════════════════════════════════════════
#  经验列表弹窗
# ════════════════════════════════════════

class PatternsListDialog(ctk.CTkToplevel):
    """展示本地已同步的所有 AI 经验，每条可展开看完整内容"""

    def __init__(self, parent, lib: PatternsLibrary):
        super().__init__(parent)
        self.lib = lib
        self.title("🧠 AI 经验库 - 本地已掌握的经验")
        self.geometry("780x600")
        self.configure(fg_color=C_BG)
        self.transient(parent)

        # 顶部
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkLabel(head, text="🧠 AI 经验库",
                     font=(FN, 16, "bold"), text_color=C_TEXT).pack(side="left")
        meta_text = f"V{lib.kb_version}  ·  共 {lib.count} 条"
        if lib.synced_at:
            meta_text += f"  ·  同步于 {lib.synced_at[:16].replace('T', ' ')}"
        ctk.CTkLabel(head, text=meta_text,
                     font=F_SM, text_color=C_TEXT3).pack(side="left", padx=(12, 0))
        ctk.CTkButton(head, text="×", width=30, height=30, font=(FN, 16),
                      fg_color="transparent", text_color=C_TEXT3,
                      hover_color="#e0e0e0",
                      command=self.destroy).pack(side="right")

        # 说明
        ctk.CTkLabel(self,
            text="这些是 AI 在生成脚本时使用的经验。点击「展开」查看每条具体内容。",
            font=F_SM, text_color=C_TEXT3,
            justify="left").pack(anchor="w", padx=18, pady=(0, 8))

        # 列表
        self.list_frame = ctk.CTkScrollableFrame(self,
            corner_radius=8, fg_color=C_CARD,
            border_color=C_BORDER, border_width=1)
        self.list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self._render()

    def _render(self):
        patterns = self.lib.patterns
        if not patterns:
            ctk.CTkLabel(self.list_frame,
                text="暂无经验。请点首页「检查更新」从服务器同步。",
                font=F_BODY, text_color=C_TEXT3).pack(pady=40)
            return

        # 按分类分组渲染
        groups = self.lib.by_category()
        for cat in self.lib.categories():
            items = groups.get(cat, [])
            if not items:
                continue
            self._render_section_header(cat, len(items))
            for p in items:
                self._render_one(p)

    def _render_section_header(self, cat: str, count: int):
        """分类小节标题"""
        cat_colors = {
            "common":  ("#f3f4f6", "#475569"),
            "browser": ("#dbeafe", "#1d4ed8"),
            "excel":   ("#d1fae5", "#065f46"),
            "word":    ("#e0e7ff", "#3730a3"),
            "ps":      ("#fce7f3", "#9d174d"),
            "pdf":     ("#fee2e2", "#991b1b"),
        }
        bg, fg = cat_colors.get(cat, ("#f3f4f6", "#374151"))
        header = tk.Frame(self.list_frame, bg=C_CARD)
        header.pack(fill="x", padx=4, pady=(8, 4))
        tk.Label(header, text=f"  {self.lib.category_label(cat)}  ",
                 font=F_SMB, fg=fg, bg=bg, padx=4).pack(side="left")
        tk.Label(header, text=f"{count} 条经验",
                 font=F_SM, fg=C_TEXT3, bg=C_CARD).pack(side="left", padx=(8, 0))

    def _render_one(self, p: dict):
        card = tk.Frame(self.list_frame, bg=C_CARD,
                       highlightthickness=1, highlightbackground=C_BORDER, bd=0)
        card.pack(fill="x", padx=4, pady=(0, 6))

        # 头部
        head = tk.Frame(card, bg=C_CARD)
        head.pack(fill="x", padx=10, pady=(8, 4))

        # 来源标签
        source = p.get("source", "builtin")
        source_color = "#16a34a" if source == "builtin" else "#2563eb"
        source_text = "内置" if source == "builtin" else "推送"
        tk.Label(head, text=source_text,
                 font=F_SM, fg="#fff", bg=source_color,
                 padx=4).pack(side="left", padx=(0, 6))

        # Code
        tk.Label(head, text=p.get("code", ""),
                 font=("Consolas", 11, "bold"),
                 fg=C_TEXT, bg=C_CARD).pack(side="left", padx=(0, 8))

        # 标题
        tk.Label(head, text=p.get("title", "(无标题)"),
                 font=F_SMB, fg=C_TEXT, bg=C_CARD,
                 anchor="w", justify="left", wraplength=420
                 ).pack(side="left", fill="x", expand=True)

        # 展开/收起按钮
        toggle_btn = tk.Button(head, text="展开 ▼", font=F_SM,
                              relief="flat", bg="#e0e0e0", fg=C_TEXT2,
                              cursor="hand2")
        toggle_btn.pack(side="right")

        # 时间戳指纹（让用户能确认这是不是最新版本）
        stamp = p.get("stamp", "")
        if stamp:
            tk.Label(head, text=stamp,
                     font=("Consolas", 9), fg="#78350f", bg="#fef3c7",
                     padx=4).pack(side="right", padx=(0, 6))

        # 内容（默认隐藏）
        content_frame = tk.Frame(card, bg=C_CARD)
        content_label = tk.Label(content_frame,
            text=p.get("content", "(无内容)"),
            font=("Consolas", 10),
            fg=C_TEXT2, bg="#fafafa",
            anchor="w", justify="left",
            wraplength=720, padx=10, pady=8,
            relief="solid", bd=1)
        content_label.pack(fill="x")
        # 初始不显示
        # content_frame.pack_forget()  # 实际上没 pack，所以不需要 forget

        expanded = [False]
        def toggle():
            if expanded[0]:
                content_frame.pack_forget()
                toggle_btn.configure(text="展开 ▼")
                expanded[0] = False
            else:
                content_frame.pack(fill="x", padx=10, pady=(0, 8))
                toggle_btn.configure(text="收起 ▲")
                expanded[0] = True
        toggle_btn.configure(command=toggle)


# ════════════════════════════════════════
#  昵称编辑对话框
# ════════════════════════════════════════

class EditNicknameDialog(ctk.CTkToplevel):
    """修改昵称（最多 3 次，超过锁定）"""

    def __init__(self, parent, api: ApiClient, on_saved=None):
        super().__init__(parent)
        self.api = api
        self.on_saved = on_saved
        self.title("修改昵称")
        self.geometry("440x320")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=C_BG)

        ctk.CTkLabel(self, text="👤 修改昵称",
                     font=(FN, 16, "bold"), text_color=C_TEXT
                     ).pack(pady=(20, 8))

        # 当前剩余次数
        self.info_label = ctk.CTkLabel(self, text="加载中...",
            font=F_SM, text_color=C_TEXT3)
        self.info_label.pack(pady=(0, 12))

        # 输入框
        ctk.CTkLabel(self, text="新昵称（1-40 字符）",
                     font=F_SMB, text_color=C_TEXT2
                     ).pack(anchor="w", padx=24, pady=(0, 4))
        self.entry = ctk.CTkEntry(self, height=38, font=F_BODY,
                                  corner_radius=7,
                                  fg_color="#fff",
                                  border_color=C_BORDER, border_width=1)
        self.entry.pack(fill="x", padx=24, ipady=4)

        # 警告
        self.warn_label = ctk.CTkLabel(self, text="",
            font=F_SM, text_color=C_ORANGE,
            wraplength=380, justify="left")
        self.warn_label.pack(padx=24, pady=(8, 0))

        # 结果
        self.result_label = ctk.CTkLabel(self, text="",
            font=F_SM, text_color=C_TEXT3,
            wraplength=380, justify="left")
        self.result_label.pack(padx=24, pady=(4, 0))

        # 按钮
        br = ctk.CTkFrame(self, fg_color="transparent")
        br.pack(side="bottom", pady=14)
        ctk.CTkButton(br, text="取消", width=90, height=34, font=F_BTN,
                      corner_radius=6, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color=C_TEXT2,
                      command=self.destroy).pack(side="left", padx=6)
        self.save_btn = ctk.CTkButton(br, text="保存", width=120, height=34,
                                       font=F_BTN, corner_radius=6,
                                       fg_color=C_GREEN, hover_color=C_GREEN_H,
                                       command=self._save)
        self.save_btn.pack(side="left", padx=6)

        # 异步加载当前状态
        threading.Thread(target=self._load_profile, daemon=True).start()

    def _load_profile(self):
        prof = self.api.get_profile()
        if not prof or not prof.get("ok"):
            self.after(0, lambda: self.info_label.configure(
                text="无法获取昵称信息", text_color=C_RED))
            return
        nickname = prof.get("nickname") or ""
        remaining = int(prof.get("nickname_remaining_edits", 3))
        locked = bool(prof.get("nickname_locked", False))

        def upd():
            if nickname:
                self.entry.insert(0, nickname)
            if locked:
                self.info_label.configure(
                    text="❌ 昵称已锁定，无法修改",
                    text_color=C_RED)
                self.entry.configure(state="disabled")
                self.save_btn.configure(state="disabled")
            else:
                self.info_label.configure(
                    text=f"当前昵称：{nickname or '(未设置)'}  ·  剩余 {remaining} 次修改",
                    text_color=C_TEXT2)
                if remaining == 1:
                    self.warn_label.configure(
                        text="⚠️ 这是最后一次修改机会，保存后将永久锁定！",
                        text_color=C_RED)
                elif remaining == 2:
                    self.warn_label.configure(
                        text="⚠️ 修改后将消耗 1 次机会，请谨慎",
                        text_color=C_ORANGE)
        self.after(0, upd)

    def _save(self):
        new_name = self.entry.get().strip()
        if not new_name:
            self.result_label.configure(text="昵称不能为空", text_color=C_RED)
            return
        if len(new_name) > 40:
            self.result_label.configure(text="昵称最长 40 字符", text_color=C_RED)
            return
        self.save_btn.configure(state="disabled", text="保存中...")
        threading.Thread(target=self._do_save, args=(new_name,), daemon=True).start()

    def _do_save(self, name: str):
        resp = self.api.update_nickname(name)
        if resp.get("ok"):
            msg = resp.get("message", "保存成功")
            self.after(0, lambda m=msg: self.result_label.configure(
                text=f"✓ {m}", text_color=C_GREEN))
            if self.on_saved:
                self.after(0, lambda r=resp: self.on_saved(r))
            self.after(1200, self.destroy)
        else:
            err = resp.get("message") or "保存失败"
            errors = resp.get("errors") or {}
            if errors:
                first = list(errors.values())[0]
                if isinstance(first, list) and first:
                    err = first[0]
            self.after(0, lambda e=err: self.result_label.configure(
                text=f"✗ {e}", text_color=C_RED))
            self.after(0, lambda: self.save_btn.configure(
                state="normal", text="保存"))
