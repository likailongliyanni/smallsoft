### EXP-004 selector 选择优先级：scoped_selector 最高
当 step.scoped_selector 非空时，**直接用它**。

scoped_selector 形如：`.el-form-item:has-text("销售价") input`
- 范围限定 + 标签文本匹配
- 几乎不会错位
- 是当前所有方式中最稳健的
