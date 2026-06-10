### EXP-037 弹窗 / 抽屉 / 编辑页内部滚动

很多后台点击「编辑」后，不是打开新页面，而是在当前页面叠一个弹窗或抽屉：

```text
/html/body/div[5]/div/div/section/...
/html/body/div[6]/div/div/section/...
```

这类弹层内部有自己的滚动区域。`{"type":"scroll","to":"bottom"}` 只滚主窗口，**不一定能滚动弹窗内部内容**，所以会出现“已经生成 scroll，但成本价/库存/提交按钮仍找不到”。

## 识别条件

满足任一条件，按本规则：

- 前一步点击了 `编 辑`、`编辑`、`查看`、`详情`
- 后续 xpath 以 `/html/body/div[4]`、`/html/body/div[5]`、`/html/body/div[6]`、`/html/body/div[7]` 开头
- 后续 xpath 包含 `/section/div/form/`
- 后续字段是 `成本价`、`销售价`、`市场价`、`库存`、`重量`、`体积`、`提交`

## 滚动规则

进入弹窗下方区域前，不要只写：

```json
{"type":"scroll","to":"bottom"}
```

优先写键盘滚动，让当前弹窗/抽屉内部滚动：

```json
{"type":"press","key":"PageDown"},
{"type":"delay","ms":300}
```

如果目标在很下面，可以连续两次：

```json
{"type":"press","key":"PageDown"},
{"type":"delay","ms":200},
{"type":"press","key":"PageDown"},
{"type":"delay","ms":300}
```

## 定位规则

弹窗/抽屉里的字段不要把 `/html/body/div[6]/...` 当主 selector。

错误：

```json
{
  "type":"fill",
  "selector":"xpath=/html/body/div[6]/div/div/section/div/form/div/div[3]/div/...",
  "xpath":"/html/body/div[6]/div/div/section/div/form/div/div[3]/div/...",
  "from_excel":"成本价(元)"
}
```

正确：用 EXP-035 的直接子 label XPath：

```json
{
  "type":"fill",
  "selector":"xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '成本价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '成本价')]]//input[not(@disabled) and not(@readonly)][1]",
  "xpath":"/html/body/div[6]/div/div/section/div/form/div/div[3]/div/div/div[2]/div/div/div[2]/div/div/div/div/div/form/div[6]/div/div/div/input",
  "from_excel":"成本价(元)"
}
```

## 完整示例：搜索后编辑成本价

```json
[
  {"type":"fill","selector":".el-form-item:visible:has-text(\"商品编码\") .el-input__inner","xpath":"<搜索框 xpath>","from_excel":"商品编码"},
  {"type":"click","selector":"button:has-text(\"搜 索\")","xpath":"<搜索按钮 xpath>","wait_after":1500},
  {"type":"click","selector":"button:has-text(\"编 辑\")","xpath":"<编辑按钮 xpath>","wait_after":1200},
  {"type":"press","key":"PageDown"},
  {"type":"delay","ms":300},
  {
    "type":"click",
    "selector":"xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '成本价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '成本价')]]",
    "xpath":"<成本价 form-item 原 xpath>",
    "wait_after":200
  },
  {
    "type":"fill",
    "selector":"xpath=//*[contains(concat(' ',normalize-space(@class),' '),' el-form-item ')][./label[contains(normalize-space(.), '成本价')] or ./*[contains(@class,'el-form-item__label') and contains(normalize-space(.), '成本价')]]//input[not(@disabled) and not(@readonly)][1]",
    "xpath":"<成本价 input 原 xpath>",
    "from_excel":"成本价(元)"
  },
  {"type":"press","key":"PageDown"},
  {"type":"delay","ms":300},
  {"type":"click","selector":"button:has-text(\"提交\")","xpath":"<提交按钮 xpath>","wait_after":1000}
]
```

## 最后自检

- 编辑弹窗内是否还在用 `/html/body/div[6]/...` 作为主 selector？如果是，改成 label XPath。
- 编辑弹窗内是否只用了 `scroll bottom`？如果是，改成 `press PageDown`。
- 提交按钮是否在弹窗底部？如果是，提交前再 `press PageDown`。
