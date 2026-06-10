### EXP-035 嵌套 SKU / 统一规格 / 价格字段必须用精确 label 定位

很多商城后台的 SKU 区域是**嵌套表单**：

```text
skuId
统一规格名称
商品编码
销售价(元)
市场价(元)
成本价(元)
库存
```

这些字段经常在同一个外层容器里。外层容器虽然标题是 `skuId`，但它的文本内容包含下面所有字段名，所以这种 selector 仍然可能点错：

```json
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"商品编码\") .el-input__inner"
}
```

Playwright 可能先匹配到外层 `skuId` 容器，然后填进第一个 input，也就是上方的 `skuId/skuld` 输入框。

## 适用字段

只要字段名包含下面任意文字，就按本规则处理：

- `统一规格名称`
- `商品编码`
- `sku标识`
- `skuId`
- `销售价`
- `市场价`
- `成本价`
- `集采价`
- `集采市场价`
- `库存`
- `预警库存`
- `重量`
- `体积`
- `利润`
- `毛利率`

## 铁律：不要用 `.el-form-item:has-text(...) .el-input__inner`

在 SKU / 价格 / 库存区域，下面这些都不够安全：

```json
{"selector": ".el-form-item:has-text(\"商品编码\") .el-input__inner"}
{"selector": ".el-form-item:visible:has-text(\"销售价(元)\") .el-input__inner"}
{"selector": "input[type=\"text\"]"}
{"selector": ".el-input__inner"}
```

原因：父级容器也会包含这些文字，导致命中父级里的第一个 input。

## fill 正确模板：优先用“直接子 label XPath”

SKU/价格字段经常出现在弹窗/抽屉里，原始 `step.xpath` 常常长这样：

```text
/html/body/div[6]/div/div/section/div/form/...
```

这里的 `div[6]` 是动态弹窗层级，运行时可能变成 `div[5]`、`div[7]`，所以**不要把这种原始绝对 xpath 当主 selector**。

最终 `selector` 优先使用“直接子 label XPath”，不要依赖 `/html/body/div[6]`：

```json
{
  "type": "fill",
  "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '<字段名>')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '<字段名>')]]//input[not(@disabled) and not(@readonly)][1]",
  "xpath": "<step.xpath>",
  "from_excel": "<字段名>"
}
```

示例：

```json
{
  "type": "fill",
  "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '成本价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '成本价')]]//input[not(@disabled) and not(@readonly)][1]",
  "xpath": "/html/body/div[6]/div/div/section/div/form/div/div[3]/div/div/div[2]/div/div/div[2]/div/div/div/div/div/form/div[6]/div/div/div/input",
  "from_excel": "成本价(元)"
}
```

## 什么时候才用 `selector: "xpath=<step.xpath>"`

只有当 `step.xpath` 不含动态弹层根节点时才可直接作为主 selector。

可以直接用：

- `/html/body/div/div/...` 这类主页面固定结构
- 已经是稳定业务容器下的 xpath

不要直接用：

- `/html/body/div[4]/...`
- `/html/body/div[5]/...`
- `/html/body/div[6]/...`
- 任何弹窗、抽屉、popover 里的 `/html/body/div[N]/...`

这些必须改成“直接子 label XPath”。

## 直接子 label XPath 模板

```json
{
  "type": "fill",
  "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '<字段名>')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '<字段名>')]]//input[not(@disabled) and not(@readonly)][1]",
  "xpath": "<原 xpath>",
  "from_excel": "<字段名>"
}
```

关键点：

- `./label[...]` 是**直接子 label**，不会匹配外层 `skuId` 大容器。
- `[not(@disabled)]` 避免填到只读/禁用的 `skuId/skuld`。
- `[not(@readonly)]` 避免填到只读展示框。
- `selector` 本身就是 XPath，不要只把 xpath 放在 `xpath` 字段。

## click 激活步骤正确模板

如果录制里 fill 前有 click 激活步骤，也不要用父级 `skuId`：

错误：

```json
{"type":"click","selector":".el-form-item:has-text(\"skuId\") .el-form-item"}
```

正确：

```json
{
  "type": "click",
  "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '<字段名>')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '<字段名>')]]",
  "xpath": "<原 click xpath>",
  "wait_after": 200
}
```

如果原 click 的 xpath 在弹窗 `/html/body/div[N]/...` 里，不要直接做主 selector，只保留到 `xpath` 字段里做兜底。

只有原 click xpath 不含动态弹窗根节点时，才可以直接：

```json
{
  "type": "click",
  "selector": "xpath=<step.xpath>",
  "xpath": "<step.xpath>",
  "wait_after": 200
}
```

## 对图片中这类字段的标准输出

```json
[
  {
    "type": "fill",
    "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '统一规格名称')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '统一规格名称')]]//input[not(@disabled) and not(@readonly)][1]",
    "xpath": "<统一规格名称 input 的 step.xpath>",
    "from_excel": "统一规格名称"
  },
  {
    "type": "fill",
    "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '商品编码')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '商品编码')]]//input[not(@disabled) and not(@readonly)][1]",
    "xpath": "<商品编码 input 的 step.xpath>",
    "from_excel": "商品编码"
  },
  {
    "type": "click",
    "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '销售价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '销售价')]]",
    "xpath": "<销售价区域 click 的 step.xpath>",
    "wait_after": 200
  },
  {
    "type": "fill",
    "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '销售价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '销售价')]]//input[not(@disabled) and not(@readonly)][1]",
    "xpath": "<销售价 input 的 step.xpath>",
    "from_excel": "销售价(元)"
  },
  {
    "type": "fill",
    "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '市场价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '市场价')]]//input[not(@disabled) and not(@readonly)][1]",
    "xpath": "<市场价 input 的 step.xpath>",
    "from_excel": "市场价(元)"
  },
  {
    "type": "fill",
    "selector": "xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '成本价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '成本价')]]//input[not(@disabled) and not(@readonly)][1]",
    "xpath": "<成本价 input 的 step.xpath>",
    "from_excel": "成本价(元)"
  }
]
```

## 最后自检

生成 DSL 前逐条检查：

- SKU / 价格 / 库存字段的 `selector` 是否还包含 `.el-form-item:has-text(...) .el-input__inner`？如果有，改成“直接子 label XPath”。
- selector 是否直接用了 `/html/body/div[5]`、`/html/body/div[6]` 这类弹层绝对 xpath？如果有，改成“直接子 label XPath”，把原 xpath 只保留在 `xpath` 字段。
- 是否还用 `skuId`、`skuld`、`规格` 这种父级标题定位后续字段？如果有，必须改。
- 是否可能填到 disabled/readonly 的 skuId 输入框？如果可能，必须用具体 input xpath。
