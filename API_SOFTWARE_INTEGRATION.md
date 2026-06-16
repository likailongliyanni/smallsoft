# 软件端 API 对接说明

接口根地址：

```text
https://tools.haobanfa.online/api
```

## 1. 健康检查

```http
GET /api/health
```

返回：

```json
{"ok": true, "version": "0.2.0-laravel"}
```

## 2. 获取交互类型

录制软件启动时调用，用来渲染“单击、双击、文本输入、文件上传、人工验证”等选项。

```http
GET /api/interaction-types
```

返回字段：

- `step_limits.normal`：普通模式最大步数，默认 20
- `step_limits.advanced`：高级模式最大步数，默认 30
- `interaction_types[].requires_field_name`：是否必须填写表格字段名

规则：

- 单击、双击：不需要字段名
- 文本输入：必须字段名
- 文件上传：必须字段名
- 人工验证：不绕过，只暂停等待人工处理

## 3. 用户注册

```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "test001",
  "password": "123456",
  "name": "测试用户"
}
```

返回 `token`，软件端保存后续请求使用：

```http
Authorization: Bearer 用户token
```

## 4. 用户登录

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "test001",
  "password": "123456"
}
```

## 5. 生成自动化脚本

```http
POST /api/ai/generate
Authorization: Bearer 用户token
Content-Type: application/json

{
  "flow_name": "商品资料批量提交",
  "mode": "normal",
  "steps": [
    {
      "order": 1,
      "event": "click",
      "interaction_type": "text_input",
      "field_name": "商品名称",
      "xpath": "//input[@name='product_name']",
      "description": "点击商品名称输入框"
    },
    {
      "order": 2,
      "event": "input",
      "interaction_type": "text_input",
      "field_name": "商品名称",
      "xpath": "//input[@name='product_name']",
      "description": "输入商品名称"
    },
    {
      "order": 3,
      "event": "upload",
      "interaction_type": "file_upload",
      "field_name": "主图",
      "xpath": "//input[@type='file']",
      "description": "上传商品主图"
    },
    {
      "order": 4,
      "event": "manual_verify",
      "interaction_type": "manual_verify",
      "description": "如果出现验证码，由人工处理后继续"
    },
    {
      "order": 5,
      "event": "click",
      "interaction_type": "single_click",
      "xpath": "//button[contains(., '提交')]",
      "description": "点击提交按钮"
    }
  ],
  "template_fields": [
    {"field_name": "商品名称", "type": "text", "required": true},
    {"field_name": "主图", "type": "file", "required": true}
  ],
  "notes": "登录由人工完成。"
}
```

后端校验：

- `normal` 模式最多 20 步
- `advanced` 模式最多 30 步
- `text_input` 和 `file_upload` 必须有 `field_name`
- 缺少定位信息不会直接拒绝，但会返回 `warnings`

返回：

```json
{
  "ok": true,
  "job": {
    "id": 1,
    "status": "completed",
    "result_script": "生成的 Python 脚本",
    "warnings": [],
    "used_provider": "deepseek",
    "used_model": "deepseek-v4-pro"
  }
}
```

## 6. 用户额度

```http
GET /api/usage
Authorization: Bearer 用户token
```

返回免费次数、付费次数、可用总次数。

## 7. DeepSeek 配置

DeepSeek Key 不放在软件端。管理员进入：

```text
https://tools.haobanfa.online/admin
```

保存：

- Provider：DeepSeek
- Base URL：`https://api.deepseek.com`
- Model：`deepseek-v4-pro`
- API Key：DeepSeek 后台创建的 Key
- Thinking：开启
- Reasoning Effort：high

保存后点击“测试模型”，返回 OK 后软件端即可调用生成脚本。
