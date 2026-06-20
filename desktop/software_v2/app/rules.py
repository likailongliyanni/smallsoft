"""
知识库 - 浏览器识别规则
=========================

这是软件的"大脑"，与软件壳子分离：
- 内置一份默认规则（DEFAULT_RULES）
- 用户可以从服务器拉取最新版本（覆盖本地）
- 录制和运行时都从这里读取行为

升级时只需要更新这个 JSON，不需要重新打包 exe。
"""

import json
import logging
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_BASE = "https://tools.haobanfa.online/api"


# ════════════════════════════════════════════════════════
#  默认规则（v1.0）
# ════════════════════════════════════════════════════════
DEFAULT_RULES = {
    "version": "1.0.0",
    "updated_at": "2026-05-24",
    "description": "好办法自动化软件的浏览器识别规则",

    # ── inject.js 远程覆盖（关键升级）──
    # 如果非空，录制时使用这里的 JS 代码（最新版）
    # 留空则用 exe 内置的 inject.js（兜底）
    # 这样 selector/事件监听等逻辑可以远程迭代
    "inject_js_override": "",

    # ── 运行器参数（DSL 解释器从这里读）──
    "runner_config": {
        "default_timeout_ms": 15000,         # 单个 action 最大等待
        "find_visible_poll_ms": 250,         # 找可见元素的轮询间隔
        "find_visible_max_loops": 60,        # 最多轮询次数
        "select_option_pre_wait_ms": 600,    # 菜单项执行前主动等（关键，给上一步触发菜单留时间）
        "select_option_wait_after_ms": 400,  # 菜单选项点击后等待
        "click_wait_after_ms": 600,          # 普通点击后等待
        "fill_retry_with_type": True,        # fill 失败时退回 click+type
        "manual_checkpoint_enabled": True,   # 第一轮允许用户选择固定人工介入点
        "manual_prompt_skip_steps": 5,       # 用户可选择接下来 N 步不提示
    },

    # ── 已知的"纯文本输入框"容器 ──
    # 这些容器里点击 → 跳过（用户只是点输入框聚焦，blur 时再用 fill 记录）
    "input_wrapper_classes": [
        "el-input", "el-textarea", "el-input-number",
        "el-autocomplete",
        "ant-input", "ant-input-affix-wrapper", "ant-input-number",
        "n-input", "n-input-number",
        "van-field", "van-cell"
    ],

    # ── 已知的"下拉/弹层触发器"容器 ──
    # 这些容器里点击 → 必须记录（这是"打开下拉菜单"的关键步骤）
    # 没有这一步，后续的 select_option 找不到选项
    "trigger_wrapper_classes": [
        "el-select", "el-cascader",
        "el-date-editor", "el-time-editor",
        "el-color-picker",
        "el-dropdown", "el-dropdown-link",
        "ant-cascader-picker", "ant-select-selector",
        "ant-picker", "ant-dropdown-trigger",
        "n-base-selection", "n-base-selection-input",
        "n-dropdown",
    ],

    # ── 下拉菜单/选项节点的 class ──
    # 这些是"点击选项"应该被记录的元素 - 必须能穿过 input_wrapper 检测
    "option_classes": [
        "el-cascader-node", "el-select-dropdown__item", "el-option",
        "el-dropdown-menu__item", "el-menu-item",
        "el-date-table__cell", "el-time-spinner__item",
        "ant-cascader-menu-item", "ant-select-item-option",
        "ant-picker-cell", "ant-dropdown-menu-item", "ant-menu-item",
        "n-base-select-option", "n-cascader-option", "n-menu-item",
        "van-picker-column__item"
    ],

    # ── 重复点击检测 ──
    "duplicate_detection": {
        "enabled": True,
        "window_ms": 800,           # 800ms 内同一选择器视为重复
        "max_warnings": 3            # 一次会话最多警告几次
    },

    # ── 选择器优先级 ──
    "selector_priority": {
        # 按钮/链接优先用文本匹配
        "button_use_text": True,
        "button_text_max_length": 30,
        # ID 必须看起来稳定（不能是框架自动生成的随机串）
        "id_blacklist_prefixes": ["__", "el-id-", "n-id-", "ant-", "react-"],
        "id_max_length": 40,
        # 用作精确匹配的 data-* 属性
        "data_attrs": ["data-testid", "data-cy", "data-test", "data-id"],
        # 框架通用 class 黑名单（用 class 选择器时跳过）
        "generic_class_prefixes": [
            "el-", "ant-", "n-", "van-",
            "is-", "has-", "primary", "default", "success",
            "warning", "danger", "info", "disabled", "active",
            "hover", "focus", "small", "medium", "large",
            "block", "round", "circle", "btn", "button"
        ]
    },

    # ── 失焦记录规则 ──
    "blur_record": {
        "skip_readonly": True,       # readonly 输入不记录
        "skip_disabled": True,       # disabled 输入不记录
        "min_value_length": 0        # 空值也记录（删除场景）
    },

    # ── label 提取规则 ──
    "label_extraction": {
        "aria_label": True,
        "for_attribute": True,
        "parent_label": True,
        "form_item_containers": [
            "form-item", "el-form-item", "ant-form-item",
            "form_item", "form-group", "n-form-item"
        ],
        "form_item_label_selectors": [
            "label", ".form-item-label",
            ".el-form-item__label", ".ant-form-item-label",
            ".n-form-item-label", "[class*='label']"
        ],
        "placeholder_strip_prefix": ["请输入", "请选择", "请填写", "输入", "选择"]
    }
}


# ════════════════════════════════════════════════════════
#  本地存储 + 服务器拉取
# ════════════════════════════════════════════════════════

def _rules_file(data_dir: Path) -> Path:
    return data_dir / "rules.json"


def load_rules(data_dir: Path) -> dict:
    """优先读本地 rules.json，没有就用默认"""
    f = _rules_file(data_dir)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"读取本地规则失败：{e}，使用默认规则")
    return DEFAULT_RULES.copy()


def save_rules(data_dir: Path, rules: dict):
    f = _rules_file(data_dir)
    f.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def fetch_rules(token: Optional[str] = None) -> Optional[dict]:
    """从服务器拉最新规则。失败返回 None。"""
    try:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(f"{API_BASE}/rules", headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "input_wrapper_classes" in data:
                return data
            # 包装格式 {"rules": {...}}
            if isinstance(data, dict) and isinstance(data.get("rules"), dict):
                return data["rules"]
    except Exception as e:
        log.warning(f"拉取规则失败：{e}")
    return None


def update_from_server(data_dir: Path, token: Optional[str] = None) -> tuple[bool, str]:
    """从服务器拉规则并保存到本地。返回 (成功?, 提示)"""
    new = fetch_rules(token)
    if not new:
        return False, "无法连接服务器或服务器未提供规则"
    local = load_rules(data_dir)
    if new.get("version") == local.get("version"):
        return True, f"已是最新版本 v{new.get('version', '?')}"
    save_rules(data_dir, new)
    return True, f"知识库已更新到 v{new.get('version', '?')}"


def rules_to_js(rules: dict) -> str:
    """把规则序列化成 JS 代码，注入到浏览器供 inject.js 使用"""
    return f"window.__hbf_rules = {json.dumps(rules, ensure_ascii=False)};"
