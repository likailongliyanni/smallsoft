### EXP-036 长页面 / 滚动后控件必须显式生成 scroll

录制器目前可能不会记录鼠标滚轮。用户手动滚动后再点击下方控件时，steps 里只看到“点击/输入”，看不到“滚动”。运行时如果页面还停在上方，就会找不到或点不到目标。

## 什么时候必须补 scroll

满足任一条件，必须在对应 click/fill/upload 前插入 `scroll`：

- 目标字段通常在页面下半部分：`描述`、`详情`、`详情图`、`库存`、`预警库存`、`重量`、`体积`、`规格`、`sku`、`销售价`、`市场价`、`成本价`
- 目标按钮通常在底部或右下角：`保存`、`提交`、`下一步`、`完成`
- step.target_box.y 接近视口底部，例如 `target_box.y > viewport.height - 120`
- 连续步骤的 xpath 从上方表单区跳到后面很深的 div，例如从 `form/div[2]` 跳到 `form/div[5]`、`form/div[6]`
- 用户流程里先填基础信息，后面突然操作富文本、图片描述、库存价格等下方区域

## scroll 输出格式

runner 支持：

```json
{"type": "scroll", "to": "bottom"}
{"type": "scroll", "to": "top"}
{"type": "scroll", "selector": ".css-selector"}
{"type": "press", "key": "PageDown"}
```

注意：

- `scroll.selector` 必须是普通 CSS selector，不能写 `xpath=...`。
- 如果目标只有 xpath，没有稳定 CSS selector，就用 `{"type":"scroll","to":"bottom"}`。
- 如果目标在「编辑弹窗 / 抽屉 / dialog」内部，`scroll bottom` 可能只滚主窗口，不滚弹窗内部；这时以 EXP-037 为准，用 `{"type":"press","key":"PageDown"}`。
- scroll 后建议补一个短 delay，让浏览器布局稳定：

```json
{"type":"scroll","to":"bottom"},
{"type":"delay","ms":300}
```

## 常见模板

### 模板 A：保存按钮在页面底部

```json
[
  {"type":"scroll","to":"bottom"},
  {"type":"delay","ms":300},
  {"type":"click","selector":"button:has-text(\"保 存\")","xpath":"<原 xpath>","wait_after":1000}
]
```

### 模板 B：滚到详情/描述区域再上传详情图

```json
[
  {"type":"scroll","to":"bottom"},
  {"type":"delay","ms":300},
  {
    "type":"upload_folder_to_library",
    "selector":"input[type=\"file\"][accept*=\"image\"], .el-dialog__wrapper input[type=\"file\"]",
    "xpath":"<原 xpath>",
    "from_excel":"详情图目录",
    "file_extensions":["jpg","jpeg","png","gif","webp"],
    "item_selector":"label.material-name, .ql-editor img",
    "select_strategy":"last_n",
    "wait_timeout":300000,
    "wait_after":1500
  }
]
```

### 模板 C：价格/库存区域在统一规格下方

如果前面选择了“统一规格”，然后要填写销售价、市场价、成本价、库存等字段，先滚到下方：

```json
[
  {"type":"scroll","to":"bottom"},
  {"type":"delay","ms":300},
  {"type":"fill","selector":"xpath=<销售价 input xpath>","xpath":"<销售价 input xpath>","from_excel":"销售价(元)"}
]
```

## 不要滥用

- 在页面顶部连续填写商品名称、品牌、类目时，不要插 scroll。
- 普通下拉菜单打开和选择之间不要插 scroll，会导致下拉关闭。
- cascader 多级选择中间不要插 scroll。

## 最后自检

生成 DSL 前检查：

- 是否有底部按钮/详情图/富文本/库存价格字段，却没有任何 scroll？
- 是否有点击 `保 存`、`提交`、`完成` 这类底部按钮前没有 scroll？
- 是否从基础信息跳到下方区域时没有 scroll？

如果不确定，宁可在进入下方区域前插入：

```json
{"type":"scroll","to":"bottom"},
{"type":"delay","ms":300}
```
