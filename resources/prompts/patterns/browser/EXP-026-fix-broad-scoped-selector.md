### EXP-026 修正录制时过于宽泛的 scoped_selector

**问题背景**：

录制器在某些场景下生成的 scoped_selector 取了**外层父容器**（比如 sku 规格组的 skuId 整个表单组），导致同一个 selector 在页面上匹配到多个元素。Playwright 严格模式下会直接报错 `matched multiple elements`，runner 完全跑不动。

**典型现象**（来自实际录制数据）：

```json
// steps.json 里多个 click 步骤的 scoped_selector 完全相同
step 19: {"scoped_selector": ".el-form-item:has-text(\"skuId\") .el-form-item", "label": "销售价(元)", "text": "销售价(元)"}
step 23: {"scoped_selector": ".el-form-item:has-text(\"skuId\") .el-form-item", "label": "销售价(元)", "text": "集采价(元)"}
step 25: {"scoped_selector": ".el-form-item:has-text(\"skuId\") .el-form-item", "label": "市场价(元)", "text": "集采市场价(元)"}
step 27: {"scoped_selector": ".el-form-item:has-text(\"skuId\") .el-form-item", "label": "skuId", "text": "库存"}
```

scoped_selector 一模一样 → 运行时 Playwright 不知道点哪个 → 全部失败。

**但是！step.text 是对的**，只是录制时 scoped 取错了父级。

---

**识别方法**（满足 1 条以上就是这种情况）：

1. 一个 step 的 scoped_selector 含 `:has-text("skuId")` 或其他通用容器名（如 `:has-text("规格")`、`:has-text("基本信息")` 等明显是分组标题的）
2. 同一份录制里有 **多个 step 的 scoped_selector 完全相同**（说明都退到了同一个父级）
3. step.text 字段有精确的字段名（不是空、不是分组标题）
4. step.text 跟 step.label 不一致（label 是错的父级标题，text 是用户实际点的元素文字）

---

**修正规则**：

把 click 步骤的 selector 用 **step.text** 重写为精确的 `.el-form-item:has-text("<step.text>")`：

```json
// 原始 step（录制数据）
{
  "action_type": "click",
  "selector": ".el-form-item:has-text(\"skuId\") .el-form-item",
  "scoped_selector": ".el-form-item:has-text(\"skuId\") .el-form-item",
  "xpath": "/html/body/.../form/div[4]/div[2]",
  "label": "销售价(元)",
  "text": "集采价(元)"  ← 用这个！
}

// 生成的 action（修正后）
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"集采价(元)\")",  ← 用 step.text 重写
  "xpath": "/html/body/.../form/div[4]/div[2]"  ← xpath 仍然保留作兜底
}
```

---

**完整示例**（对应录制_0526_151804 的 sku 规格组）：

```json
// step 19 (click 激活销售价区域)
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"销售价(元)\")",
  "xpath": "/html/body/div[4]/div/div/section/div/form/div/div[3]/div/div/div[2]/div/div/div[2]/div/div/div/div/div/form/div[4]/div"
}

// step 20 (fill 销售价)
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"销售价(元)\") .el-input__inner",
  "xpath": "/html/body/.../form/div[4]/div/div/div/div/input",
  "from_excel": "销售价(元)"
}

// step 23 (click 激活集采价区域)
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"集采价(元)\")",
  "xpath": "/html/body/.../form/div[4]/div[2]"
}

// step 24 (fill 集采价)
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"集采价(元)\") .el-input__inner",
  "xpath": "/html/body/.../form/div[4]/div[2]/div/div/div/input",
  "from_excel": "集采价(元)"
}

// step 25 (click 激活集采市场价区域) — 同样修正
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"集采市场价(元)\")",
  "xpath": "/html/body/.../form/div[5]/div[2]"
}

// step 27 (click 激活库存区域) — 同样修正
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"库存\")",
  "xpath": "/html/body/.../form/div[7]"
}
```

---

**铁律**：
- ✅ 保留 click 步骤（不要删，遵守 EXP-020）
- ✅ 用 step.text 重写 click 的 selector（**优先级高于 scoped_selector**）
- ✅ xpath 字段必须保留（EXP-023）
- ✅ 紧跟的 fill 步骤继续用它自己的精确 scoped_selector（`.el-form-item:has-text("<字段名>") .el-input__inner`）
- ❌ 不要保留宽泛的 `.el-form-item:has-text("skuId") .el-form-item`（会匹配多个，报 strict mode 错）
- ❌ 不要用 step.label（这种情况下 label 是错的父级标题，不是用户点的元素）
- ❌ 不要直接删 click（违反 EXP-020）

---

**边界情况**：
- 如果 step.text 也是分组标题（如 "skuId"、"规格信息"），说明用户真的点的是分组标题 → 这时选 `.el-form-item:has-text("<text>")` 也是对的（精确匹配那个分组）
- 如果 step.text 为空 → 退回用 xpath 作兜底：`selector: "xpath=<step.xpath>"`
- 如果有多个 step.text 相同（比如 2 个"销售价(元)"按钮），需要再用 `:nth-of-type` 区分 —— 这种情况罕见，先按 step.xpath 兜底
