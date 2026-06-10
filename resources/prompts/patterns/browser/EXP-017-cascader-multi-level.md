### EXP-017 多级联动菜单（cascader）每一级都是独立步骤

多级联动（如「商品类目：办公电器 / 厨房大家电 / 商用电器」）**N 级菜单 = N+1 步**：

```
步骤 1：click 触发器（打开第一级）
步骤 2：select_option 第一级（"办公电器"）
步骤 3：select_option 第二级（"厨房大家电"）
步骤 4：select_option 第三级（"商用电器"）
... 以此类推
```

---

**⚠️ EXP-027 不适用于 cascader**：

cascader 的多级选项**不要**插入 fill 步骤（cascader 没有搜索框，fill 会把焦点带走导致下拉关闭）。cascader 就是「触发器 click + N 个 select_option」的纯链式结构。

但 cascader 的**触发器 click** 还是按 EXP-027 的规则改写 selector 和 wait_after：
- selector：`.el-form-item:has-text("LABEL") .el-input__inner`
- wait_after：1500

---

**铁律**：
- ✅ 每一级 select_option 都是独立的 action
- ✅ 每一级 select_option 之间 wait_after=400~500（让下一级动画出来）
- ✅ select_option 的 selector 用 `li:has-text("...")`（跟 EXP-009 一致）
- ❌ **绝不允许**把多级合并成 1 个 select_option
- ❌ **绝不允许**省略中间任何一级
- ❌ **绝不允许**在 cascader 多级之间插入 fill 步骤（EXP-027 的补 fill 规则不适用 cascader）

**Excel 列名规律**：用户录制时通常会按 `菜单项_1 / 菜单项_2 / 菜单项_3` 这样命名一级二级三级。

例子（用户录了 4 步：1 个触发器 + 3 个级别）：

```json
// 第 1 步：打开 cascader（按 EXP-027 改写 selector）
{"type":"click", "selector":".el-form-item:has-text(\"商品类目\") .el-input__inner", "xpath":"...", "wait_after":1500},

// 第 2 步：第一级（注意 selector 用 li:has-text）
{"type":"select_option", "from_excel":"菜单项_3", "match_by_text":true,
 "selector":"li:has-text(\"办公电器\")", "xpath":"...", "wait_after":500},

// 第 3 步：第二级
{"type":"select_option", "from_excel":"菜单项_4", "match_by_text":true,
 "selector":"li:has-text(\"厨房大家电\")", "xpath":"...", "wait_after":500},

// 第 4 步：第三级（最后一级，叶子节点）
{"type":"select_option", "from_excel":"菜单项_5", "match_by_text":true,
 "selector":"li:has-text(\"商用电器\")", "xpath":"...", "wait_after":500}
```

**判断方法**：步骤里有连续多个 select_option（中间没有其他操作），就是 cascader。每一级都保留，每级之间**不要插 fill**。
