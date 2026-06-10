### EXP-030 input 默认 disabled / 需要 click 激活的模式

**问题背景**：很多后台系统（如 daoyeshan.com 的 sku 表单）的 input **默认是 disabled 状态**，必须先点击 input 所在区域才能进入编辑模式。这是某些系统的设计——防止误触，需要明确激活才能输入。

**实测现象**：
- 录制时用户**先点击 input 区域，再输入文字**（看似两个独立操作）
- 不点击直接 fill → 报错 "input is disabled" 或 fill 后值丢失

---

## 识别方法

满足以下条件就是激活模式：

1. 一个 step 是 `click`，紧跟着的 step 是 `input` / `fill`
2. 两个 step 的 label 相同 或 都指向同一个 form-item
3. click 的 scoped_selector 看起来"多余"（点击的不是按钮、不是 input 本身，而是 input 的父容器/标签区）

**典型例子**（daoyeshan 录制的 sku 价格字段）：
```json
// step 19
{
  "action_type": "click",
  "selector": ".el-form-item:has-text(\"skuId\") .el-form-item",
  "label": "销售价(元)",
  "text": "销售价(元)"
}

// step 20
{
  "action_type": "input",
  "selector": "input[placeholder=\"...\"]",
  "scoped_selector": ".el-form-item:has-text(\"销售价(元)\") .el-input__inner",
  "label": "销售价(元)",
  "value": "99.00",
  "excel_column": "销售价(元)"
}
```

---

## 生成规则（铁律）

**绝对不要把 fill 前的 click 去重或合并**！即使看起来"没必要"。

```json
// ✅ 正确：保留 click 步骤（激活）+ fill 步骤
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"销售价(元)\")",
  "xpath": "<原 click 的 xpath>",
  "wait_after": 200
},
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"销售价(元)\") .el-input__inner",
  "xpath": "<原 fill 的 xpath>",
  "from_excel": "销售价(元)"
}

// ❌ 错误：把 click 当多余的去掉,只留 fill
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"销售价(元)\") .el-input__inner",
  "from_excel": "销售价(元)"
}
// 运行时:input 是 disabled 的,fill 失败
```

---

## click 步骤的 selector 修正

录制时 click 的 scoped_selector 经常是 **父容器**（如 `:has-text("skuId")`），多个 fill 前的 click 撞同一个 selector → 配合 EXP-026 用 **step.text** 重写：

```json
// 录制原始 click step
{
  "scoped_selector": ".el-form-item:has-text(\"skuId\") .el-form-item",
  "label": "销售价(元)",
  "text": "销售价(元)"
}

// 按 EXP-026 + EXP-030 生成
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"销售价(元)\")",
  "xpath": "<原 xpath>",
  "wait_after": 200
}
```

---

## 标准模板：disabled-input 字段的 click + fill

每个需要"先点击再输入"的字段，生成 2 个 action：

```json
// 1. 点击激活 (wait_after 200~300ms 让 input 进入编辑态)
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"<字段名>\")",
  "xpath": "<原 xpath>",
  "wait_after": 200
},
// 2. 填值
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"<字段名>\") .el-input__inner",
  "xpath": "<原 xpath>",
  "from_excel": "<Excel 列名>"
}
```

---

## 适用范围

| 字段类型 | 是否需要激活 click |
|---|---|
| 普通文本 input（商品名称、品牌名） | ❌ 通常不需要 |
| 价格输入（销售价、市场价等数字） | ✅ daoyeshan 实测需要 |
| sku 表单内的字段 | ✅ daoyeshan 实测需要 |
| el-input-number 数字控件 | ⚠️ 看实现,el-input-number 外层 div 点击通常会激活内部 input |
| 弹窗内的 input | ⚠️ 看实现 |

**规则**：录制时**如果用户实际点了**（哪怕看起来多余），就保留 click。不要 AI 自己判断"这个 click 没必要"。

---

## 铁律

- ✅ 录制里 fill 前有 click（同一个 label）→ **必须保留** click（违反 EXP-020 的"不合并"原则的具体情况之一）
- ✅ click 的 selector 用 step.text 重写为精确的 `.el-form-item:has-text("具体字段名")`（EXP-026）
- ✅ click 的 wait_after 给 200~300ms（让 input 切换到编辑态）
- ❌ 不要把 fill 前的 click 当"多余"去重
- ❌ 不要假设"Playwright 的 fill 会自动 focus"——对 disabled input 不行

---

## 完整流程示例（daoyeshan sku 表单）

> 注意：如果页面是嵌套 SKU / 统一规格区域，`.el-form-item:has-text("销售价(元)")` 仍可能先匹配到外层 `skuId/skuld` 容器。遇到 `统一规格名称 / 商品编码 / 销售价 / 市场价 / 成本价 / 库存` 等字段时，以 EXP-035 为准，click/fill 的 `selector` 优先用 `xpath=<step.xpath>`。

```json
[
  // 销售价
  {"type":"click","selector":".el-form-item:has-text(\"销售价(元)\")","xpath":"...","wait_after":200},
  {"type":"fill","selector":".el-form-item:has-text(\"销售价(元)\") .el-input__inner","xpath":"...","from_excel":"销售价(元)"},

  // 市场价 (同模板)
  {"type":"click","selector":".el-form-item:has-text(\"市场价(元)\")","xpath":"...","wait_after":200},
  {"type":"fill","selector":".el-form-item:has-text(\"市场价(元)\") .el-input__inner","xpath":"...","from_excel":"市场价(元)"},

  // 成本价、集采价、集采市场价、库存,同样的 click+fill 模板
  ...
]
```
