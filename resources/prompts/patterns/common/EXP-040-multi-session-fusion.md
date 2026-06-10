### EXP-040 多次录制融合（multi-session fusion）—— 优先级最高

> 当 user 消息中存在 `sessions` 字段（数组，多个录制）时，必须进入"融合模式"。
> 这意味着用户在同一个任务上录制了 2-5 次，你的任务是从这些录制里**提炼最稳定的版本**。
>
> **不要把 sessions 当独立流程**。它们是同一个任务，操作顺序大致相同但可能有细微差异。

## 处理优先级

如果 user 消息中同时存在 `steps` 和 `sessions`：
- `sessions` 优先（包含 `steps` 在内，作为 session_1）
- 用 `sessions` 全部数据融合出一份 DSL

如果只有 `steps`（单次录制），按常规流程处理。

## 融合 4 大原则

### 原则 1：共同步骤 = 核心步骤

如果同一个动作出现在 **全部 N 次** 录制里（顺序也大致一致），它是核心步骤，**必须保留**。

判断 "同一个动作" 的依据：
- action_type 相同（都是 click / input / select_option ...）
- label / scoped_selector / xpath 任一字段在多次中匹配
- 大致在序列里的相对位置一致

### 原则 2：只出现 1-2 次的步骤 = 偶然操作

如果某动作只在 1-2 次（< 半数）录制里出现，**多半是用户偶然多点了一下**：
- 重复点击同一个 label.material-name
- 不小心点了页面空白区域
- 重复滚动

**默认删除这些步骤**。除非它们出现在所有 sessions 的同一阶段，那才保留。

### 原则 3：选择器多变 → 选最稳的

如果同一个步骤在 N 次录制里 selector 不同：

```
session_1: button:has-text("新 增")
session_2: button.el-button.add-btn
session_3: button:nth-child(2)
```

**优先级**（高到低）：
1. `:has-text("XXX")` ——文本几乎不会变
2. `scoped_selector`（含 form-item label 锚定）—— 极稳
3. `[data-*]` 属性
4. `#id`（要短且非自动生成）
5. 业务 class（如 `.add-btn`，但不是 `.el-button`）
6. `nth-child` / xpath —— **不到万不得已不用**

→ 用 `button:has-text("新 增")` 作为主 selector，把 xpath 放兜底。

### 原则 4：value 在各次不同 → 必然是 Excel 数据

如果同一个 input 步骤的 value 在 N 次里**全不一样**：

```
session_1: 商品名 = "测试商品 A"
session_2: 商品名 = "测试商品 B"  
session_3: 商品名 = "测试商品 C"
```

→ 这必然是要参数化的 Excel 列，**不要写 value**，必须用 `from_excel`。

建议列名根据 step.label 推断：
- label="商品名" → `"from_excel": "商品名"`
- label="销售价(元)" → `"from_excel": "销售价(元)"`
- label="" 但 value 像价格 → `"from_excel": "价格"`

如果 value 在 N 次里**完全相同**（如所有次都填了 "AA"）→ 这是固定值，写 `"value": "AA"` 即可，**不要**当 Excel 列。

### 补充原则 5：wait_after 取最大值

如果同一步在不同次里需要不同等待时间（比如 session_1 跑得快没问题，session_2 跑得慢失败了），取**所有次成功时的最大 wait_after**。宁可慢一点也不要不稳定。

## 偶然操作的去重模板

录制时经常出现"用户连点 2 次相同 button"，3 次录制里可能：
- session_1: click X, click X（连点 2 次）
- session_2: click X（点 1 次）
- session_3: click X, click X, click X（点 3 次）

**统一去重 → 只保留 1 次**（除非业务上确认要重复，比如"双击展开"）。

## 不要做的

- ❌ 把 N 次 sessions 当成 N 个独立流程，输出 N 个 DSL（错！应该 1 个融合 DSL）
- ❌ 简单取交集（会丢失关键步骤，比如某 session 上传图比其他多）
- ❌ 简单取并集（会包含一堆偶然操作）
- ❌ 因为 session 之间步数不同就报错（不同次步数 ±2 很正常）
- ❌ 把 session_2 里出现的"用户走神点错"也保留进 DSL

## 多次录制下的 description 字段

整理页生成的 description 来自 session_1。融合后保留 session_1 的 description，**除非**：
- 某步在其他 session 有更明确的 user_note（用户备注）→ 优先用那个
- 某 input 步骤的 value 在不同次完全不同 → description 改成「在「XX」输入内容（自动检测为 Excel 数据列）」

## 输出格式

返回 1 个 JSON DSL（跟单次录制一样的格式），无需任何额外标注是融合的。客户端只关心最终能跑的脚本。

如果你删除/合并了较多步骤（>5 个），可以在 DSL 顶部加个 `name` 后缀，例如：
```json
{
  "version": "1.0",
  "name": "<原流程名>（融合自 3 次录制）",
  "actions": [...]
}
```

## 验证清单

在输出前自检：
- [ ] sessions 中每次都出现的关键步骤是否都在 DSL 里？
- [ ] 偶然出现的重复 click 是否已合并？
- [ ] value 在各次不同的 input 是否都改成了 from_excel？
- [ ] selector 是否用了最稳的版本？
- [ ] 是否保留了开弹窗、确定按钮、上传等关键节点？
