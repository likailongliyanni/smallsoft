### EXP-JST-001 聚水潭 ERP 平台概览（优先级最高）

> 当 user 消息中 `category=jst` 时，目标网站固定是 **聚水潭 EPaaS 平台**（`https://www.erp321.com/epaas`）。
> 这是国内最大电商 ERP 之一，特化场景和通用浏览器自动化有关键差异，本规则**优先级高于 browser/EXP-XXX**。

## 平台基本信息

- 域名：`www.erp321.com`
- 入口：`/epaas`（统一 PaaS 入口）
- 框架：Vue + Element UI（早期还有 ExtJS 混用）
- 登录方式：账号密码（首次可能要扫码绑定）
- 多店铺：账号绑定多个店铺，操作前可能需要"切换店铺"
- 数据规模：单次批量 100-1000 行很常见，软件要稳

## 聚水潭特有的 DOM 模式

### 1. 菜单结构

聚水潭主界面是**左侧多级折叠菜单 + 右侧 Tab 标签页**：

```
[ 左侧菜单 ]   |  Tab1 ｜ Tab2 ｜ Tab3
              |  ─────────────────
   商品管理   |   <iframe 或 SPA 视图>
     ├ 商品列表 |
     ├ 商品分类 |
   订单管理   |
     ├ 待发货  |
   ...
```

- 同一时刻可能开多个 Tab，点击切换
- 每个 Tab 在父页面里都是独立的容器，不是新窗口
- 关闭 Tab 用 Tab 标题旁的 × 按钮

### 2. 列表页通用模式

- 顶部：搜索框（多字段） + 高级搜索折叠面板
- 中间：表格（el-table），支持多选、排序、勾选过滤
- 底部：分页器
- 行操作：每行最右侧的「操作」列，悬停或点击展开下拉菜单

### 3. 弹窗模式

- **编辑商品 / 订单**：从右侧滑出抽屉（drawer）或居中 modal
- **选择关联数据**（如选客户、选物流）：通常是 modal 里嵌入一个列表 + 搜索
- **批量操作确认**：小型确认弹窗

## 选择器策略（vs 通用浏览器）

### 不要用 xpath 绝对路径

聚水潭的 DOM 嵌套很深（左侧菜单 + Tab + 内容区），xpath 像 `/html/body/div[3]/div[2]/div/section/...` 几乎不可复用。

**优先用：**
1. `:has-text("具体功能名")` 锁定按钮（聚水潭的中文按钮名很稳定）
2. `.el-form-item:has-text("LABEL") input` 锁定表单字段
3. `.el-table__row` + `td:has-text("...")` 锁定表格行
4. `placeholder` 锁定搜索框

### 多 Tab 场景：用 `:visible` 过滤

聚水潭同时打开多个 Tab 时，DOM 里有多个 `el-form`、多个 `el-table`，必须用 `:visible` 锁定当前激活 Tab。

```json
{
  "type": "fill",
  "selector": ".el-form-item:visible:has-text(\"商品编码\") input",
  "from_excel": "商品编码"
}
```

## 频繁出现的操作模式

### 模式 A：搜索 → 选第一行 → 编辑

```
1. fill 搜索框
2. click [搜 索] 按钮
3. wait 1500ms（聚水潭后端经常慢）
4. click 第一行的「编辑」按钮 → 弹出抽屉
5. 在抽屉里 fill 字段
6. click [保 存]
7. wait 弹窗关闭（用 wait_for_selector hidden）
```

### 模式 B：批量勾选 → 批量操作

```
1. fill 顶部搜索条件
2. click 搜索
3. 勾选全选 checkbox（.el-table__header .el-checkbox）
4. 顶部出现的批量操作按钮 → click [批量审核] 等
5. 弹确认 → click [确 定]
```

### 模式 C：商品上架（最复杂）

```
1. click [商品列表]
2. click [新增商品]
3. 抽屉打开，填基础信息（名称、品牌、分类）
4. 上传主图（聚水潭素材库流程，见 EXP-JST-XXX）
5. 填规格、SKU、价格
6. click [保 存]
7. 列表自动刷新，新商品在第一行
```

## 反爬注意事项

- 客户端必须用 **stealth_cdp** 模式（真实 Edge + stealth.js）
- runner 不要快速连点 — 聚水潭后端有频控，每次 click 后建议 `wait_after >= 500`
- 切忌**循环 100 行无任何 wait** — 一定要 `delay` 散布
