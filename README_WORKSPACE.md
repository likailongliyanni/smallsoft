# 好办法网页自动化平台 Laravel 框架版

这是 `tools.haobanfa.online` 的商业后台框架版本，基于 Laravel 12 + PHP 8.2 + MySQL，默认使用 DeepSeek API 生成自动化脚本。

## 已包含模块

- 官网首页
- 注册、登录、账号中心
- 用户注册、登录、免费生成次数
- 软件端 API：训练提交、AI 脚本生成、用户额度查询
- 管理员后台 `/admin`
- 管理员 DeepSeek API 配置和连接测试
- 用户管理、额度调整
- 生成记录、订单记录、反馈记录
- Laravel 数据库迁移
- 录制交互类型 API `/api/interaction-types`
- 内置脚本生成提示词 `resources/prompts/automation_script_system.md`

## 目录说明

- `app/Models`：用户、订单、生成记录、模型配置等数据模型
- `app/Http/Controllers`：用户 API、管理员 API、训练提交 API、AI 生成控制器
- `app/Services`：Token 和 AI 脚本生成服务
- `database/migrations`：数据库迁移
- `resources/views`：首页、注册登录页、账号中心、管理员后台页面
- `public`：宝塔网站运行目录必须指向这里
- `reference/plain_php_commercial_v1`：旧版原生 PHP 参考实现，不参与 Laravel 部署
- `artifacts`：打包文件输出目录

## 本地说明

当前电脑没有检测到 PHP 命令，所以本机没有执行 `composer install`、`php artisan migrate` 和 PHP 语法检查。请在宝塔服务器 PHP 8.2 环境执行部署文档里的校验命令。

## 关键页面

- `/`：公开首页
- `/login`：登录入口
- `/register`：注册入口
- `/account`：普通用户账号中心
- `/admin`：管理员后台，不在公开导航显示
- `/api/health`：健康检查
- `/api/interaction-types`：录制软件读取交互方式配置

## DeepSeek 配置

后台页面 `/admin` 可以保存 DeepSeek API Key。也可以在 `.env` 里配置：

```env
AI_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_API_KEY=你的DeepSeekKey
DEEPSEEK_THINKING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=high
```

推荐优先在管理员后台保存 Key，这样软件端不会接触模型 Key。

## 管理员账号

管理员账号不写死在数据库，第一次登录时会根据 `.env` 自动创建或更新管理员用户：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ChangeMe_2026!
```

上线必须修改默认密码。

页面逻辑：

- 首页只做注册/登录入口，不放复杂体验流程。
- 右上角只保留“注册”和“登录”。
- 普通用户点击登录后进入 `/account`。
- 管理员账号点击登录后进入 `/admin`，在后台配置 DeepSeek API 和用户额度。
- `/console` 会跳转到 `/account`，复杂自动化体验后续放到桌面软件。
