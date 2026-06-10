### EXP-032 人工介入是运行期能力，不写进 DSL

新版客户端支持运行期人工介入：第一轮执行时，用户可以在某些步骤完成后选择“从这里人工介入”。一个完整循环允许设置多个介入点；后续循环会在相同步骤后自动暂停，等用户手工处理完再继续。

这件事由客户端 runner 负责，不属于 AI 生成 DSL 的职责。

## 禁止输出

最终 JSON 的 actions 里不要输出以下类型或同义动作：
- `manual`
- `manual_verify`
- `human_intervention`
- `pause`
- `wait_user`
- `confirm_by_user`

不要把验证码、短信、滑块、复杂风控、人工审批等场景写成一个自定义 manual action。当前 runner 不需要这种 DSL。

## 正确处理方式

- 如果用户已经录制了某些步骤，就按步骤正常生成 actions。
- 如果某几步未来需要人工接入，用户会在第一次运行时自己选择暂停点。
- 如果某一步明显无法稳定自动化，也不要编造 manual action；仍按当前 step 的 selector/xpath 输出最接近的可执行动作。

## 例子

错误：
```json
{"type":"manual_verify","description":"用户手动完成验证码"}
```

正确：
```json
{"type":"click","selector":"button:has-text(\"发送验证码\")","xpath":"...","wait_after":1000}
```

是否在这一步之后停下来人工处理，由客户端运行时弹层决定。
