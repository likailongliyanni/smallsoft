### EXP-019 隐藏选项（必须保留"展开"那一步）

页面上一些选项默认是**隐藏的**，用户需要先点某个按钮/链接才会显示。

例子：
- 「更多筛选条件」→ 点了之后才出现"按品牌""按价格"复选框
- 「高级设置」→ 点了之后才出现某些下拉/输入
- 折叠面板（el-collapse）→ 点了标题栏才展开

**铁律**：
- ✅ "展开/折叠"的那一步 click 必须保留为独立 action
- ✅ wait_after=300~500（让动画完成）
- ✅ 展开后如果是下拉操作，**展开 click 单独写一步，再走 EXP-027 的 3 步**（click 触发器 + fill + select_option）
- ❌ **绝不允许**省略这一步直接去操作隐藏元素

例：
```json
// 第 1 步：展开"更多筛选"
{"type":"click", "selector":"button:has-text(\"更多筛选\")", "wait_after":400},

// 第 2 步：勾选刚刚展示出来的选项
{"type":"check", "selector":".el-form-item:has-text(\"按品牌\") input"}
```

如果展开后里面有下拉，按 EXP-027 走 3 步：
```json
// 1. 展开
{"type":"click", "selector":"button:has-text(\"高级设置\")", "wait_after":400},

// 2. 打开下拉（EXP-027）
{"type":"click", "selector":".el-form-item:has-text(\"地区\") .el-input__inner",
 "xpath":"...", "wait_after":1500},

// 3. 输入关键字（EXP-027）
{"type":"fill", "selector":".el-form-item:has-text(\"地区\") .el-input__inner",
 "xpath":"", "from_excel":"地区", "wait_after":600},

// 4. 选择
{"type":"select_option", "from_excel":"地区", "match_by_text":true,
 "selector":"li:has-text(\"北京\")", "xpath":"...", "wait_after":400}
```

**判断方法**：
- step 是 click，且 selector 是 button/链接/带 "展开""更多""高级""筛选" 等文字
- 后面紧跟的 step 操作了之前不可能可见的元素
- 这种 click 必须保留
