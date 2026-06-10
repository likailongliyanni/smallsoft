### EXP-034 表格复选框 / 表头全选 / 批量操作

后台管理系统里，表格勾选行、表头全选经常录制成：

```json
{
  "action_type": "click",
  "selector": "label",
  "xpath": "/html/body/.../table/thead/tr/th/div/label",
  "label": null,
  "text": null,
  "description": "点击「按钮」"
}
```

这种 `selector: "label"` **绝对不能直接输出**。页面上通常有很多表单 label，比如“标签:”“商品编码:”，runner 会先点到第一个 label，导致点错或 outside viewport。

## 识别条件

满足任一条件，都按“表格复选框”处理：

- `step.xpath` 包含 `/table/`、`/thead/`、`/tbody/`、`/th/`、`/td/`
- `step.xpath` 或 `selector/scoped_selector` 含 `el-table`、`ant-table`
- `step.selector` 是裸标签：`label`、`span`、`div`、`i`
- `step.target_box` 很小，宽高接近 checkbox，例如 10~30px
- 后面紧跟 `批量删除 / 批量下架 / 批量审核 / 批量拒绝审核 / 批量通过` 等按钮

## 生成规则

### 规则 A：表格 checkbox 禁止裸 selector

错误：

```json
{"type":"click","selector":"label","xpath":"/html/body/.../table/thead/tr/th/div/label"}
```

正确：

```json
{
  "type": "click",
  "selector": "xpath=/html/body/.../table/thead/tr/th/div/label",
  "xpath": "/html/body/.../table/thead/tr/th/div/label",
  "wait_after": 300
}
```

说明：

- `selector` 直接写成 `xpath=<原 xpath>`，让 runner 第一优先级就走精确路径
- 同时保留 `xpath` 字段，给旧兜底逻辑使用
- 不要输出 `label`、`span`、`div` 这种裸 selector

### 规则 B：表头全选优先保留精确 xpath

表头全选通常在：

```text
.../table/thead/tr/th/.../label
```

这种没有稳定文字，不能用 `:has-text()`。直接用录制 xpath 最稳。

推荐：

```json
{
  "type": "click",
  "selector": "xpath=<step.xpath>",
  "xpath": "<step.xpath>",
  "wait_after": 300
}
```

### 规则 C：行 checkbox 同样不能用裸 label

如果 xpath 在 `tbody/tr/td` 内，也用同样模板：

```json
{
  "type": "click",
  "selector": "xpath=<step.xpath>",
  "xpath": "<step.xpath>",
  "wait_after": 300
}
```

### 规则 D：相邻完全重复的表格 checkbox click，只保留 1 次

这是 EXP-020 的唯一小例外：**只针对表格 checkbox 的相邻重复点击**。

如果连续两步满足：

- 都是表格 checkbox click
- `xpath` 完全相同
- `target_box.cx/cy` 基本相同
- 中间没有其他业务步骤

则认为是录制器/浏览器冒泡导致的重复点击，只输出 1 条。否则会“勾选一次又取消一次”，批量操作就没有选中行。

错误：

```json
[
  {"type":"click","selector":"xpath=/html/body/.../table/thead/tr/th/div/label","xpath":"/html/body/.../table/thead/tr/th/div/label"},
  {"type":"click","selector":"xpath=/html/body/.../table/thead/tr/th/div/label","xpath":"/html/body/.../table/thead/tr/th/div/label"}
]
```

正确：

```json
[
  {"type":"click","selector":"xpath=/html/body/.../table/thead/tr/th/div/label","xpath":"/html/body/.../table/thead/tr/th/div/label","wait_after":300}
]
```

注意：这个去重只适用于“相邻、完全相同、表格 checkbox”。普通 click 仍遵守 EXP-020，不合并。

### 规则 E：搜索后马上勾选表格，要给搜索按钮等待

如果 `button:has-text("搜 索")` 后面紧跟表格 checkbox / 批量按钮，说明搜索会刷新表格。

搜索按钮必须补等待：

```json
{
  "type": "click",
  "selector": "button:has-text(\"搜 索\")",
  "xpath": "<原 xpath>",
  "wait_after": 1500
}
```

大表格或接口慢时可用 `wait_after: 2000`。

## 完整示例

录制：

```json
[
  {"action_type":"click","selector":"button:has-text(\"搜 索\")","xpath":"/html/body/.../button"},
  {"action_type":"click","selector":"label","xpath":"/html/body/.../table/thead/tr/th/div/label"},
  {"action_type":"click","selector":"label","xpath":"/html/body/.../table/thead/tr/th/div/label"},
  {"action_type":"click","selector":"button:has-text(\"批量下架\")","xpath":"/html/body/.../button[4]"}
]
```

生成：

```json
[
  {"type":"click","selector":"button:has-text(\"搜 索\")","xpath":"/html/body/.../button","wait_after":1500},
  {"type":"click","selector":"xpath=/html/body/.../table/thead/tr/th/div/label","xpath":"/html/body/.../table/thead/tr/th/div/label","wait_after":300},
  {"type":"click","selector":"button:has-text(\"批量下架\")","xpath":"/html/body/.../button[4]","wait_after":800}
]
```
