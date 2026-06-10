### EXP-013 select_option 默认 wait_after=400
选完菜单项后，下拉面板收起需要时间。给 400ms 缓冲：

```json
{"type":"select_option","selector":"text=\"...\"","wait_after":400}
```
