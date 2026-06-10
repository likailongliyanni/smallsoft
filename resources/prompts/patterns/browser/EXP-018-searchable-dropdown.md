### EXP-018 可搜索下拉框（已被 EXP-027 覆盖）

**重要**：本经验包的逻辑已经被 **EXP-027** 完全覆盖。EXP-027 让 AI 对**所有** select_option 都默认按可搜索 3 步处理（click + fill + select_option），不需要根据录制识别是否可搜索。

---

**保留本经验包仅用于历史参考**。如果原录制本身就是 3 步（用户主动录了搜索过程），按 EXP-027 的模板原样输出即可：

```json
// 第 1 步：点开下拉（EXP-027）
{"type":"click", "selector":".el-form-item:has-text(\"品牌\") .el-input__inner",
 "xpath":"...", "wait_after":1500},

// 第 2 步：输入关键字过滤（EXP-027）
{"type":"fill", "selector":".el-form-item:has-text(\"品牌\") .el-input__inner",
 "xpath":"", "from_excel":"品牌", "wait_after":600},

// 第 3 步：选过滤后的结果（EXP-009）
{"type":"select_option", "from_excel":"品牌", "match_by_text":true,
 "selector":"li:has-text(\"晨光\")", "xpath":"...", "wait_after":400}
```

**铁律**：
- ✅ fill 和 select_option **同时绑同一个 Excel 列**（输什么搜什么）
- ✅ fill 用跟 click 同一个 selector（`.el-input__inner`）
- ❌ 不要把 fill 跟 click 合并
- ❌ 不要因为录制只有 2 步就只输出 2 步（按 EXP-027 主动补 fill）
