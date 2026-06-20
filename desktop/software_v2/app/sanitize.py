"""
反馈数据脱敏 —— 上传给作者前自动隐藏敏感字段。
"""

# 敏感字段关键词（label/description 中包含这些 → 隐藏 value）
SENSITIVE_KEYWORDS = [
    "密码", "password", "pwd", "pass",
    "验证码", "captcha", "verify code",
    "身份证", "id card", "idcard",
    "银行卡", "信用卡", "card no",
    "支付密码", "pay password",
]

MASK = "***已隐藏***"


def _is_sensitive(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k.lower() in t for k in SENSITIVE_KEYWORDS)


def sanitize_step(step: dict) -> dict:
    """脱敏单条步骤"""
    out = dict(step)
    # 1. password 类型直接隐藏
    if step.get("input_type") == "password":
        out["value"] = MASK
        return out
    # 2. 标签/描述包含敏感词
    if step.get("action_type") == "input":
        haystack = " ".join([
            str(step.get("label", "")),
            str(step.get("description", "")),
            str(step.get("excel_column", "")),
        ])
        if _is_sensitive(haystack):
            out["value"] = MASK
    return out


def sanitize_steps(steps: list) -> list:
    """脱敏整个步骤列表"""
    return [sanitize_step(s) for s in steps]


def sanitize_dsl(dsl: dict) -> dict:
    """脱敏 DSL 中的 fill 指令"""
    out = dict(dsl)
    actions = []
    for a in dsl.get("actions", []):
        ac = dict(a)
        if ac.get("type") == "fill":
            # 用 selector 里的 placeholder 来判断敏感
            sel = str(ac.get("selector", ""))
            if _is_sensitive(sel):
                ac["value"] = MASK
        actions.append(ac)
    out["actions"] = actions
    return out


def preview(data: dict, max_len: int = 600) -> str:
    """生成给用户看的预览文本（带脱敏标记）"""
    import json
    txt = json.dumps(data, ensure_ascii=False, indent=2)
    if len(txt) > max_len:
        txt = txt[:max_len] + "\n... (省略，完整内容会发送)"
    return txt
