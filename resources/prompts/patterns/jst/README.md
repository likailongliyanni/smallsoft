# 聚水潭专属经验包

这里的经验文件**仅在 `category=jst` 时被服务器加载**，用于针对聚水潭 ERP（erp321.com/epaas）的特化优化。

## 加载顺序

服务器构建 system prompt 时按下面顺序加载：

1. `prompts/json_dsl_system.md` — 通用 DSL 框架
2. `prompts/patterns/common/*.md` — 所有场景通用经验
3. `prompts/patterns/browser/*.md` — 浏览器通用经验（jst 模式叠加这层）
4. `prompts/patterns/jst/*.md` — 聚水潭专属经验（**本目录**，优先级最高）
5. 数据库 `ai_patterns` 表里 category 是 common / browser / jst 的经验

## 命名规范

`EXP-JST-NNN-短描述.md`，例如：
- `EXP-JST-001-platform-overview.md` — 平台概览
- `EXP-JST-002-search-table-pattern.md` — 搜索 + 表格模式
- `EXP-JST-010-product-create.md` — 商品上架专项
- `EXP-JST-020-order-process.md` — 订单处理专项

## 单向隔离

聚水潭经验**不会**被 `category=browser` 等其他模式加载，避免污染其他业务场景。

但聚水潭模式**可以**继承 browser/ 通用经验（聚水潭就是浏览器自动化的特化）。
