### EXP-009 下拉菜单 + Excel 数据映射

**前置条件**：select_option 之前**必须**有"打开下拉"的 click（见 EXP-011），否则下拉是关着的，怎么都找不到选项。

**重要**：本规则被 **EXP-027** 进一步增强（默认补 fill 关键字搜索），请同时参考 EXP-027。如果两者有差异，**以 EXP-027 为准**。

---

当 step 满足 `action_type=select_option` **且** `excel_column 非空` 时，输出：

```json
{
  "type": "select_option",
  "from_excel": "<excel_column 的值>",
  "match_by_text": true,
  "selector": "li:has-text(\"<step.text 的值>\")",
  "xpath": "<step.xpath 的值>",
  "wait_after": 400
}
```

**关键**：必须**同时输出** from_excel + selector + xpath 这 3 个字段。
- 运行时优先用 from_excel 从 Excel 当前行取文本动态生成新 selector
- 如果 Excel 数据缺失/为空，自动回退到 selector 或 xpath（即录制时的原始选项）

**selector 形式**：用 `li:has-text("...")` 而不是 `text="..."`（li:has-text 更宽容，匹配各种 li 容器内的文本，包括 .el-select-dropdown__item、.ant-select-item、role=option 的 li 等）。

例：
- step: `{"action_type":"select_option","selector":"text=\"全部商品\"","xpath":"/html/body/.../li","text":"全部商品","excel_column":"菜单项_1"}`
- ✅ 生成：
```json
{
  "type": "select_option",
  "from_excel": "菜单项_1",
  "match_by_text": true,
  "selector": "li:has-text(\"全部商品\")",
  "xpath": "/html/body/.../li",
  "wait_after": 400
}
```

**禁止**：
- ❌ 只输出 from_excel 而不带 selector/xpath（没兜底）
- ❌ 把前一步的"打开下拉" click 删掉（下拉就关着，永远找不到选项）
- ❌ selector 用 `text="..."`（不够宽容，推荐 `li:has-text("...")`）
