"""
DeepSeek 通讯诊断工具
=====================

独立测试软件 → 服务器 → DeepSeek 整条链路是否畅通。
不依赖软件主体逻辑，单纯 HTTP 调用，结果一目了然。

用法：
    python tools/test_deepseek.py

会自动测试 7 个环节，每个环节实时显示结果。
失败时一键复制完整日志给作者。
"""

import json
import socket
import ssl
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk
from urllib.parse import urlparse

# 让脚本无论从哪里运行都能 import app
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

try:
    from app.serial import get_serial
except Exception:
    def get_serial():
        return "TEST-0000-0000-0000-0000"

API_BASE = "https://tools.haobanfa.online/api"

# ── UI 配置 ──
FN = "Microsoft YaHei"
C_BG = "#f5f7fa"
C_TEXT = "#1a1a1a"
C_OK = "#16a34a"
C_FAIL = "#dc2626"
C_WAIT = "#94a3b8"
C_INFO = "#2563eb"


class TestStep:
    def __init__(self, name: str, desc: str):
        self.name = name
        self.desc = desc
        self.status = "pending"  # pending / running / ok / fail
        self.detail = ""
        self.elapsed_s = 0.0


STEPS = [
    TestStep("DNS 解析", "解析 tools.haobanfa.online"),
    TestStep("TCP 连接", "443 端口能否打开"),
    TestStep("TLS 握手", "HTTPS 证书校验"),
    TestStep("/api/health", "服务器健康检查"),
    TestStep("/api/auth/login", "设备登录拿 token"),
    TestStep("/api/usage", "获取次数（顺便验证 token）"),
    TestStep("/api/ai/generate", "AI 生成调用（关键，最长 60 秒）"),
]


class TestApp:
    def __init__(self, root):
        self.root = root
        root.title("DeepSeek 通讯诊断工具")
        root.geometry("740x680")
        root.configure(bg=C_BG)

        # 顶部
        tk.Label(root, text="🔍 DeepSeek 通讯链路诊断",
                 font=(FN, 16, "bold"), bg=C_BG, fg=C_TEXT
                 ).pack(pady=(16, 4))
        tk.Label(root, text=f"目标：{API_BASE}",
                 font=(FN, 11), bg=C_BG, fg=C_INFO).pack()
        tk.Label(root, text=f"序列号：{get_serial()}",
                 font=("Consolas", 11), bg=C_BG, fg=C_TEXT
                 ).pack(pady=(2, 12))

        # 步骤列表
        frame = tk.Frame(root, bg="#fff", relief="solid", bd=1)
        frame.pack(fill="x", padx=20, pady=(0, 12))

        self.step_widgets = []
        for i, step in enumerate(STEPS):
            row = tk.Frame(frame, bg="#fff")
            row.pack(fill="x", padx=14, pady=8)
            icon = tk.Label(row, text="⏸", font=(FN, 14),
                            bg="#fff", fg=C_WAIT, width=3)
            icon.pack(side="left")
            name_lbl = tk.Label(row, text=f"{i+1}. {step.name}",
                                font=(FN, 12, "bold"),
                                bg="#fff", fg=C_TEXT, width=18, anchor="w")
            name_lbl.pack(side="left")
            desc_lbl = tk.Label(row, text=step.desc,
                                font=(FN, 11), bg="#fff",
                                fg="#555", anchor="w")
            desc_lbl.pack(side="left", padx=(10, 0), fill="x", expand=True)
            time_lbl = tk.Label(row, text="",
                                font=("Consolas", 10),
                                bg="#fff", fg="#888", width=10)
            time_lbl.pack(side="right")
            self.step_widgets.append((icon, name_lbl, desc_lbl, time_lbl))

        # 日志框
        tk.Label(root, text="📋 完整日志",
                 font=(FN, 12, "bold"), bg=C_BG, fg=C_TEXT
                 ).pack(anchor="w", padx=22)
        self.log = scrolledtext.ScrolledText(
            root, height=14, font=("Consolas", 10),
            bg="#fafafa", fg=C_TEXT, relief="solid", bd=1, wrap="word")
        self.log.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        # 按钮区
        btns = tk.Frame(root, bg=C_BG)
        btns.pack(pady=10)
        self.start_btn = tk.Button(
            btns, text="▶ 开始诊断", font=(FN, 13, "bold"),
            bg=C_OK, fg="#fff", relief="flat", padx=24, pady=8,
            cursor="hand2", command=self.start)
        self.start_btn.pack(side="left", padx=6)

        self.copy_btn = tk.Button(
            btns, text="📋 复制日志", font=(FN, 13, "bold"),
            bg="#2563eb", fg="#fff", relief="flat", padx=24, pady=8,
            cursor="hand2", command=self.copy_log)
        self.copy_btn.pack(side="left", padx=6)

        self.token = None
        self.running = False

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
            self.root.after(0, upd)
        except Exception:
            pass

    def set_step(self, idx, status, detail="", elapsed=0):
        STEPS[idx].status = status
        STEPS[idx].detail = detail
        STEPS[idx].elapsed_s = elapsed

        icon, name_lbl, desc_lbl, time_lbl = self.step_widgets[idx]

        def upd():
            if status == "running":
                icon.configure(text="⏳", fg=C_INFO)
                desc_lbl.configure(text=f"{STEPS[idx].desc}  → 进行中...", fg=C_INFO)
                time_lbl.configure(text="")
            elif status == "ok":
                icon.configure(text="✓", fg=C_OK)
                desc_lbl.configure(text=f"{STEPS[idx].desc}  → {detail}", fg=C_OK)
                time_lbl.configure(text=f"{elapsed:.1f}s")
            elif status == "fail":
                icon.configure(text="✗", fg=C_FAIL)
                desc_lbl.configure(text=f"{STEPS[idx].desc}  → {detail[:60]}", fg=C_FAIL)
                time_lbl.configure(text=f"{elapsed:.1f}s")
        self.root.after(0, upd)

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_btn.configure(state="disabled", text="诊断中...")
        # 清空
        self.log.delete("1.0", "end")
        for i, s in enumerate(STEPS):
            s.status = "pending"
            s.detail = ""
            self.set_step(i, "pending")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.log_line("━━━━━━ 开始诊断 ━━━━━━", C_INFO)
            self.log_line(f"Python: {sys.version.split()[0]}")
            self.log_line(f"requests 版本: {requests.__version__}")
            self.log_line(f"API_BASE: {API_BASE}")
            self.log_line("")

            host = urlparse(API_BASE).hostname

            # 步骤 1: DNS
            self._step1_dns(host)
            # 步骤 2: TCP
            self._step2_tcp(host)
            # 步骤 3: TLS
            self._step3_tls(host)
            # 步骤 4: health
            self._step4_health()
            # 步骤 5: login
            self._step5_login()
            # 步骤 6: usage
            self._step6_usage()
            # 步骤 7: AI generate
            self._step7_ai()

            self.log_line("")
            self.log_line("━━━━━━ 诊断完成 ━━━━━━", C_INFO)
            ok_count = sum(1 for s in STEPS if s.status == "ok")
            self.log_line(f"通过: {ok_count} / {len(STEPS)}",
                          C_OK if ok_count == len(STEPS) else C_FAIL)
        except Exception as e:
            self.log_line(f"诊断异常: {e}", C_FAIL)
            import traceback
            self.log_line(traceback.format_exc())
        finally:
            self.running = False
            self.root.after(0, lambda: self.start_btn.configure(
                state="normal", text="▶ 重新诊断"))

    # ── 各步骤 ──

    def _step1_dns(self, host):
        idx = 0
        self.set_step(idx, "running")
        self.log_line(f"[1] DNS 解析 {host} ...")
        t0 = time.time()
        try:
            ip = socket.gethostbyname(host)
            elapsed = time.time() - t0
            self.set_step(idx, "ok", f"{ip}", elapsed)
            self.log_line(f"    → {ip}  ({elapsed:.2f}s)", C_OK)
        except Exception as e:
            elapsed = time.time() - t0
            self.set_step(idx, "fail", str(e), elapsed)
            self.log_line(f"    ❌ {e}", C_FAIL)
            self.log_line("    可能原因：网络断开、DNS 服务器异常、host 文件被改", C_FAIL)
            raise

    def _step2_tcp(self, host):
        idx = 1
        self.set_step(idx, "running")
        self.log_line(f"[2] TCP 连接 {host}:443 ...")
        t0 = time.time()
        try:
            with socket.create_connection((host, 443), timeout=10) as s:
                elapsed = time.time() - t0
                local = s.getsockname()
                self.set_step(idx, "ok", f"已连接", elapsed)
                self.log_line(f"    → 本地 {local[0]}:{local[1]}  ({elapsed:.2f}s)", C_OK)
        except socket.timeout:
            elapsed = time.time() - t0
            self.set_step(idx, "fail", "超时", elapsed)
            self.log_line(f"    ❌ 10 秒内未能建立 TCP 连接", C_FAIL)
            self.log_line("    可能原因：服务器宕机、防火墙拦截 443 端口", C_FAIL)
            raise RuntimeError("TCP 超时")
        except Exception as e:
            elapsed = time.time() - t0
            self.set_step(idx, "fail", str(e), elapsed)
            self.log_line(f"    ❌ {e}", C_FAIL)
            raise

    def _step3_tls(self, host):
        idx = 2
        self.set_step(idx, "running")
        self.log_line(f"[3] TLS 握手 ...")
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    elapsed = time.time() - t0
                    subject = dict(x[0] for x in cert.get("subject", []))
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    cn = subject.get("commonName", "?")
                    self.set_step(idx, "ok", f"CN={cn}", elapsed)
                    self.log_line(f"    → 证书 CN: {cn}", C_OK)
                    self.log_line(f"    → 颁发者: {issuer.get('commonName', '?')}", C_OK)
                    self.log_line(f"    → ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.time() - t0
            self.set_step(idx, "fail", str(e), elapsed)
            self.log_line(f"    ❌ {e}", C_FAIL)
            self.log_line("    可能原因：证书过期、系统时间不对、被代理拦截", C_FAIL)
            raise

    def _step4_health(self):
        idx = 3
        self.set_step(idx, "running")
        url = f"{API_BASE}/health"
        self.log_line(f"[4] GET {url} ...")
        t0 = time.time()
        try:
            r = requests.get(url, timeout=(10, 15))
            elapsed = time.time() - t0
            if r.ok:
                self.set_step(idx, "ok", f"HTTP {r.status_code}", elapsed)
                self.log_line(f"    → HTTP {r.status_code}  ({elapsed:.2f}s)", C_OK)
                self.log_line(f"    → 响应: {r.text[:200]}")
            else:
                self.set_step(idx, "fail", f"HTTP {r.status_code}", elapsed)
                self.log_line(f"    ❌ HTTP {r.status_code}: {r.text[:200]}", C_FAIL)
                raise RuntimeError(f"health 失败 {r.status_code}")
        except Exception as e:
            elapsed = time.time() - t0
            if STEPS[idx].status != "fail":
                self.set_step(idx, "fail", str(e)[:60], elapsed)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)
            raise

    def _step5_login(self):
        idx = 4
        self.set_step(idx, "running")
        url = f"{API_BASE}/auth/login"
        serial = get_serial()
        self.log_line(f"[5] POST {url}")
        self.log_line(f"    用户名: {serial}")
        t0 = time.time()
        try:
            r = requests.post(url, json={
                "username": serial,
                "password": serial,
            }, timeout=(10, 30))
            elapsed = time.time() - t0
            data = r.json()
            if r.ok and data.get("token"):
                self.token = data["token"]
                self.set_step(idx, "ok", "已获取 token", elapsed)
                self.log_line(f"    → HTTP {r.status_code}  ({elapsed:.2f}s)", C_OK)
                self.log_line(f"    → token (前 30 字): {self.token[:30]}...", C_OK)
            elif r.ok:
                # 没 token 可能需要注册
                self.log_line(f"    → 没 token, 尝试注册...", C_INFO)
                r2 = requests.post(f"{API_BASE}/auth/register", json={
                    "username": serial, "password": serial,
                    "name": f"诊断设备_{serial[:9]}",
                }, timeout=(10, 30))
                d2 = r2.json()
                if r2.ok and d2.get("token"):
                    self.token = d2["token"]
                    self.set_step(idx, "ok", "注册并登录", elapsed)
                    self.log_line(f"    → 注册成功, token (前 30 字): {self.token[:30]}...", C_OK)
                else:
                    self.set_step(idx, "fail", "注册失败", elapsed)
                    self.log_line(f"    ❌ 注册响应: {r2.text[:300]}", C_FAIL)
                    raise RuntimeError("注册失败")
            else:
                self.set_step(idx, "fail", f"HTTP {r.status_code}", elapsed)
                self.log_line(f"    ❌ HTTP {r.status_code}: {r.text[:300]}", C_FAIL)
                raise RuntimeError(f"登录失败 {r.status_code}")
        except Exception as e:
            elapsed = time.time() - t0
            if STEPS[idx].status != "fail":
                self.set_step(idx, "fail", str(e)[:60], elapsed)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)
            raise

    def _step6_usage(self):
        idx = 5
        self.set_step(idx, "running")
        url = f"{API_BASE}/usage"
        self.log_line(f"[6] GET {url}")
        t0 = time.time()
        try:
            r = requests.get(url, headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }, timeout=(10, 15))
            elapsed = time.time() - t0
            if r.ok:
                d = r.json()
                free = d.get("free_generations", "?")
                paid = d.get("paid_generations", "?")
                self.set_step(idx, "ok", f"免费 {free} / 付费 {paid}", elapsed)
                self.log_line(f"    → HTTP {r.status_code}  ({elapsed:.2f}s)", C_OK)
                self.log_line(f"    → 免费次数: {free}", C_OK)
                self.log_line(f"    → 付费次数: {paid}", C_OK)
                self.log_line(f"    → 完整响应: {json.dumps(d, ensure_ascii=False)}")
            else:
                self.set_step(idx, "fail", f"HTTP {r.status_code}", elapsed)
                self.log_line(f"    ❌ {r.text[:300]}", C_FAIL)
                raise RuntimeError(f"usage 失败")
        except Exception as e:
            elapsed = time.time() - t0
            if STEPS[idx].status != "fail":
                self.set_step(idx, "fail", str(e)[:60], elapsed)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)
            raise

    def _step7_ai(self):
        idx = 6
        self.set_step(idx, "running")
        url = f"{API_BASE}/ai/generate"
        self.log_line(f"[7] POST {url}  ← 关键步骤")
        self.log_line(f"    用最小测试请求（1 步）...")

        # 最小测试请求
        payload = {
            "flow_name": "诊断测试",
            "mode": "normal",
            "format": "json_dsl_v1",
            "steps": [
                {
                    "step": 1,
                    "action": "click",
                    "selector": "button:has-text(\"测试\")",
                    "label": "测试",
                    "value": "",
                    "text": "测试",
                    "description": "诊断测试，不需要真的能执行",
                }
            ],
            "notes": "这是连通性诊断，请简单返回一个 JSON DSL，不需要实际可用",
        }

        self.log_line(f"    请求大小: {len(json.dumps(payload))} 字节")
        t0 = time.time()

        # 开心跳，避免用户以为卡死
        beat_stop = threading.Event()
        def beat():
            while not beat_stop.is_set():
                el = int(time.time() - t0)
                if el > 0:
                    self.log_line(f"    ⏱  已等待 {el}s ...", C_INFO)
                if beat_stop.wait(10):
                    break
        threading.Thread(target=beat, daemon=True).start()

        try:
            r = requests.post(url, json=payload, headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, timeout=(15, 90))  # 连接 15s + 读取 90s
            beat_stop.set()
            elapsed = time.time() - t0
            self.log_line(f"    → HTTP {r.status_code} （耗时 {elapsed:.1f}s）",
                          C_OK if r.ok else C_FAIL)

            if not r.ok:
                self.set_step(idx, "fail", f"HTTP {r.status_code}", elapsed)
                self.log_line(f"    ❌ 服务器响应: {r.text[:600]}", C_FAIL)
                # 友好提示
                if r.status_code == 401:
                    self.log_line("    ⚠️  token 失效或未授权", C_FAIL)
                elif r.status_code == 402:
                    self.log_line("    ⚠️  次数不足", C_FAIL)
                elif r.status_code == 422:
                    self.log_line("    ⚠️  请求字段不合法，看上面的 errors", C_FAIL)
                elif r.status_code == 500:
                    self.log_line("    ⚠️  服务器内部错误（DeepSeek 调用可能失败）", C_FAIL)
                elif r.status_code == 504:
                    self.log_line("    ⚠️  网关超时（DeepSeek 没及时返回）", C_FAIL)
                raise RuntimeError(f"AI 失败 {r.status_code}")

            d = r.json()
            job = d.get("job", {})
            used_model = job.get("used_model") or job.get("used_provider", "")
            usage = job.get("usage")
            result_script = job.get("result_script", "")
            err = job.get("error_message", "")
            status_field = job.get("status", "")

            self.log_line(f"    → job.status: {status_field}", C_OK)
            self.log_line(f"    → job.used_model: {used_model}", C_OK if used_model else C_FAIL)
            self.log_line(f"    → job.usage: {usage}")
            self.log_line(f"    → job.error_message: {err or '(无)'}")
            self.log_line(f"    → result_script 长度: {len(str(result_script))} 字符")

            if result_script:
                preview = str(result_script)[:400]
                self.log_line(f"    → result_script 前 400 字: {preview}")

            if used_model and result_script:
                self.set_step(idx, "ok", f"已调用 {used_model}", elapsed)
                self.log_line(f"    ✓ DeepSeek 真的被调用了！", C_OK)
                self.log_line(f"    ✓ 余额应该会扣除少量 token", C_OK)
            elif err:
                self.set_step(idx, "fail", f"job 错误: {err[:40]}", elapsed)
                self.log_line(f"    ❌ AI 返回了错误: {err}", C_FAIL)
            elif not used_model:
                self.set_step(idx, "fail", "未调用 AI（used_model 为空）", elapsed)
                self.log_line(f"    ❌ used_model 为空，说明 DeepSeek 根本没被调用", C_FAIL)
                self.log_line(f"    ❌ 可能服务器侧的 AI 配置有问题", C_FAIL)
            else:
                self.set_step(idx, "fail", "返回空脚本", elapsed)
                self.log_line(f"    ❌ result_script 为空", C_FAIL)

        except requests.exceptions.ConnectTimeout:
            beat_stop.set()
            elapsed = time.time() - t0
            self.set_step(idx, "fail", "连接 15s 超时", elapsed)
            self.log_line(f"    ❌ 15 秒内无法连接到 /api/ai/generate", C_FAIL)
        except requests.exceptions.ReadTimeout:
            beat_stop.set()
            elapsed = time.time() - t0
            self.set_step(idx, "fail", "读取 90s 超时", elapsed)
            self.log_line(f"    ❌ 90 秒内没收到响应", C_FAIL)
            self.log_line(f"    ❌ DeepSeek 极有可能在服务器侧卡住或超时", C_FAIL)
        except Exception as e:
            beat_stop.set()
            elapsed = time.time() - t0
            if STEPS[idx].status != "fail":
                self.set_step(idx, "fail", str(e)[:60], elapsed)
            self.log_line(f"    ❌ {type(e).__name__}: {e}", C_FAIL)

    def copy_log(self):
        text = self.log.get("1.0", "end").strip()
        if not text:
            return
        # 加上汇总
        summary_lines = ["=== DeepSeek 通讯诊断报告 ===", ""]
        for i, s in enumerate(STEPS, 1):
            sym = {"ok": "✓", "fail": "✗", "running": "⏳", "pending": "⏸"}.get(s.status, "?")
            summary_lines.append(
                f"{sym} {i}. {s.name}: {s.detail} ({s.elapsed_s:.1f}s)"
            )
        summary_lines.append("")
        summary_lines.append("=== 详细日志 ===")
        summary_lines.append(text)
        summary_lines.append("")
        summary_lines.append("=== END ===")

        full = "\n".join(summary_lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(full)
        self.copy_btn.configure(text="✓ 已复制！可粘贴给作者")
        self.root.after(3000, lambda: self.copy_btn.configure(text="📋 复制日志"))


if __name__ == "__main__":
    root = tk.Tk()
    app = TestApp(root)
    root.mainloop()
