### EXP-010 下拉菜单 + 固定选项

当 step.action_type=select_option **且** step.excel_column 为空时（每次都选同一个固定选项）：

```json
{
  "type": "select_option",
  "selector": "li:has-text(\"<step.text 的值>\")",
  "xpath": "<step.xpath>",
  "wait_after": 400
}
```

例：
- step: `{"action_type":"select_option","text":"集采不含运","xpath":"...","excel_column":""}`
- ✅ 生成：`{"type":"select_option","selector":"li:has-text(\"集采不含运\")","xpath":"...","wait_after":400}`

**selector 形式**：跟 EXP-009 一致，用 `li:has-text("...")` 而不是 `text="..."`（兼容性更好）。

**重要**：本规则被 **EXP-027** 增强（默认前面要有 click + fill），请同时看 EXP-027。
