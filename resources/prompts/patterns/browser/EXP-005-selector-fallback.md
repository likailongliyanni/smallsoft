### EXP-005 selector 次选：用 step.selector
当 scoped_selector 为空，用 step.selector。

但避免使用**太宽泛**的：
- ❌ 单独的 `div` / `span` / `input` / `button`
- ❌ `text=""` 空文本
- ✅ `button:has-text("登录")` 含文本
- ✅ `input[placeholder="..."]` 含属性
- ✅ `.business-class.other-class` 多个 class
