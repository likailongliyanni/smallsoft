import json
from pathlib import Path
import time
import traceback

import requests

API_BASE = "https://tools.haobanfa.online/api"


def _is_proxy_error(exc: BaseException) -> bool:
    """识别代理错误：用户的 VPN / Clash / 系统代理坏了，不是服务器问题"""
    s = str(exc).lower()
    return (
        "proxyerror" in s
        or "unable to connect to proxy" in s
        or "tunnel connection failed" in s
        or "proxyschemeunknown" in s
    )


def safe_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    带代理自动降级的请求封装。
    先按系统代理走；如果代理坏了（ProxyError 等），自动绕过代理重试一次。
    其他错误正常抛出。
    """
    try:
        return requests.request(method, url, **kwargs)
    except (requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError,
            requests.exceptions.SSLError) as e:
        if not _is_proxy_error(e):
            raise
        # 代理坏了：显式禁用所有代理重试一次
        bypass_kwargs = dict(kwargs)
        bypass_kwargs["proxies"] = {"http": None, "https": None}
        return requests.request(method, url, **bypass_kwargs)


class ApiClient:
    def __init__(self, serial: str):
        self.serial = serial
        self.token: str | None = None
        self.is_paid: bool = False

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _file_headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def register_device(self) -> dict:
        resp = safe_request(
            "POST",
            f"{API_BASE}/auth/register",
            json={
                "username": self.serial,
                "password": self.serial,
                "name": f"设备_{self.serial[:9]}",
            },
            headers=self._headers(),
            timeout=15,
        )
        data = resp.json()
        if data.get("token"):
            self.token = data["token"]
        return data

    def login_device(self) -> dict:
        resp = safe_request(
            "POST",
            f"{API_BASE}/auth/login",
            json={"username": self.serial, "password": self.serial},
            headers=self._headers(),
            timeout=15,
        )
        data = resp.json()
        if data.get("token"):
            self.token = data["token"]
        return data

    def ensure_logged_in(self) -> dict:
        try:
            data = self.login_device()
            if data.get("token"):
                return data
        except Exception:
            pass
        return self.register_device()

    def get_kb_version(self) -> dict:
        """获取经验库版本信息（首页显示用，公开接口无需 token）"""
        try:
            resp = safe_request("GET", f"{API_BASE}/kb-version", timeout=8)
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        return {"ok": False}

    def get_usage(self) -> dict:
        resp = safe_request(
            "GET",
            f"{API_BASE}/usage",
            headers=self._headers(),
            timeout=10,
        )
        data = resp.json()
        try:
            self.is_paid = int(data.get("paid_generations", 0)) > 0 \
                or int(data.get("total_paid", 0)) > 0
        except Exception:
            self.is_paid = False
        return data

    def generate_script(self, flow_name: str, steps: list,
                        notes: str = "", mode: str = "normal",
                        category: str = "browser",
                        model_key: str = "code",
                        sessions: list = None,
                        on_progress=None) -> dict:
        """
        请求 AI 生成 JSON DSL 格式的脚本（带详细诊断）

        category: 场景分类（browser/excel/word/ps/pdf），决定服务器加载哪类经验包
        model_key: 阿里云模型档位（code/balanced/strong/fast/vision），后台路由到具体模型
        sessions: 多次录制的全部 sessions（可选）。格式：[{session_index, step_count, steps: [...]}, ...]
                 若提供，服务器会启用"多次录制融合"模式，比单次更稳。
        on_progress: 进度回调 fn(stage: str, elapsed_s: float, detail: str)
        """
        url = f"{API_BASE}/ai/generate"
        payload = {
            "flow_name": flow_name,
            "mode": mode,
            "format": "json_dsl_v1",
            "category": category,
            "model_key": model_key,
            "steps": steps,
            "notes": notes,
        }
        if sessions and len(sessions) > 1:
            payload["sessions"] = sessions
            payload["multi_session"] = True
            payload["session_count"] = len(sessions)

        diag = {
            "url": url,
            "method": "POST",
            "payload_size_bytes": len(json.dumps(payload)),
            "steps_count": len(steps),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stages": [],
        }
        t0 = time.time()

        def stage(name, detail=""):
            elapsed = time.time() - t0
            entry = {"stage": name, "elapsed_s": round(elapsed, 2), "detail": detail}
            diag["stages"].append(entry)
            if on_progress:
                try:
                    on_progress(name, elapsed, detail)
                except Exception:
                    pass

        # 检测系统代理（VPN / Clash 之类）
        try:
            sys_proxies = requests.utils.get_environ_proxies(url)
        except Exception:
            sys_proxies = {}
        has_sys_proxy = bool(sys_proxies)

        stage(
            "准备请求",
            f"目标 URL: {url}\n步骤数: {len(steps)}\n数据大小: {diag['payload_size_bytes']} 字节"
            + (f"\n检测到系统代理: {sys_proxies}" if has_sys_proxy else "")
        )

        def _is_proxy_error(exc: BaseException) -> bool:
            """识别代理引起的连接错误（不是真正的服务器问题）"""
            s = str(exc).lower()
            return (
                "proxyerror" in s
                or "unable to connect to proxy" in s
                or "tunnel connection failed" in s
                or "proxyschemeunknown" in s
            )

        def _do_post(use_proxy: bool):
            kwargs = {
                "json": payload,
                "headers": self._headers(),
                "timeout": (15, 200),
            }
            if not use_proxy:
                # 显式禁用所有代理（包括系统环境变量）
                kwargs["proxies"] = {"http": None, "https": None}
            return requests.post(url, **kwargs)

        # 关键：连接 15 秒 + 读取 200 秒
        # 连接 15 秒内必须成功（否则是网络/DNS/防火墙问题）
        # 读取 200 秒给 AI模型思考时间
        resp = None
        proxy_bypassed = False
        try:
            stage("正在连接服务器", "（连接超时设为 15 秒）")
            try:
                resp = _do_post(use_proxy=True)
            except (requests.exceptions.ProxyError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.SSLError) as e:
                # 是不是代理坏了？是的话绕过代理重试一次
                if has_sys_proxy and _is_proxy_error(e):
                    stage("⚠️ 系统代理失效，自动绕过代理重试",
                          f"原始错误: {type(e).__name__}: {str(e)[:200]}")
                    resp = _do_post(use_proxy=False)
                    proxy_bypassed = True
                else:
                    raise
            stage("收到响应",
                  f"HTTP {resp.status_code}\n响应大小: {len(resp.content)} 字节"
                  + ("\n（已绕过系统代理）" if proxy_bypassed else ""))
        except requests.exceptions.ConnectTimeout as e:
            stage("❌ 连接超时", str(e))
            return {
                "_error": True,
                "_kind": "connect_timeout",
                "_message": "连接服务器超时（15 秒内未能建立连接）",
                "_hint": "可能原因：网络断开、DNS 解析失败、服务器宕机、防火墙拦截",
                "_diag": diag,
            }
        except requests.exceptions.ReadTimeout as e:
            stage("❌ 读取超时", str(e))
            return {
                "_error": True,
                "_kind": "read_timeout",
                "_message": "服务器在 200 秒内未返回结果",
                "_hint": "可能原因：AI模型卡住、服务器处理失败、网络抖动",
                "_diag": diag,
            }
        except requests.exceptions.SSLError as e:
            stage("❌ SSL 错误", str(e))
            return {
                "_error": True,
                "_kind": "ssl_error",
                "_message": f"SSL 证书错误：{e}",
                "_hint": "可能原因：系统时间不对、证书过期、被代理拦截",
                "_diag": diag,
            }
        except requests.exceptions.ProxyError as e:
            stage("❌ 代理错误（绕过也失败）", str(e))
            return {
                "_error": True,
                "_kind": "proxy_error",
                "_message": f"系统代理连接失败：{e}",
                "_hint": "请关闭 VPN / Clash / 系统代理后重试，或检查代理配置",
                "_diag": diag,
            }
        except requests.exceptions.ConnectionError as e:
            stage("❌ 连接错误", str(e))
            hint = "可能原因：无网络、DNS 失败、服务器不可达"
            if has_sys_proxy:
                hint += "（已尝试绕过系统代理，仍然失败 — 大概率是真的连不上服务器）"
            return {
                "_error": True,
                "_kind": "connection_error",
                "_message": f"网络连接失败：{e}",
                "_hint": hint,
                "_diag": diag,
            }
        except Exception as e:
            stage("❌ 未知错误", f"{type(e).__name__}: {e}")
            return {
                "_error": True,
                "_kind": "unknown",
                "_message": f"请求异常 {type(e).__name__}: {e}",
                "_traceback": traceback.format_exc(),
                "_diag": diag,
            }

        # HTTP 错误（4xx / 5xx）
        if not resp.ok:
            try:
                body = resp.json()
            except Exception:
                body = {"raw_text": resp.text[:1000]}
            stage("❌ HTTP 错误", f"状态码 {resp.status_code}")
            return {
                "_http_error": True,
                "_status": resp.status_code,
                "_body": body,
                "_diag": diag,
            }

        # 解析 JSON 响应
        try:
            data = resp.json()
            stage("解析响应", "成功")
        except Exception as e:
            stage("❌ JSON 解析失败", f"{e}\n前 200 字符: {resp.text[:200]}")
            return {
                "_error": True,
                "_kind": "parse_error",
                "_message": "服务器返回的不是有效 JSON",
                "_raw_text": resp.text[:1000],
                "_diag": diag,
            }

        # 成功
        data["_diag"] = diag
        stage("✓ 完成", f"总耗时 {time.time()-t0:.1f} 秒")
        return data

    def upload_ai_image(self, image_path: Path, flow_name: str = "", step_index: int | None = None) -> dict:
        url = f"{API_BASE}/ai/images/upload"
        try:
            with open(image_path, "rb") as f:
                files = {"image": (image_path.name, f, "image/jpeg")}
                data = {"flow_name": flow_name}
                if step_index:
                    data["step_index"] = str(step_index)
                resp = safe_request(
                    "POST",
                    url,
                    files=files,
                    data=data,
                    headers=self._file_headers(),
                    timeout=(15, 120),
                )
        except Exception as e:
            return {
                "_error": True,
                "_kind": "upload_error",
                "_message": f"图片上传失败 {type(e).__name__}: {e}",
                "_traceback": traceback.format_exc(),
            }

        try:
            body = resp.json()
        except Exception:
            body = {"raw_text": resp.text[:1000]}

        if not resp.ok or not body.get("ok"):
            return {
                "_http_error": True,
                "_status": resp.status_code,
                "_body": body,
            }

        return body

    def get_profile(self) -> dict:
        """获取用户资料（含昵称信息）"""
        try:
            resp = safe_request("GET", f"{API_BASE}/me/profile",
                              headers=self._headers(), timeout=10)
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        return {"ok": False}

    def update_nickname(self, nickname: str) -> dict:
        """修改昵称（剩余次数会扣减）"""
        try:
            resp = safe_request("POST", f"{API_BASE}/me/nickname",
                                json={"nickname": nickname},
                                headers=self._headers(), timeout=15)
            return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"ok": False, "message": resp.text[:200]}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def get_announcements(self) -> dict:
        """获取公告列表（公开接口）"""
        try:
            resp = safe_request("GET", f"{API_BASE}/announcements", timeout=8)
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        return {"ok": False, "items": []}

    def submit_feedback(self, flow_name: str, template_json: dict,
                        user_note: str = "", error_msg: str = "",
                        source: str = "manual") -> dict:
        resp = safe_request(
            "POST",
            f"{API_BASE}/feedback",
            json={
                "flow_name": flow_name,
                "template": template_json,
                "note": user_note,
                "error": error_msg,
                "source": source,
            },
            headers=self._headers(),
            timeout=30,
        )
        return resp.json()
