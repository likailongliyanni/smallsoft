### EXP-029 防 0×0 隐藏占位陷阱（Vue/Element UI 必读）

**问题背景**：Vue + Element UI 的页面**经常**在 DOM 里有 0 尺寸（width=0 height=0）的隐藏占位元素，原因是：
1. Vue 模板预渲染（v-if 还没触发，但 DOM 已经渲染了空占位）
2. 同一个 form-item 在 dialog / drawer / tab 里被复用模板
3. el-select 的下拉项内部有重复的 form-item 结构

**典型现象**：实测 daoyeshan.com 的「规格类型」form-item 在 DOM 里有 2 份：
```
[0] 位置 (0,0) 0×0  ← Vue 模板预渲染的 0 尺寸隐藏占位
[1] 位置 (219,192) 548×32  ← 真正的表单项
```

**如果用 `.first` 直接锚定会取到 [0]，后果**：
- `scroll_into_view_if_needed()` 在 0 尺寸元素上**必然超时**
- 在 0 尺寸元素内 `.locator(...)` 找子元素也找不到
- click / fill 都会失败

---

## 规则 A：radio 单选项 → 全局找，不用 form-item 锚定

radio 选项的文字（"统一规格"、"是"、"否"、"启用"）在表单里通常**唯一**，可以直接全局找：

```json
// ❌ 错误：用 form-item 锚定 + .first（会取到 0×0 占位）
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"规格类型\") label.el-radio:has-text(\"统一规格\")"
}

// ✅ 正确：直接全局找 label.el-radio
{
  "type": "click",
  "selector": "label.el-radio:has-text(\"统一规格\")",
  "xpath": "<原 xpath>",
  "wait_after": 1500
}
```

**wait_after = 1500ms**：radio 选中后 Vue 会渲染子字段（如「统一规格」选中后展开 sku 信息），需要等渲染。

---

## 规则 B：fill / select 等需要 form-item 锚定的场景 → 用 `:visible` 过滤

输入框、下拉框需要 form-item 锚定（页面上多个 input 必须用 label 区分），加 `:visible` 伪类过滤掉 0×0：

```json
// ❌ 可能取到 0×0 占位
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"销售价(元)\") .el-input__inner"
}

// ✅ :visible 过滤后只取可见的
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"销售价(元)\") .el-input__inner",
  "xpath": "<原 xpath>",
  "from_excel": "销售价(元)"
}
```

注意：`:visible` 是 Playwright 扩展的伪类（不是 CSS 标准），runner 支持。

---

## 规则 C：用 JS 兜底校验

如果你担心 selector 仍然不稳，可以在 click/fill 后**补一步 JS 校验**（通过 runner 已有的能力）。但通常规则 A + B 已足够。

---

## 识别"可能踩坑"的步骤

满足以下任一条件，AI 必须用上面规则修正 selector：

1. step.action_type = `click` 且 selector 含 `.el-form-item:has-text(...).el-radio` 或类似
2. step.action_type = `fill` / `select_option` 且 selector 用了 `.el-form-item:has-text(...)` 但没有 `:visible`
3. step.label 是「规格类型」「是否上架」「启用状态」等典型有 0×0 占位风险的字段
4. **凡是 selector 含 `.first` 暗示** 的场景（其实 selector 不会含 .first，但 Playwright 默认 .first 行为同样有风险）

---

## 完整修复示例（daoyeshan「规格类型 = 统一规格」）

录制步骤：
```json
{
  "action_type": "click",
  "selector": ".el-form-item:has-text(\"规格类型\") .el-radio",
  "scoped_selector": ".el-form-item:has-text(\"规格类型\") .el-radio",
  "xpath": "/html/body/.../label",
  "label": "规格类型",
  "text": "统一规格"
}
```

AI 生成 action（按 EXP-029 规则 A 修正）：
```json
{
  "type": "click",
  "selector": "label.el-radio:has-text(\"统一规格\")",
  "xpath": "/html/body/.../label",
  "wait_after": 1500
}
```

后面如果还要填「统一规格名称」（radio 选中后展开的子字段）：
```json
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"统一规格名称\") .el-input__inner",
  "xpath": "<原 xpath>",
  "from_excel": "统一规格名称"
}
```

> 新规则：如果「统一规格名称」所在区域后面还有 `skuId/skuld / 商品编码 / 销售价 / 市场价 / 成本价 / 库存` 等嵌套 SKU 字段，则不要用上面的 `.el-form-item:visible:has-text(...)` 模板，改按 EXP-035 使用 `selector:"xpath=<step.xpath>"` 或“直接子 label XPath”。

---

## 铁律

- ✅ radio 类 click → 直接用 `label.el-radio:has-text("选项文字")`，**不要**套 form-item
- ✅ fill / select 类 → 加 `:visible` 过滤掉 0×0 占位
- ✅ radio 选中后 wait_after=1500（等 Vue 渲染子字段）
- ✅ xpath 字段保留（EXP-023）
- ❌ 不要用 `.el-form-item:has-text(LABEL) label.el-radio:has-text(OPTION)` 这种**双层 form-item 锚定**（一定会被 0×0 占位坑）
- ❌ 不要假设 `.first` 安全 —— Vue 框架下 `.first` 经常取到隐藏占位

---

## 实证数据（test-spec-radio.py 测试结果）

| 策略 | 实现方式 | 结果 |
|---|---|---|
| 策略 1 | `.el-form-item:has-text("规格类型").first` + scroll_into_view | ❌ scroll 超时（取到 0×0 元素） |
| 策略 2 | JS 全局找 label.el-radio + scrollIntoView | ✅ 成功 |
| 策略 3 | PageDown 滚屏 + Locator(`label.el-radio`) | ✅ 成功 |
| 策略 4 | mouse.wheel + Locator(`label.el-radio`) | ✅ 成功 |
| 策略 5 | JS 强制 input.checked = true | ✅ 成功 |

**结论**：只要不用 form-item 锚定（策略 2-5），全部成功。

---

## 第二轮实证：input/fill 也有 0×0 占位陷阱（v2）

继续测试 daoyeshan 的「统一规格名称」input，发现**输入框也有同样问题**：

**实测**：DOM 里有 2 个 input 都"匹配"「统一规格名称」：
```
[0] disabled=True placeholder=''  bounding_box={w:0, h:0}  ← 0×0 隐藏占位
[1] disabled=False placeholder='请输入规格名称'  bounding_box={w:200, h:32}  ← 真正可输入
```

错误流程：
- AI 生成的 selector：`.el-form-item:has-text("统一规格名称") .el-input__inner`
- runner 用 Playwright `.first` → 取到 [0] 那个 0×0 占位
- check 发现 `disabled: True, placeholder: ''` → 报错"input is disabled"

**修复**：
1. **AI 层（这条经验）**：所有 `.el-form-item:has-text(...)` 形式的 selector 都加 `:visible` 过滤
2. **runner 层（HANDOFF）**：`first_visible` 函数额外检查 `bounding_box().width/height > 0`

---

## 规则 D：fill 类 selector 总是加 :visible（强制）

不只是规格、价格字段——**所有** fill / select 类 action 的 selector 都应该加 `:visible`：

> 例外：嵌套 SKU / 统一规格 / 价格库存区域以 EXP-035 为准。因为外层 `skuId/skuld` 容器也会包含所有子字段文本，`:visible:has-text(...)` 仍可能填错到第一个 skuId input。

```json
// 旧的 EXP-007/008/009 模板（有 0×0 风险）
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"商品名称\") .el-input__inner",
  "from_excel": "商品名称"
}

// 新的安全模板（强制加 :visible）
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"商品名称\") .el-input__inner",
  "xpath": "<原 xpath>",
  "from_excel": "商品名称"
}
```

`:visible` 是 Playwright 扩展的伪类，会同时过滤：
- `display: none`
- `visibility: hidden`
- `opacity: 0`
- **width=0 或 height=0 的元素**（关键!）

---

## 完整修复模板（综合 EXP-029）

```
所有 click radio:      "label.el-radio:has-text(\"<选项>\")"
所有 click checkbox:   ".el-checkbox:visible:has-text(\"<选项>\") .el-checkbox__inner"  (或 label.el-checkbox)
所有 fill text:        ".el-form-item:visible:has-text(\"<字段>\") .el-input__inner"
所有 fill number:      ".el-form-item:visible:has-text(\"<字段>\") input"
所有 select 触发器:    ".el-form-item:visible:has-text(\"<字段>\") .el-input__inner"
所有 select 选项:      "li:visible:has-text(\"<选项>\")"  (EXP-027)
所有 cascader 触发器:  ".el-form-item:visible:has-text(\"<字段>\") .el-cascader"  (EXP-017)
所有 cascader 选项:    "li:visible:has-text(\"<选项>\")"  (EXP-022)
所有上传弹窗内的:      ".el-dialog__wrapper:visible <子 selector>"
```

**口诀**：含 `:has-text(LABEL)` 的地方,**前面或后面**都加 `:visible`,radio 类不需要（直接全局找文字）。
