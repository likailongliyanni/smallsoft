### EXP-011 触发器 click 必须保留为独立步骤

**铁律**：当 step.action_label 是「打开下拉」或 step.is_trigger=true 时：
- ✅ 生成一个独立的 click action
- ✅ **绝不允许**把它跟下一步的 select_option / click 合并

为什么？因为下拉菜单 99% 是**关着**的状态，必须先 click 触发器把它打开，**才能**看到选项。如果省略这一步，运行时直接找选项 → 找不到 → 整个脚本崩。

---

**触发器 click 的 selector 和 wait_after 由 EXP-027 统一规定**：
- selector：用 `.el-form-item:has-text("LABEL") .el-input__inner`
- wait_after：1500（不是 800）

---

**判断方法**（按优先级）：
1. step.action_label 含「打开下拉」「展开」「触发」→ 这是触发器
2. step.is_trigger === true → 这是触发器
3. step.tag === 'div' 且 selector 含 el-select / el-cascader / avue-select / ant-select / ant-picker 等 → 这是触发器
4. 当前 step 后面紧跟着 select_option → 这是触发器

**例子**：

```json
// 用户录了两步：先打开下拉，再选选项
// ❌ 错误：合并成 1 步
{"type":"select_option", "selector":"li:has-text(\"普通商品\")"}

// ✅ 正确：保留 2 步（按 EXP-027 实际是 3 步）
{"type":"click", "selector":".el-form-item:has-text(\"商品类型\") .el-input__inner",
 "xpath":"...", "wait_after":1500},
{"type":"fill", "selector":".el-form-item:has-text(\"商品类型\") .el-input__inner",
 "xpath":"", "from_excel":"菜单项_2", "wait_after":600},
{"type":"select_option", "from_excel":"菜单项_2", "match_by_text":true,
 "selector":"li:has-text(\"普通商品\")", "xpath":"...", "wait_after":400}
```
