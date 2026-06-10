### EXP-999 浏览器自动化最终收口

本条是 browser 分类最后规则。若前面 browser 经验有冲突，以本条为准。

1. 新版截图只做辅助证据。
   - `screenshot_url` / 黄色圆点 / `manual_before_click` 只解释当前 step 的点击目标。
   - 不因截图新增、删除、重排步骤。
   - 模糊/马赛克区域不要推断业务内容。

2. 普通步骤不合并。
   - 普通 click / fill / select_option / check 按 step 顺序保留。
   - 只有素材库、多图上传、富文本图片上传这些 runner 已支持的专用场景，才允许生成 `upload_folder_to_library`。

3. 下拉默认保守。
   - 普通枚举下拉默认 2 步：click + select_option。
   - 只有大列表字段或用户录制了搜索输入，才 3 步：click + fill + select_option。
   - 不要对 readonly 下拉盲目 fill。

4. Excel 只听用户绑定。
   - `excel_column` 非空才用 `from_excel`。
   - 普通按钮、新增、保存、完成、下一步等 click 不创造 Excel 列。
   - 截图不能让你新增 Excel 表头。

5. 人工介入不进 DSL。
   - 不输出 `manual` / `manual_verify` / `pause` / `human_intervention`。
   - 人工介入点由客户端第一轮运行时让用户选择，可有多个。

6. selector 要可执行。
   - 有 `xpath` 必须保留。
   - 最终 `action.selector` 本身必须是精确定位；不要把精确定位只放在 `scoped_selector`。
   - `fill` 禁止使用 `input[type="text"]`、`input`、`.el-input__inner` 这类全局宽泛 selector；有字段名时必须改成 `.el-form-item:visible:has-text("<字段名>") .el-input__inner`。
   - SKU / 统一规格 / 价格库存嵌套区域（统一规格名称、商品编码、销售价、市场价、成本价、库存等）禁止用 `.el-form-item:has-text(...) .el-input__inner`；优先 `selector: "xpath=<step.xpath>"`，避免填到上方 `skuId/skuld`（EXP-035）。
   - 这些 SKU/价格字段如果必须合成 selector，用 EXP-035 的“直接子 label XPath”，不能用父级 `skuId` 或模糊 `:has-text`。
   - 表格复选框 / 表头全选禁止输出裸 `label`、`span`、`div`、`i`；如果 `step.xpath` 在 table/thead/tbody 里，`selector` 必须写成 `xpath=<step.xpath>`（EXP-034）。
   - 相邻完全重复的表格 checkbox click，只输出 1 次；否则会勾选后又取消（EXP-034）。
   - 搜索按钮后马上勾选表格或批量操作时，搜索 click 要补 `wait_after: 1500`，等待表格刷新（EXP-034）。
   - 选项优先 `li:visible:has-text(...)` 或 `li:has-text(...)`。
   - Vue/Element UI 表单优先加 `:visible`，避免 0x0 隐藏占位。

7. 长页面滚动要显式写入 DSL。
   - 录制器可能漏掉鼠标滚轮；进入详情、描述、库存、价格、重量、体积、底部保存按钮等下方区域前，必须插入 `{"type":"scroll","to":"bottom"}` + `{"type":"delay","ms":300}`（EXP-036）。
   - 如果点击「编辑」后是在弹窗/抽屉里操作，`scroll bottom` 不够；进入下方字段前用 `{"type":"press","key":"PageDown"}` + delay（EXP-037）。
   - 弹窗/抽屉内的 `/html/body/div[5]`、`/html/body/div[6]` 绝对 xpath 不稳定，不能作为主 selector；SKU/价格字段用 EXP-035 直接子 label XPath（EXP-037）。
   - 点击 `保 存`、`提交`、`完成` 这类底部按钮前，如果前面有长表单内容，先 scroll bottom（EXP-036）。
   - 弹窗/抽屉底部的 `提交` 按钮前，优先再 `press PageDown`（EXP-037）。
   - 下拉菜单 / cascader 多级选择中间不要插 scroll，避免面板关闭（EXP-036）。

最终只输出 JSON，不输出解释。第一个非空白字符必须是 `{`，禁止在 `{` 前输出 `json`、```json、``` 或任何前言。
