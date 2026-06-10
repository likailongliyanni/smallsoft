### EXP-031 fill 的 selector 必须是最终可执行的精确定位

**问题背景**：
有些录制步骤里同时有两个定位字段：
- `selector`: 录制器原始选择器，例如 `input[type="text"]`
- `scoped_selector`: 带字段名范围的选择器，例如 `.el-form-item:has-text("销售价(元)") .el-input__inner`

如果最终 DSL 仍把 `action.selector` 输出成 `input[type="text"]`，runner 可能只使用或优先使用这个宽泛 selector，结果反复命中页面第一个文本框，例如 sku 表单里的 `skuld`，导致销售价、市场价、成本价、库存等值全部填错位置。

---

## 铁律：action.selector 本身必须精确

最终 JSON 里的 `selector` 字段就是 runner 的主定位器，不能把精确定位只放在 `scoped_selector` 字段里。

当 step 是 `fill` / `input`，并且满足以下任一条件时，必须重写最终 `action.selector`：
1. `step.selector` 是宽泛输入框：`input[type="text"]`、`input`、`.el-input__inner`、`textarea`。
2. `step.selector` 不含字段名，但 `step.scoped_selector` 含 `.el-form-item:has-text(...)`。
3. `step.excel_column` 或 `step.label` 能明确指出字段名。

---

## 重写规则

优先使用 `step.scoped_selector`，但要把 `.el-form-item:has-text(...)` 改成 `.el-form-item:visible:has-text(...)`：

```json
// 错误：主 selector 太宽泛，会填到第一个 input，例如 skuld
{
  "type": "fill",
  "selector": "input[type=\"text\"]",
  "scoped_selector": ".el-form-item:has-text(\"销售价(元)\") .el-input__inner",
  "from_excel": "销售价(元)"
}

// 正确：selector 本身就是精确定位
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"销售价(元)\") .el-input__inner",
  "xpath": "<原 xpath>",
  "from_excel": "销售价(元)"
}
```

如果 `step.scoped_selector` 为空，但 `step.label` 或 `step.excel_column` 非空，则基于字段名生成：

```json
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"<字段名>\") .el-input__inner",
  "xpath": "<原 xpath>",
  "from_excel": "<Excel 列名>"
}
```

字段名优先级：`step.excel_column` > `step.label` > `step.text`。

---

## Element UI 数字输入框模板

daoyeshan / Element UI 的价格、库存、重量、体积等数字输入框，经常录制成 `input[type="text"]`。这些字段必须输出为带表单项锚点的 selector：

```json
[
  {
    "type": "click",
    "selector": ".el-form-item:visible:has-text(\"销售价(元)\") .el-input-number",
    "xpath": "<原 click xpath>",
    "wait_after": 200
  },
  {
    "type": "fill",
    "selector": ".el-form-item:visible:has-text(\"销售价(元)\") .el-input__inner",
    "xpath": "<原 fill xpath>",
    "from_excel": "销售价(元)"
  },
  {
    "type": "fill",
    "selector": ".el-form-item:visible:has-text(\"市场价(元)\") .el-input__inner",
    "xpath": "<原 fill xpath>",
    "from_excel": "市场价(元)"
  },
  {
    "type": "fill",
    "selector": ".el-form-item:visible:has-text(\"库存\") .el-input__inner",
    "xpath": "<原 fill xpath>",
    "from_excel": "库存"
  }
]
```

> 重要升级：如果字段位于 SKU / 统一规格 / 价格库存的**嵌套表单区域**，外层 `skuId/skuld` 容器会包含下面所有字段文本，`.el-form-item:visible:has-text(...) .el-input__inner` 仍可能命中外层并填到 skuId。此时以 EXP-035 为准，最终 `selector` 优先写成 `xpath=<step.xpath>`，或使用 EXP-035 的“直接子 label XPath”模板。

---

## 禁止输出

- 不要输出 `selector: "input[type=\"text\"]"` 作为 fill 的最终主 selector。
- 不要输出 `selector: "input"` 作为 fill 的最终主 selector。
- 不要输出 `selector: ".el-input__inner"` 作为 fill 的最终主 selector。
- 不要只把精确定位放在 `scoped_selector`，最终 DSL 的 `selector` 必须已经精确。
- 不要依赖 runner 去理解 `scoped_selector`，因为不同 runner 可能忽略它。

---

## 最后自检

生成 DSL 前逐条检查：
- 每个 `fill` 的 `selector` 是否能从页面上定位到唯一的业务字段？
- 如果同一页有多个输入框，`selector` 是否包含字段名或可见表单项锚点？
- 价格/库存/SKU 字段是否还残留 `input[type="text"]`？
- 如果答案不确定，优先用 `.el-form-item:visible:has-text("<字段名>") .el-input__inner`。
