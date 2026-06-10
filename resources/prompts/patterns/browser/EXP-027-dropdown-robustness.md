### EXP-027 下拉菜单 - 默认 2 步,大列表才 3 步(v3 实测版)

**核心理念**：
- 普通下拉（运费模板/商品类型/是否上架 等）→ 2 步：click + select_option
- 大列表下拉（品牌/类目/地区 等）→ 3 步：click + fill + select_option

**⚠️ 重要修正(v3)**：旧版（v2）说"默认 3 步,fill 在 readonly 上是 no-op"——**这个假设是错的!**
实测 Playwright 的 `fill()` 在 readonly input 上会 **timeout 30 秒**，不是 no-op。
所以盲目对所有下拉 fill 会让普通枚举字段每个卡 30s。

**新铁律**：**宁可漏补 fill,也不要乱补 fill**。
- 漏补：大列表找不到选项,用户看错误日志改下个 → 不严重
- 乱补：每个普通枚举字段卡 30s,39 步流程要 20 分钟 → 严重

---

## ⚠️ 适用范围

**适用**：单级 select / el-select / avue-select / ant-select / n-base-selection 等普通下拉

**不适用**：
- ❌ **cascader 多级联动**（EXP-017 / EXP-022）—— 中间不要插 fill,会让面板关闭
- ❌ **隐藏选项的展开 click**（EXP-019）—— 那是单纯的 click,不是下拉触发

---

## 🎯 判断标准：什么时候用 3 步（补 fill）

**条件 A**：字段名是**大列表关键词**之一 → 3 步
| 大列表关键词 | 示例 |
|---|---|
| 品牌 / brand | 「品牌」「制造商」「产地品牌」 |
| 类目 / 分类 / category | 「商品类目」「商品分类」「子分类」 |
| 地区 / 省 / 市 / 区 / region | 「地区」「省份」「城市」「行政区」 |
| 供应商 / 经销商 / 商家 | 「供应商」「物流商」 |
| 材质 / 款式 / 颜色 / 规格 / 系列 | 「材质」「款式」「颜色」「型号系列」 |
| SKU / SPU / 商品 ID | 「关联 SKU」「父商品」 |
| 含"搜索"/"过滤"字样 | 「搜索品牌」「过滤分类」 |

**条件 B**：用户录制时**已经主动录了 fill 步骤** → 3 步
- 录制数据里 click 和 select_option 之间有 input/fill 步骤,说明用户当时输入了关键字搜索
- 这种保留用户原意

**其他全部情况** → **2 步**（不补 fill）

---

## 🚫 必须用 2 步的典型字段

| 字段名 | 为什么是 2 步 |
|---|---|
| **运费模板** | 通常固定枚举（含运/不含运）,readonly 模式 |
| **商品类型** | 固定枚举（普通商品/服务商品） |
| **是否上架 / 是否启用** | 是/否 二选一 |
| **状态** | 启用/禁用/草稿 等少量枚举 |
| **税率** | 0%/6%/9%/13% 等固定值 |
| **单位** | 个/件/箱/kg 等少量枚举 |
| **币种** | CNY/USD/EUR |
| **性别** | 男/女 |
| **结算方式** | 固定支付方式 |

判断辅助：**step.text 是不是 ≤ 6 字的短词 + 看起来是状态/类别枚举** → 2 步。

---

## 模板 1：2 步（默认）

```json
// 1) 打开下拉
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"<字段名>\") .el-input__inner",
  "xpath": "<原 click 的 xpath>",
  "wait_after": 1500
},
// 2) 直接点选项
{
  "type": "select_option",
  "from_excel": "<Excel 列>",
  "match_by_text": true,
  "selector": "li:has-text(\"<step.text>\")",
  "xpath": "<原 select_option 的 xpath>",
  "wait_after": 400
}
```

---

## 模板 2：3 步（大列表）

只有字段名匹配大列表关键词、或录制本身就有 fill 时,才用这个模板：

```json
// 1) 打开下拉
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"<字段名>\") .el-input__inner",
  "xpath": "<原 click 的 xpath>",
  "wait_after": 1500
},
// 2) 输入关键字搜索（只对可搜索下拉用!)
{
  "type": "fill",
  "selector": ".el-form-item:has-text(\"<字段名>\") .el-input__inner",
  "xpath": "<原 fill 的 xpath,如有>",
  "from_excel": "<同 Excel 列>",
  "wait_after": 600
},
// 3) 点选过滤后的选项
{
  "type": "select_option",
  "from_excel": "<Excel 列>",
  "match_by_text": true,
  "selector": "li:has-text(\"<step.text>\")",
  "xpath": "<原 select_option 的 xpath>",
  "wait_after": 400
}
```

---

## click 触发器的 selector

| 框架特征（看录制 selector） | click 的 selector 用 |
|---|---|
| `.el-select` / `.avue-select` / `.el-input` | `.el-form-item:has-text("X") .el-input__inner` |
| `.ant-select` | `.ant-select-selector` |
| `.n-base-selection` | `.n-base-selection` |
| `[role="combobox"]` | `[role="combobox"]` |

---

## 完整示例（daoyeshan 录制）

| 字段 | 模板 | 原因 |
|---|---|---|
| 运费模板 = 集采不含运 | **2 步** | 字段名不是大列表关键词,text 是短枚举词 |
| 商品类型 = 普通商品 | **2 步** | 字段名"类型"是状态类,text 是固定选项 |
| 商品类目 (cascader) | 见 EXP-017/022 | cascader 不补 fill |
| 品牌 = 晨光 | **3 步** | 字段名"品牌"是大列表关键词 |
| 是否上架 | 见 EXP-029 | radio 直接点 label |

---

## 铁律

- ✅ **默认 2 步**（click + select_option）
- ✅ 字段名是大列表关键词（品牌/类目/地区等）→ 3 步
- ✅ 用户录制本身有 fill → 保留 3 步
- ✅ click 触发器用 `.el-input__inner`（不是 `.el-select`）
- ✅ click 的 wait_after = 1500ms
- ✅ select_option 的 selector 用 `li:has-text(...)`
- ❌ **不要对所有下拉都生成 3 步** —— 普通枚举 readonly input 会卡 30s
- ❌ 不要把规则套到 cascader（EXP-017/022）和隐藏元素 click（EXP-019）

---

## 给用户的诊断提示（仍然失败时）

模板套对了但还失败,检查 2 件事：
1. **Excel 单元格的值跟页面选项文本完全一致吗?**（空格、全/半角、繁简）
2. **大列表字段是不是漏判了?** 比如某些"分类码"也是大列表,但字段名没含"分类"——这种情况用户在整理页手动加 fill 步骤

---

## 历史教训

v1（最早）：根据字段名启发式判断,2 步 vs 3 步——OK 但 AI 容易判断错
v2（错误）：默认 3 步,以为 fill 是 no-op——实测发现 30s timeout,弃用
v3（当前）：默认 2 步 + 明确的大列表关键词清单——保守但稳

**经验**：Playwright 的 `fill()` 在 readonly input 上**不是 no-op**,而是 timeout!
不要假设"补错不会出问题",要假设"补错就会卡 30s 单步"。
