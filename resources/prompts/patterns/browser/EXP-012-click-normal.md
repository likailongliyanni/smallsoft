### EXP-012 普通 click：不需要 wait_after
普通的点击（按钮、链接、复选框）不需要等待，因为后续 fill/click 自带等待：

```json
{"type":"click","selector":"button:has-text(\"保存\")"}
```

只在以下场景需要 wait_after：
- 触发下拉/弹窗（800ms，见 EXP-011）
- 提交按钮可能跳转（1000ms）
- select_option 后（400ms，见 EXP-013）
