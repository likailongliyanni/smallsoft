### EXP-999 最后强调（统一总则）

## 通用输出规则
- ✅ 只输出 JSON
- ✅ 从 `{` 开始，到 `}` 结束
- ✅ 按 step 顺序逐条转换（EXP-014）
- ❌ 不要 Python、不要 Markdown
- ❌ 不要解释文字
- ❌ 不要凭空创造 selector（EXP-015）

## selector 选择规则
- ✅ scoped_selector 非空 → 优先用它（EXP-004）
- ✅ step.xpath 非空 → action 必须带 "xpath" 字段（EXP-023）
- ✅ 多个 step 的 scoped_selector 完全相同（如都是 `:has-text("skuId")`）→ 用 step.text 重写 selector（EXP-026）
- ✅ **radio 类 click 直接用 `label.el-radio:has-text("选项")` 全局找**，不要套 form-item（EXP-029）
- ✅ **fill / select 用 `:has-text(LABEL)` 时加 `:visible` 过滤**，防 0×0 隐藏占位（EXP-029）
- ✅ **SKU / 统一规格 / 价格库存字段**（统一规格名称、商品编码、销售价、市场价、成本价、库存等）优先 `selector:"xpath=<step.xpath>"`，不要用 `.el-form-item:has-text(...) .el-input__inner`，防止填到 `skuId/skuld`（EXP-035）
- ✅ **表格 checkbox / 表头全选**：如果录制 selector 是裸 `label` 且 xpath 在 table/thead/tbody 内，selector 必须改成 `xpath=<step.xpath>`（EXP-034）
- ❌ 触发器 click **不要**用 `text="<当前值>"` 或带随机 id（EXP-021）
- ❌ 不要用父级 `skuId/skuld/规格` 容器定位后续的商品编码、价格、库存字段（EXP-035）
- ❌ 表格 checkbox 绝对不要输出裸 `label`、`span`、`div`、`i`，会点到页面第一个表单 label（EXP-034）
- ❌ 不要省略 xpath 字段（即使 selector 已经很稳定）
- ❌ 不要假设 `.first` 安全 —— Vue 框架下 `.first` 经常取到 0×0 隐藏占位（EXP-029）

## Excel 数据绑定
- ✅ excel_column 非空 → 用 from_excel（EXP-007）
- ✅ select_option + from_excel 时 → 加 match_by_text=true（EXP-009）
- ✅ excel_column 空但 value 非空 → 用固定 value（EXP-008）

## 下拉菜单（EXP-027 v3 实测版 - 默认 2 步,大列表才 3 步）
- ✅ **默认 2 步**:click（`.el-input__inner`,wait=1500）+ select_option（`li:has-text`,wait=400）
- ✅ **3 步**(多补 fill) 的条件:字段名含"品牌/类目/分类/地区/省/市/供应商/材质/款式"等大列表关键词,或录制本身有 fill 步骤
- ✅ 普通枚举字段(运费模板/商品类型/是否XX/状态/税率/单位)**严格 2 步**,**不要补 fill**
- ✅ select_option 的 selector 用 `li:has-text("...")` (不是 `text="..."`)
- ❌ **不要默认 3 步** —— Playwright 的 fill 在 readonly input 上会 timeout 30s,不是 no-op(实测教训)
- ❌ **cascader 多级**不要套 EXP-027 的 fill 步骤(EXP-017 / EXP-022)
- ❌ **「展开/折叠」click** 不是下拉触发,单独写一步即可(EXP-019)

## 多级 cascader（EXP-017 / EXP-022）
- ✅ N 级菜单 = 1 个触发 click + N 个 select_option（共 N+1 步）
- ✅ 触发 click 仍按 EXP-027：`.el-input__inner` + wait=1500
- ✅ 每级 select_option：`li:has-text("...")` + wait=500
- ❌ 多级之间**不要插 fill**
- ❌ 不要合并、不要省略中间级

## click 步骤（EXP-020 是主规则）
- ✅ 用户每点一次 → 生成一个 action，不要合并不要去重
- ✅ 唯一例外：相邻完全重复的表格 checkbox click，只保留 1 次，避免勾选后又取消（EXP-034）
- ✅ 普通 click 不需要 wait_after（EXP-012）
- ✅ 触发下拉的 click → 走 EXP-027 流程
- ✅ 展开隐藏元素的 click → 保留 + wait_after=400（EXP-019）
- ✅ 搜索按钮后紧跟表格勾选/批量操作时，搜索 click 补 `wait_after:1500` 等待表格刷新（EXP-034）

## 长页面滚动（EXP-036）
- ✅ 进入详情、描述、详情图、库存、重量、体积、价格、底部保存按钮等下方区域前，插入 `{"type":"scroll","to":"bottom"}` + `{"type":"delay","ms":300}`
- ✅ 点击 `保 存` / `提交` / `完成` 前，如果页面是长表单，先 scroll bottom
- ✅ 点击「编辑」后如果是在弹窗/抽屉里操作，下方字段前优先 `{"type":"press","key":"PageDown"}` + delay，不要只用 scroll bottom（EXP-037）
- ✅ 弹窗/抽屉内 `/html/body/div[5]`、`/html/body/div[6]` 绝对 xpath 不稳定，主 selector 用 label XPath（EXP-035/037）
- ❌ 下拉菜单和 cascader 多级选择中间不要插 scroll，会导致菜单关闭

## 文件上传（runner 当前只支持单文件 upload）
- ✅ 单文件上传 → `upload` + from_excel（EXP-016）
- ✅ click 触发上传 + upload + click 确定 → 标准 3 步序列（EXP-016）
- ✅ 素材库弹窗 → 3 步合并：click 打开 + upload + click 确定（EXP-025）
- ✅ 多图（无素材库）→ N 个独立 upload + N 列 Excel（EXP-024）
- ✅ 上传后 wait_after ≥ 2000ms（让 el-loading-mask 消失,防后续 click 被拦截）
- ❌ 不要使用 `upload_dir` / `upload_folder_to_library`（runner 不认识）
- ⚠️ 真正的"目录扫描批量上传"需要更新 exe，见 HANDOFF-multi-image-upload.md

## input 激活模式（EXP-030）
- ✅ 录制里 fill 前有 click（同一个 label）→ **必须保留** click（不要去重）
- ✅ click 激活的 wait_after 给 200~300ms（让 input 切换到编辑态）
- ✅ click 的 selector 用 step.text 重写为 `.el-form-item:has-text("具体字段名")`（EXP-026）
- ❌ 不要假设"Playwright 的 fill 会自动 focus" —— 对 daoyeshan 等 disabled input 不行

## 防 0×0 隐藏占位陷阱（EXP-029）
- ✅ radio click → `label.el-radio:has-text("<选项>")` 全局找
- ✅ fill / select / cascader 触发 → selector 加 `:visible` 过滤（如 `.el-form-item:visible:has-text(...)`）
- ✅ 选项类（li/option）→ `li:visible:has-text("<文字>")`
- ❌ 不要用 `.el-form-item:has-text(LABEL).first` 直接锚定（Vue 框架下经常取到 0×0 占位）
