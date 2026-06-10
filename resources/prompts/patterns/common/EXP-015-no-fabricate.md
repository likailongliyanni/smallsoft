### EXP-015 禁止凭空创造 selector
- 不要发明 step 数据里没有的 selector
- 不要把 step.text 当 selector（text 是元素显示内容，不是定位器）
- 不要把 step.label 当 selector（label 是字段名）
- 只能用 step 已有的 scoped_selector / selector / xpath
