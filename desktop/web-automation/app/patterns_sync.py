"""
客户端经验库同步
================

设计：
- 服务器 ai_patterns 表 + 文件 patterns 都通过 /api/patterns/all 暴露
- 客户端本地存 patterns.json
- 每条经验有 code（串号，如 EXP-009）+ checksum
- 检查更新时对比 code+checksum，缺失/变化的拉下来

本地缓存格式：
{
  "kb_version": "1.0.7",
  "synced_at": "2026-05-24T20:00:00",
  "count": 16,
  "patterns": [
    {
      "code": "EXP-001",
      "title": "输出必须只是 JSON 对象",
      "content": "...",
      "source": "builtin",
      "priority": 10,
      "updated_at": "..."
    }, ...
  ]
}
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_BASE = "https://tools.haobanfa.online/api"


class PatternsLibrary:
    """本地经验库管理器"""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "patterns.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning(f"读取本地 patterns 失败: {e}")
        return {
            "kb_version": "0.0.0",
            "synced_at": None,
            "count": 0,
            "patterns": [],
        }

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning(f"保存本地 patterns 失败: {e}")

    # ── 查询 ──

    @property
    def kb_version(self) -> str:
        return self.data.get("kb_version", "0.0.0")

    @property
    def synced_at(self) -> Optional[str]:
        return self.data.get("synced_at")

    @property
    def count(self) -> int:
        return len(self.data.get("patterns", []))

    @property
    def patterns(self) -> list:
        return self.data.get("patterns", [])

    def has(self, code: str) -> bool:
        return any(p.get("code") == code for p in self.patterns)

    def get(self, code: str) -> Optional[dict]:
        for p in self.patterns:
            if p.get("code") == code:
                return p
        return None

    def categories(self) -> list[str]:
        """返回经验包覆盖的所有场景分类（按内置顺序）"""
        order = ["common", "browser", "excel", "word", "ps", "pdf"]
        present = {p.get("category") or "browser" for p in self.patterns}
        # 按顺序展示已知分类，再补未知
        ordered = [c for c in order if c in present]
        extras = sorted(present - set(order))
        return ordered + extras

    def by_category(self) -> dict[str, list]:
        """按分类分组（key=分类，value=该分类下的经验列表）"""
        groups: dict[str, list] = {}
        for p in self.patterns:
            cat = p.get("category") or "browser"
            groups.setdefault(cat, []).append(p)
        # 每组内按 priority 排
        for items in groups.values():
            items.sort(key=lambda x: (x.get("priority", 99), x.get("code", "")))
        return groups

    @staticmethod
    def category_label(cat: str) -> str:
        return {
            "common":  "🌐 通用",
            "browser": "🌍 浏览器",
            "excel":   "📊 Excel",
            "word":    "📝 Word",
            "ps":      "🎨 PS",
            "pdf":     "📄 PDF",
        }.get(cat, cat)

    # ── 同步 ──

    def fetch_manifest(self) -> tuple[Optional[dict], Optional[str]]:
        """拉服务器轻量列表。返回 (data, error_msg)"""
        url = f"{API_BASE}/patterns/manifest"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json(), None
            if resp.status_code == 404:
                return None, "服务器还未部署经验同步接口（HTTP 404）"
            return None, f"服务器返回 HTTP {resp.status_code}"
        except requests.exceptions.ConnectTimeout:
            return None, "连接服务器超时（15s）"
        except requests.exceptions.ReadTimeout:
            return None, "服务器响应超时"
        except requests.exceptions.ConnectionError as e:
            return None, f"无法连接：{str(e)[:80]}"
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)[:80]}"

    def fetch_single(self, code: str) -> Optional[dict]:
        """拉单条经验"""
        try:
            resp = requests.get(f"{API_BASE}/patterns/{code}", timeout=10)
            if resp.ok:
                data = resp.json()
                return data.get("pattern")
        except Exception as e:
            log.warning(f"拉取经验 {code} 失败: {e}")
        return None

    def fetch_all(self) -> tuple[Optional[dict], Optional[str]]:
        """一次性拉全部。返回 (data, error_msg)"""
        url = f"{API_BASE}/patterns/all"
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200:
                return resp.json(), None
            if resp.status_code == 404:
                return None, "服务器还未部署经验同步接口（HTTP 404）"
            return None, f"服务器返回 HTTP {resp.status_code}"
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)[:80]}"

    def sync_incremental(self) -> tuple[bool, str, dict]:
        """
        增量同步：对比 manifest，只下载缺失/变化的经验
        返回 (成功?, 提示, 统计 dict)
        """
        manifest_data, err = self.fetch_manifest()
        if not manifest_data:
            # manifest 失败，尝试 fetch_all 兜底
            all_data, err2 = self.fetch_all()
            if not all_data:
                return False, err or err2 or "未知错误", {}
            return self._apply_full_sync(all_data)

        if not manifest_data.get("ok"):
            return False, "服务器返回了 ok=false", {}

        server_patterns = manifest_data.get("patterns", [])
        server_kb_version = manifest_data.get("kb_version", "0.0.0")

        # 当前本地的 code → checksum 映射
        local_map = {
            p["code"]: hashlib.md5(p.get("content", "").encode("utf-8")).hexdigest()
            for p in self.patterns
        }

        # 服务器 code → checksum
        server_codes = {p["code"] for p in server_patterns}

        # 待拉取：服务器有 + 本地没有 OR checksum 不同
        to_fetch = []
        for sp in server_patterns:
            local_checksum = local_map.get(sp["code"])
            if local_checksum != sp.get("checksum"):
                to_fetch.append(sp["code"])

        # 待删除：本地有 + 服务器没有（被禁用或删除）
        to_delete = [code for code in local_map.keys() if code not in server_codes]

        stats = {
            "added_or_updated": len(to_fetch),
            "deleted": len(to_delete),
            "total_server": len(server_patterns),
        }

        if not to_fetch and not to_delete:
            self.data["kb_version"] = server_kb_version
            self.data["synced_at"] = datetime.now().isoformat(timespec="seconds")
            self.save()
            return True, f"已是最新（共 {len(server_patterns)} 条经验）", stats

        # 拉缺失/变化的经验
        new_patterns_map = {p["code"]: p for p in self.patterns}
        for code in to_fetch:
            full = self.fetch_single(code)
            if full:
                new_patterns_map[code] = full

        # 删除被服务器禁用的
        for code in to_delete:
            new_patterns_map.pop(code, None)

        # 按 priority 排序
        new_list = list(new_patterns_map.values())
        new_list.sort(key=lambda x: (x.get("priority", 99), x.get("code", "")))

        self.data = {
            "kb_version": server_kb_version,
            "synced_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(new_list),
            "patterns": new_list,
        }
        self.save()
        return True, (
            f"已同步：新增/更新 {stats['added_or_updated']} 条，"
            f"删除 {stats['deleted']} 条，共 {len(new_list)} 条"
        ), stats

    def sync_all(self) -> tuple[bool, str]:
        """简单粗暴：一次性全量替换"""
        data, err = self.fetch_all()
        if not data:
            return False, err or "未知错误"
        ok, msg, _ = self._apply_full_sync(data)
        return ok, msg

    def _apply_full_sync(self, data: dict) -> tuple[bool, str, dict]:
        """把 /api/patterns/all 的返回数据应用到本地"""
        if not data.get("ok"):
            return False, "服务器返回 ok=false", {}
        patterns = data.get("patterns", [])
        self.data = {
            "kb_version": data.get("kb_version", "0.0.0"),
            "synced_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(patterns),
            "patterns": patterns,
        }
        self.save()
        return True, f"已同步全部 {len(patterns)} 条经验（全量模式）", {
            "added_or_updated": len(patterns),
            "deleted": 0,
            "total_server": len(patterns),
        }
