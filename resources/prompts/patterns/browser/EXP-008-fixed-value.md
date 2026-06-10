### EXP-008 excel_column 为空 → 用固定 value
当 step.excel_column 字段为空，但 step.value 非空时：

```json
{"type":"fill","selector":"...","value":"<step.value 的值>"}
```

如果 value 也为空：`"value": ""`
