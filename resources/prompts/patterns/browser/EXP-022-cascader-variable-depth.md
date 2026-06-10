### EXP-022 多级菜单：录制 1 条路径 + Excel 每行可走不同路径

这是 EXP-017（多级 cascader）的进阶版。用户的实际使用场景：

- 录制时：只点了一条路径（如「办公电器 / 厨房大家电 / 商用电器」）
- 运行时：Excel 每一行可能是**完全不同的路径**，**层级深浅也可能不同**

| Excel 行 | 菜单项_3 | 菜单项_4 | 菜单项_5 |
|---|---|---|---|
| 1 | 办公电器 | 厨房大家电 | 商用电器 |
| 2 | 食品饮料 | 零食 | 薯片 |
| 3 | 服装 | 男装 | （留空）|
| 4 | 家电 | （留空）| （留空）|

---

**⚠️ EXP-027 的补 fill 规则不适用 cascader**（同 EXP-017）：

cascader 多级之间**绝对不要**插 fill 步骤，会让下拉关闭。

但 cascader **触发器 click** 仍按 EXP-027 改写：用 `.el-input__inner`、`wait_after=1500`。

---

**生成 DSL 的铁律**：

1. **每一级都生成独立 select_option**（即使录制时只录了一级）
   - 每个都有 `from_excel + match_by_text + selector + xpath`
   - selector 用 `li:has-text("<录制时文本>")`（运行时会被 Excel 数据覆盖）

2. **不要试图根据录制路径"推断"层级数**
   - 录制时点了 3 级，就生成 3 个 select_option
   - 运行时 Excel 某列为空 → runner 会自动跳过那一步（已实现）

3. **wait_after 给足时间**
   - 默认 400ms，cascader 给 500-600ms（不同分类子节点加载速度不同）

例（用户录了「触发器 → 一级 → 二级 → 三级」）：

```json
[
  // 1. 触发器：按 EXP-027 改写 selector
  {"type":"click", "selector":".el-form-item:has-text(\"商品类目\") .el-input__inner",
   "xpath":"...", "wait_after":1500},

  // 2. 一级（selector 用 li:has-text）
  {"type":"select_option",
   "from_excel":"菜单项_3", "match_by_text":true,
   "selector":"li:has-text(\"办公电器\")", "xpath":"...",
   "wait_after":500},

  // 3. 二级（Excel 空时 runner 跳过）
  {"type":"select_option",
   "from_excel":"菜单项_4", "match_by_text":true,
   "selector":"li:has-text(\"厨房大家电\")", "xpath":"...",
   "wait_after":500},

  // 4. 三级（同上）
  {"type":"select_option",
   "from_excel":"菜单项_5", "match_by_text":true,
   "selector":"li:has-text(\"商用电器\")", "xpath":"...",
   "wait_after":500}
]
```

**运行时行为**（runner 已实现）：
- Excel 给值 → 用 `text="VALUE"` 在 `.el-cascader-menu / .ant-cascader-menu` 等可见菜单容器内找选项
- Excel 为空 → 跳过这一步（不报错，继续下一步）
- 多个同名文字 → 优先取当前打开的菜单里的（容器范围 + :visible 过滤）

**禁止**：
- ❌ 把多级合并成一个 select_option
- ❌ 给中间某级加 condition 让它"按需执行"——直接生成所有级就行，runner 自动处理空值
- ❌ 用录制时的 `#cascader-menu-3584-0-0` 这种带随机 id 当 selector（必须用 `li:has-text("...")`）
- ❌ **在 cascader 多级之间插 fill 步骤**（EXP-027 的补 fill 规则不适用 cascader）
