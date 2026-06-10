### EXP-007 excel_column 非空 → 必用 from_excel
当 step.excel_column 字段非空时（如 "商品名称"、"价格"），意味着用户希望批量执行不同数据。

**必须**输出 `"from_excel": "<excel_column 的值>"`，绝不能写死 value。

例：
- step: `{"action_type":"input","excel_column":"商品名称","value":"测试"}`
- ✅ 生成：`{"type":"fill","selector":"...","from_excel":"商品名称"}`
- ❌ 错误：`{"type":"fill","selector":"...","value":"测试"}`（写死了，Excel 数据不生效）
