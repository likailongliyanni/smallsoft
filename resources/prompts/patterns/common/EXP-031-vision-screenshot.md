### EXP-031 辅助截图规则：点击前截图 + 黄色圆点

新版录制器支持选择性截图：用户把鼠标悬停在准备点击的位置，按 `Ctrl+Shift+X` 截图，然后再点击同一目标。截图会随对应 step 一起发送。

## 字段含义

- `screenshot_url`：该 step 的辅助截图地址。
- `screenshot_label`：截图标签，通常包含 step 编号。
- `screenshot_focus`：黄色圆点/焦点位置。
- `screenshot_match=manual_before_click`：截图发生在点击前，黄色圆点表示用户准备点击的位置。
- `screenshot_kind=privacy_focus_viewport`：隐私焦点截图，圆点附近清晰，外围被模糊/马赛克处理。

## 使用原则

1. steps.json 是主线，截图是证据。
   - 不要因为截图里看到其他按钮就新增步骤。
   - 不要因为截图里看不清某处就删除 step。
   - 不要改变 step 顺序。

2. 黄色圆点优先解释当前 step 的目标。
   - 如果 DOM 里 selector/xpath 不稳定，而截图圆点明显落在按钮、输入框、下拉触发器、菜单项上，可结合 step.label / step.text 选择更稳 selector。
   - 圆点落在下拉菜单项上时，该 step 更可能是 `select_option`。
   - 圆点落在输入框/文本域上时，该 step 更可能是 `fill` 或激活输入框的 `click`。
   - 圆点落在按钮/链接上时，该 step 更可能是 `click`。

3. 模糊区域不要强推断。
   - 外围模糊/马赛克是隐私保护，不代表页面不存在。
   - 只用清晰区域和黄色圆点附近的信息做判断。
   - 看不清的文本以 step.text / step.label / step.description 为准。

4. 截图不能替代 xpath。
   - 只要 step.xpath 非空，action 必须带 `"xpath"` 字段。
   - 截图只帮助判断 action 类型和 selector 稳定化，不输出到最终 JSON。

## 多图处理

一个流程可能有几十步，但只有少数步骤带截图。没有截图的步骤按 DOM/selector/xpath 规则正常生成；有截图的步骤结合视觉证据增强判断。

如果服务端提供了单独的 `vision_observations`（图片 AI 对截图的结构化分析），优先把它当作当前 step 的补充说明，但仍不得覆盖 steps.json 的顺序和用户明确的 excel_column。
