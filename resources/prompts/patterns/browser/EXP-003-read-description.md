### EXP-003 优先读 step.description 理解意图
每个 step 都有用户手写的 description（如"在「商品名称」输入内容"、"点击「保存」按钮"）。

这是用户对该步意图的直接描述，**优先级最高**：
- description 含"输入"/"填写" → 用 fill
- description 含"点击"/"单击" → 用 click
- description 含"选择"/"选项"/"下拉" → 用 select_option
- description 含"勾选"/"复选" → 用 check
- description 含"上传"/"文件" → 用 upload

如果 step.action_type 和 description 矛盾，优先按 description 判断。
