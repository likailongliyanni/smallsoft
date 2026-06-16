# AI 经验包（学习文件）测试指南

## 设计理念

**问题**：之前每次遇到新场景（下拉菜单/级联菜单/上传/日期选择...）就要改代码改提示词，导致：
- 软件越改越复杂
- 提示词写死成"针对当前场景"
- 改完得发版

**解决**：把"如何处理某场景"作为**知识独立存在**：
1. 文件系统：`resources/prompts/patterns/*.md` （默认经验，git 管理）
2. 数据库：`ai_patterns` 表（管理员可推送的"学习文件"，热更新）

## 文件结构

```
resources/prompts/
├── json_dsl_system.md           # 通用框架（输出要求、Schema）
└── patterns/                    # 经验包（可任意叠加）
    ├── 01-output-strict.md
    ├── 02-description-first.md
    ├── 03-selector-priority.md
    ├── 04-fill-value-source.md
    ├── 05-select-excel-mapping.md
    ├── 06-wait-after-timing.md
    └── 99-final-reminder.md
```

每次 AI 调用前，自动加载：
1. 通用框架 → 文件 patterns（按文件名排序）→ 数据库 patterns（按 priority 排序）
2. 拼接成完整 system prompt 发给 DeepSeek

## 测试步骤

### 1. 部署后验证表已创建

```bash
mysql -u root -p haobanfa
> SHOW TABLES LIKE 'ai_patterns';
> DESCRIBE ai_patterns;
```

### 2. 拿管理员 token

浏览器登录 `/admin` → 控制台跑：
```js
localStorage.getItem('webauto_admin_token')
```

### 3. 预览当前完整 system prompt

```bash
TOKEN="你的admin_token"

curl -H "Authorization: Bearer $TOKEN" \
  https://tools.haobanfa.online/api/admin/ai-patterns/preview
```

返回的 `system_prompt` 字段是 DeepSeek 实际收到的完整提示词。

### 4. 测试：推送一个新经验包

假设我们发现 AI 对"日期选择器"识别不准，写一个经验包：

```bash
curl -X POST https://tools.haobanfa.online/api/admin/ai-patterns \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "date-picker",
    "title": "日期选择器（el-date-picker）",
    "content": "当 step 的 selector 含 \"el-date-editor\" 或 description 含\"日期\"/\"时间\"时：\n- 用 fill 而不是 click\n- value 用 YYYY-MM-DD 格式（如 \"2026-05-24\"）\n- excel_column 非空 → from_excel\n- selector 优先 .el-form-item:has-text(\"<标签>\") input",
    "enabled": true,
    "priority": 50,
    "changelog": "v1.0 新增：日期选择器处理规则"
  }'
```

期望返回：
```json
{
  "ok": true,
  "pattern": {
    "id": 1,
    "code": "date-picker",
    "title": "日期选择器（el-date-picker）",
    "enabled": true,
    "priority": 50,
    ...
  }
}
```

### 5. 验证经验包已生效

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://tools.haobanfa.online/api/admin/ai-patterns/preview \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print('提示词长度:', d['length']); print('结尾:', d['system_prompt'][-500:])"
```

应该能在末尾看到刚推送的"日期选择器"经验包内容。

### 6. 测试软件使用

打开桌面软件，录制一个含日期选择器的流程，生成脚本，看 AI 是否按新规则处理。

### 7. 列出所有经验包

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://tools.haobanfa.online/api/admin/ai-patterns
```

### 8. 更新一个经验包（同 code 自动覆盖）

```bash
curl -X POST https://tools.haobanfa.online/api/admin/ai-patterns \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "date-picker",
    "title": "日期选择器 v2",
    "content": "...更详细的规则...",
    "enabled": true,
    "priority": 50
  }'
```

### 9. 临时禁用某个经验包（不删除）

```bash
curl -X POST https://tools.haobanfa.online/api/admin/ai-patterns \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "date-picker",
    "title": "日期选择器",
    "content": "...",
    "enabled": false
  }'
```

### 10. 删除经验包

```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  https://tools.haobanfa.online/api/admin/ai-patterns/1
```

## 拼接优先级

```
通用框架（json_dsl_system.md）
    ↓
patterns/01-output-strict.md
patterns/02-description-first.md
patterns/03-selector-priority.md
patterns/04-fill-value-source.md
patterns/05-select-excel-mapping.md
patterns/06-wait-after-timing.md
patterns/99-final-reminder.md
    ↓
数据库 ai_patterns 中 enabled=true 的记录
（按 priority ASC，再按 id ASC）
```

数据库的经验包**追加到最后**，所以会**覆盖**文件经验包中冲突的规则（因为 LLM 最后看到的影响更大）。

## 未来可扩展场景

- ✨ 日期选择器 / 时间选择器
- ✨ 富文本编辑器（Quill、TinyMCE、CKEditor）
- ✨ 文件上传（单个 / 多个 / 拖拽）
- ✨ 树形选择器
- ✨ 标签输入框
- ✨ 颜色选择器
- ✨ 滑块/评分
- ✨ 验证码处理（人工介入）
- ✨ 特定网站的快捷规则（电商后台 / ERP / CRM）

每个场景一个 .md 文件，独立维护，不影响其他场景。
