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


def _step_is_sensitive(step: dict) -> bool:
    """这一步是否涉及敏感信息：密码类型，或标签/描述/列名命中敏感词。"""
    if step.get("input_type") == "password":
        return True
    haystack = " ".join([
        str(step.get("label", "")),
        str(step.get("description", "")),
        str(step.get("excel_column", "")),
    ])
    return _is_sensitive(haystack)


def sanitize_step(step: dict) -> dict:
    """脱敏单条步骤"""
    out = dict(step)
    if _step_is_sensitive(step):
        out["value"] = MASK
    return out


def sanitize_steps(steps: list) -> list:
    """脱敏整个步骤列表"""
    return [sanitize_step(s) for s in steps]


def sanitize_dsl(dsl: dict, steps=None) -> dict:
    """脱敏 DSL 中的 fill 指令。

    除了按 selector 关键词判断，还结合录制步骤（steps）：把 steps 里判定为敏感的
    原始值收集起来，DSL 里同值的 fill 一并隐藏——堵住「密码框 selector 不含敏感词
    （如 placeholder=请输入）导致明文密码随反馈上传」的漏洞。
    """
    sensitive_values = set()
    for s in (steps or []):
        if _step_is_sensitive(s):
            v = s.get("value")
            if v is not None and str(v) != "":
                sensitive_values.add(str(v))

    out = dict(dsl)
    actions = []
    for a in dsl.get("actions", []):
        ac = dict(a)
        if ac.get("type") == "fill":
            sel = str(ac.get("selector", ""))
            val = ac.get("value")
            if _is_sensitive(sel) or (val is not None and str(val) in sensitive_values):
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
