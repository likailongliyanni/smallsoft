### EXP-021 触发器永远不用 text="当前选中值" 作为 selector

这条专门解决「下拉框 selector 用 `text="集采不含运"` 这种用户当前选中值，重跑必崩」的问题。

**核心规则**：当 step 的 action_label 是「打开下拉」或 is_trigger=true 时：
- ❌ **绝对不要**用 `text="<当前选中值>"` 当 selector（重跑时表单是空的，那串字不存在）
- ❌ **绝对不要**用 `#cascader-menu-3584-0-0` 这种带随机数字的 id

**触发器 selector 用什么** —— 由 EXP-027 统一规定：
- selector：`.el-form-item:has-text("LABEL") .el-input__inner`（**EXP-027 已经覆盖原录制的 scoped_selector**）
- 例外：cascader 触发器仍用录制的 scoped_selector（见 EXP-017 / EXP-022）

---

**"selector 不稳定"的标志**：
- `selector` 以 `text=` 开头 → 不稳定（必改）
- `selector` 用了 `#cascader-menu-XXXX-0-0` 这种带随机数字 id → 不稳定（必改）
- `selector` 含 `:has-text("<某中文长字符串>")` 但 step 是触发器 → 大概率是录制时把当前值当 selector 了 → 必改

---

**修复方法**：

录制数据：
```json
{
  "action_type": "click",
  "action_label": "打开下拉",
  "selector": "text=\"集采不含运\"",              // ❌ 不稳定
  "scoped_selector": ".el-form-item:has-text(\"运费模板\") .avue-select",
  "xpath": "/html/body/div[4]/...",
  "label": "运费模板",
  "is_trigger": true
}
```

→ 生成 action（用 EXP-027 的规则改写）：
```json
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"运费模板\") .el-input__inner",
  "xpath": "/html/body/div[4]/...",
  "wait_after": 1500
}
```

注意：**EXP-027 推荐用 `.el-input__inner` 而不是 `.avue-select` 等外层 div**，因为 click input 更可靠地触发下拉打开。
