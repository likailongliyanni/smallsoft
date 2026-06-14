"""
AI模型通讯诊断工具（内置版）

测试软件 → 服务器 → AI模型整条链路。
作为 Toplevel 对话框集成在主软件首页。
"""

import json
import socket
import ssl
import sys
import threading
import time
import tkinter as tk
from tkinter import scrolledtext
from urllib.parse import urlparse

import requests

API_BASE = "https://tools.haobanfa.online/api"

FN = "Microsoft YaHei"
C_BG = "#f5f7fa"
C_TEXT = "#1a1a1a"
C_OK = "#16a34a"
C_FAIL = "#dc2626"
C_WAIT = "#94a3b8"
C_INFO = "#2563eb"


class _Step:
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
        self.status = "pending"
        self.detail = ""
        self.elapsed_s = 0.0


STEPS_TEMPLATE = [
    ("DNS 解析", "解析 tools.haobanfa.online"),
    ("TCP 连接", "443 端口能否打开"),
    ("TLS 握手", "HTTPS 证书校验"),
    ("/api/health", "服务器健康检查"),
    ("/api/auth/login", "设备登录拿 token"),
    ("/api/usage", "获取次数（顺便验证 token）"),
    ("/api/ai/generate", "AI 生成调用（关键，最长 90 秒）"),
]


class DiagDialog(tk.Toplevel):
    def __init__(self, parent, serial: str):
        super().__init__(parent)
        self.title("AI模型通讯诊断")
        self.geometry("740x680")
        self.configure(bg=C_BG)
        self.transient(parent)

        self.serial = serial
        self.token = None
        self.running = False
        self.steps = [_Step(n, d) for n, d in STEPS_TEMPLATE]

        tk.Label(self, text="🔍 AI模型通讯链路诊断",
                 font=(FN, 15, "bold"), bg=C_BG, fg=C_TEXT
                 ).pack(pady=(14, 4))
        tk.Label(self, text=f"目标: {API_BASE}",
                 font=(FN, 10), bg=C_BG, fg=C_INFO).pack()
        tk.Label(self, text=f"序列号: {serial}",
                 font=("Consolas", 10), bg=C_BG, fg=C_TEXT
                 ).pack(pady=(2, 10))

        frame = tk.Frame(self, bg="#fff", relief="solid", bd=1)
        frame.pack(fill="x", padx=18, pady=(0, 10))

        self.step_widgets = []
        for i, step in enumerate(self.steps):
            row = tk.Frame(frame, bg="#fff")
            row.pack(fill="x", padx=12, pady=6)
            icon = tk.Label(row, text="⏸", font=(FN, 13),
                            bg="#fff", fg=C_WAIT, width=3)
            icon.pack(side="left")
            name_lbl = tk.Label(row, text=f"{i+1}. {step.name}",
                                font=(FN, 11, "bold"),
                                bg="#fff", fg=C_TEXT, width=17, anchor="w")
            name_lbl.pack(side="left")
            desc_lbl = tk.Label(row, text=step.desc,
                                font=(FN, 10), bg="#fff",
                                fg="#555", anchor="w")
            desc_lbl.pack(side="left", padx=(6, 0), fill="x", expand=True)
            time_lbl = tk.Label(row, text="",
                                font=("Consolas", 9),
                                bg="#fff", fg="#888", width=10)
            time_lbl.pack(side="right")
            self.step_widgets.append((icon, name_lbl, desc_lbl, time_lbl))

        tk.Label(self, text="📋 完整日志",
                 font=(FN, 11, "bold"), bg=C_BG, fg=C_TEXT
                 ).pack(anchor="w", padx=20)
        self.log = scrolledtext.ScrolledText(
            self, height=12, font=("Consolas", 9),
            bg="#fafafa", fg=C_TEXT, relief="solid", bd=1, wrap="word")
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 8))

        btns = tk.Frame(self, bg=C_BG)
        btns.pack(pady=8)
        self.start_btn = tk.Button(
            btns, text="▶ 开始诊断", font=(FN, 12, "bold"),
            bg=C_OK, fg="#fff", relief="flat", padx=22, pady=7,
            cursor="hand2", command=self.start)
        self.start_btn.pack(side="left", padx=6)

        self.copy_btn = tk.Button(
            btns, text="📋 复制日志", font=(FN, 12, "bold"),
            bg="#2563eb", fg="#fff", relief="flat", padx=22, pady=7,
            cursor="hand2", command=self.copy_log)
        self.copy_btn.pack(side="left", padx=6)

    def log_line(self, line, color=None):
        def upd():
            tag = None
            if color:
                tag = f"c_{color.replace('#', '')}"
                self.log.tag_configure(tag, foreground=color)
            ts = time.strftime("%H:%M:%S")
            self.log.insert("end", f"[{ts}] {line}\n", tag if tag else "")
            self.log.see("end")
        try:
            self.after(0, upd)
        except Exception:
            pass

    def set_step(self, idx, status, detail="", elapsed=0):
        s = self.steps[idx]
        s.status = status
        s.detail = detail
        s.elapsed_s = elapsed
        icon, name_lbl, desc_lbl, time_lbl = self.step_widgets[idx]

        def upd():
            if status == "running":
                icon.configure(text="⏳", fg=C_INFO)
                desc_lbl.configure(text=f"{s.desc}  → 进行中...", fg=C_INFO)
                time_lbl.configure(text="")
            elif status == "ok":
                icon.configure(text="✓", fg=C_OK)
                desc_lbl.configure(text=f"{s.desc}  → {detail}", fg=C_OK)
                time_lbl.configure(text=f"{elapsed:.1f}s")
            elif status == "fail":
                icon.configure(text="✗", fg=C_FAIL)
                desc_lbl.configure(text=f"{s.desc}  → {detail[:50]}", fg=C_FAIL)
                time_lbl.configure(text=f"{elapsed:.1f}s")
        self.after(0, upd)

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_btn.configure(state="disabled", text="诊断中...")
        self.log.delete("1.0", "end")
        for i, s in enumerate(self.steps):
            s.status = "pending"
            s.detail = ""
            self.set_step(i, "pending")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.log_line("━━━━━━ 开始诊断 ━━━━━━", C_INFO)
            self.log_line(f"Python: {sys.version.split()[0]}")
            self.log_line(f"requests: {requests.__version__}")
            self.log_line(f"API_BASE: {API_BASE}")
            self.log_line(f"序列号: {self.serial}")
            self.log_line("")

            host = urlparse(API_BASE).hostname

            self._step_dns(host)
            self._step_tcp(host)
            self._step_tls(host)
            self._step_health()
            self._step_login()
            self._step_usage()
            self._step_ai()

            self.log_line("")
            self.log_line("━━━━━━ 诊断完成 ━━━━━━", C_INFO)
            ok_count = sum(1 for s in self.steps if s.status == "ok")
            self.log_line(f"通过: {ok_count} / {len(self.steps)}",
                          C_OK if ok_count == len(self.steps) else C_FAIL)
        except Exception as e:
            self.log_line(f"诊断异常: {e}", C_FAIL)
            import traceback
            self.log_line(traceback.format_exc())
        finally:
            self.running = False
            self.after(0, lambda: self.start_btn.configure(
                state="normal", text="▶ 重新诊断"))

    def _step_dns(self, host):
        i = 0
        self.set_step(i, "running")
        self.log_line(f"[1] DNS 解析 {host} ...")
        t0 = time.time()
        try:
            ip = socket.gethostbyname(host)
            el = time.time() - t0
            self.set_step(i, "ok", ip, el)
            self.log_line(f"    → {ip} ({el:.2f}s)", C_OK)
        except Exception as e:
            el = time.time() - t0
            self.set_step(i, "fail", str(e), el)
            self.log_line(f"    ❌ {e}", C_FAIL)
            raise

    def _step_tcp(self, host):
        i = 1
        self.set_step(i, "running")
        self.log_line(f"[2] TCP 连接 {host}:443 ...")
        t0 = time.time()
        try:
            with socket.create_connection((host, 443), timeout=10) as s:
                el = time.time() - t0
                self.set_step(i, "ok", "已连接", el)
                self.log_line(f"    → 已连接 ({el:.2f}s)", C_OK)
        except Exception as e:
            el = time.time() - t0
            self.set_step(i, "fail", str(e)[:40], el)
            self.log_line(f"    ❌ {e}", C_FAIL)
            raise

    def _step_tls(self, host):
        i = 2
        self.set_step(i, "running")
        self.log_line(f"[3] TLS 握手 ...")
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    el = time.time() - t0
                    subject = dict(x[0] for x in cert.get("subject", []))
                    cn = subject.get("commonName", "?")
                    self.set_step(i, "ok", f"CN={cn}", el)
                    self.log_line(f"    → CN: {cn} ({el:.2f}s)", C_OK)
        except Exception as e:
            el = time.time() - t0
            self.set_step(i, "fail", str(e)[:40], el)
            self.log_line(f"    ❌ {e}", C_FAIL)
            raise

    def _step_health(self):
        i = 3
        self.set_step(i, "running")
        url = f"{API_BASE}/health"
        self.log_line(f"[4] GET {url} ...")
        t0 = time.time()
        try:
            r = requests.get(url, timeout=(10, 15))
            el = time.time() - t0
            if r.ok:
                self.set_step(i, "ok", f"HTTP {r.status_code}", el)
                self.log_line(f"    → HTTP {r.status_code} ({el:.2f}s)", C_OK)
                self.log_line(f"    → 响应: {r.text[:200]}")
            else:
                self.set_step(i, "fail", f"HTTP {r.status_code}", el)
                self.log_line(f"    ❌ HTTP {r.status_code}: {r.text[:200]}", C_FAIL)
                raise RuntimeError(f"health 失败")
        except Exception as e:
            el = time.time() - t0
            if self.steps[i].status != "fail":
                self.set_step(i, "fail", str(e)[:40], el)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)
            raise

    def _step_login(self):
        i = 4
        self.set_step(i, "running")
        url = f"{API_BASE}/auth/login"
        self.log_line(f"[5] POST {url}")
        t0 = time.time()
        try:
            r = requests.post(url, json={
                "username": self.serial, "password": self.serial,
            }, timeout=(10, 30))
            el = time.time() - t0
            d = r.json()
            if r.ok and d.get("token"):
                self.token = d["token"]
                self.set_step(i, "ok", "已获取 token", el)
                self.log_line(f"    → HTTP {r.status_code} ({el:.2f}s)", C_OK)
                self.log_line(f"    → token: {self.token[:30]}...", C_OK)
            elif r.ok:
                self.log_line(f"    → 尝试注册...")
                r2 = requests.post(f"{API_BASE}/auth/register", json={
                    "username": self.serial, "password": self.serial,
                    "name": f"诊断_{self.serial[:9]}",
                }, timeout=(10, 30))
                d2 = r2.json()
                if r2.ok and d2.get("token"):
                    self.token = d2["token"]
                    self.set_step(i, "ok", "注册并登录", el)
                    self.log_line(f"    → 注册成功", C_OK)
                else:
                    self.set_step(i, "fail", "注册失败", el)
                    self.log_line(f"    ❌ {r2.text[:200]}", C_FAIL)
                    raise RuntimeError("注册失败")
            else:
                self.set_step(i, "fail", f"HTTP {r.status_code}", el)
                self.log_line(f"    ❌ HTTP {r.status_code}: {r.text[:200]}", C_FAIL)
                raise RuntimeError(f"登录失败")
        except Exception as e:
            el = time.time() - t0
            if self.steps[i].status != "fail":
                self.set_step(i, "fail", str(e)[:40], el)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)
            raise

    def _step_usage(self):
        i = 5
        self.set_step(i, "running")
        url = f"{API_BASE}/usage"
        self.log_line(f"[6] GET {url}")
        t0 = time.time()
        try:
            r = requests.get(url, headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }, timeout=(10, 15))
            el = time.time() - t0
            if r.ok:
                d = r.json()
                free = d.get("free_generations", "?")
                paid = d.get("paid_generations", "?")
                self.set_step(i, "ok", f"免费 {free}/付费 {paid}", el)
                self.log_line(f"    → HTTP {r.status_code} ({el:.2f}s)", C_OK)
                self.log_line(f"    → 免费: {free}, 付费: {paid}", C_OK)
                self.log_line(f"    → 完整: {json.dumps(d, ensure_ascii=False)}")
            else:
                self.set_step(i, "fail", f"HTTP {r.status_code}", el)
                self.log_line(f"    ❌ {r.text[:200]}", C_FAIL)
                raise RuntimeError()
        except Exception as e:
            el = time.time() - t0
            if self.steps[i].status != "fail":
                self.set_step(i, "fail", str(e)[:40], el)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)
            raise

    def _step_ai(self):
        i = 6
        self.set_step(i, "running")
        url = f"{API_BASE}/ai/generate"
        self.log_line(f"[7] POST {url}  ← 关键步骤")
        self.log_line(f"    用最小请求（1 步）测试...")
        payload = {
            "flow_name": "诊断测试",
            "mode": "normal",
            "format": "json_dsl_v1",
            "steps": [{
                "step": 1, "action": "click",
                "selector": 'button:has-text("测试")',
                "label": "测试", "value": "", "text": "测试",
                "description": "连通性诊断",
            }],
            "notes": "这是连通性诊断，请简单返回 JSON DSL",
        }
        self.log_line(f"    请求大小: {len(json.dumps(payload))} 字节")
        t0 = time.time()

        beat_stop = threading.Event()
        def beat():
            while not beat_stop.is_set():
                el = int(time.time() - t0)
                if el > 0:
                    self.log_line(f"    ⏱ 已等待 {el}s ...", C_INFO)
                if beat_stop.wait(10):
                    break
        threading.Thread(target=beat, daemon=True).start()

        try:
            r = requests.post(url, json=payload, headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, timeout=(15, 90))
            beat_stop.set()
            el = time.time() - t0
            self.log_line(f"    → HTTP {r.status_code} （耗时 {el:.1f}s）",
                          C_OK if r.ok else C_FAIL)

            if not r.ok:
                self.set_step(i, "fail", f"HTTP {r.status_code}", el)
                self.log_line(f"    ❌ {r.text[:600]}", C_FAIL)
                if r.status_code == 401:
                    self.log_line("    ⚠️ token 失效", C_FAIL)
                elif r.status_code == 402:
                    self.log_line("    ⚠️ 次数不足", C_FAIL)
                elif r.status_code == 422:
                    self.log_line("    ⚠️ 字段不合法", C_FAIL)
                elif r.status_code == 500:
                    self.log_line("    ⚠️ 服务器内部错误", C_FAIL)
                elif r.status_code == 504:
                    self.log_line("    ⚠️ 网关超时", C_FAIL)
                return

            d = r.json()
            job = d.get("job", {})
            used_model = job.get("used_model") or job.get("used_provider", "")
            usage = job.get("usage")
            result_script = job.get("result_script", "")
            err = job.get("error_message", "")
            status_field = job.get("status", "")

            self.log_line(f"    → job.status: {status_field}", C_OK)
            self.log_line(f"    → job.used_model: {used_model or '(空!)'}",
                          C_OK if used_model else C_FAIL)
            self.log_line(f"    → job.usage: {usage}")
            self.log_line(f"    → job.error_message: {err or '(无)'}")
            self.log_line(f"    → result_script 长度: {len(str(result_script))} 字符")

            if result_script:
                self.log_line(f"    → result_script 前 400 字:")
                self.log_line(f"        {str(result_script)[:400]}")

            if used_model and result_script:
                self.set_step(i, "ok", f"已调用 {used_model}", el)
                self.log_line(f"    ✓ AI模型真的被调用了！", C_OK)
                self.log_line(f"    ✓ 余额应该会扣除少量 token", C_OK)
            elif err:
                self.set_step(i, "fail", f"job 错误: {err[:30]}", el)
                self.log_line(f"    ❌ AI 返回错误: {err}", C_FAIL)
            elif not used_model:
                self.set_step(i, "fail", "未调用 AI", el)
                self.log_line(f"    ❌ used_model 为空，AI模型没被调用", C_FAIL)
                self.log_line(f"    ❌ 检查服务器侧 AI 配置（API Key、提示词）", C_FAIL)
            else:
                self.set_step(i, "fail", "返回空", el)
                self.log_line(f"    ❌ result_script 为空", C_FAIL)
        except requests.exceptions.ConnectTimeout:
            beat_stop.set()
            el = time.time() - t0
            self.set_step(i, "fail", "连接超时", el)
            self.log_line(f"    ❌ 15 秒内无法连接", C_FAIL)
        except requests.exceptions.ReadTimeout:
            beat_stop.set()
            el = time.time() - t0
            self.set_step(i, "fail", "读取超时", el)
            self.log_line(f"    ❌ 90 秒内没收到响应", C_FAIL)
            self.log_line(f"    ❌ AI模型在服务器侧卡住了", C_FAIL)
        except Exception as e:
            beat_stop.set()
            el = time.time() - t0
            if self.steps[i].status != "fail":
                self.set_step(i, "fail", str(e)[:40], el)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)

    def copy_log(self):
        text = self.log.get("1.0", "end").strip()
        if not text:
            return
        summary = ["=== AI模型通讯诊断报告 ===", ""]
        for i, s in enumerate(self.steps, 1):
            sym = {"ok": "✓", "fail": "✗", "running": "⏳", "pending": "⏸"}.get(s.status, "?")
            summary.append(f"{sym} {i}. {s.name}: {s.detail} ({s.elapsed_s:.1f}s)")
        summary.append("")
        summary.append("=== 详细日志 ===")
        summary.append(text)
        summary.append("")
        summary.append("=== END ===")

        full = "\n".join(summary)
        self.clipboard_clear()
        self.clipboard_append(full)
        self.copy_btn.configure(text="✓ 已复制！")
        self.after(2500, lambda: self.copy_btn.configure(text="📋 复制日志"))
