### EXP-023 每个 click/fill/select_option/check 都必须输出 xpath

**问题背景**：文字链接（如"调整价格""编辑""删除"）录制时有 xpath 但没有稳定的 CSS selector，生成脚本时如果不输出 xpath，runner 找不到元素直接报错。

**铁律**：只要 step.xpath 非空，生成的 action **必须带上 `"xpath"` 字段**，无一例外。

**优先级（selector 怎么选）仍然不变**：
1. scoped_selector 非空 → selector 用它（最稳定）
2. scoped_selector 空，selector 可用 → selector 用它
3. 都不可用 → selector 直接写 `"xpath=<step.xpath>"`

**但不管 selector 选了哪种，xpath 字段都要输出**：

```json
// 情况 A：有稳定的 scoped_selector
{
  "type": "click",
  "selector": ".el-form-item:has-text(\"销售价\") input",
  "xpath": "/html/body/div[1]/div/form/div[3]/div/input"
}

// 情况 B：有可用的 selector
{
  "type": "click",
  "selector": "a:has-text(\"调整价格\")",
  "xpath": "/html/body/div[2]/div/table/tr[1]/td[5]/a[2]"
}

// 情况 C：scoped_selector 和 selector 都不可用（空或太宽泛）
// → selector 直接用 xpath= 前缀形式，xpath 字段也保留
{
  "type": "click",
  "selector": "xpath=/html/body/div[2]/div/table/tr[1]/td[5]/a[2]",
  "xpath": "/html/body/div[2]/div/table/tr[1]/td[5]/a[2]"
}
```

**"不可用"的判断标准**（任一命中就不能用）：
- 值为空字符串 `""`
- 值为 `null` 或字段不存在
- 值是纯标签名：`div`、`span`、`a`、`input`、`button`（无附加属性/文本）
- 值含 `text=""` 空文本
- 值含随机 id（如 `#el-id-3584-0`）

**为什么 xpath 必须保留**：
- runner 执行时会先尝试 selector，如果失败则用 xpath 兜底
- 每次鼠标点击都一定有目标元素，xpath 是该元素的绝对路径，录制时必然存在
- 即使用户不小心点了空白处，xpath 也能精确记录当时点击的 DOM 节点
- 丢弃 xpath = 丢弃唯一可靠的兜底定位信息 = 执行必崩

**特别注意 — 纯文字链接场景**：
页面上的 `<a>调整价格</a>`、`<span class="link">编辑</span>` 这类元素：
- 往往没有 scoped_selector（不在 form-item 里）
- selector 可能只是 `a` 或 `span`（太宽泛，不可用）
- **xpath 是唯一可靠定位方式，必须输出**
