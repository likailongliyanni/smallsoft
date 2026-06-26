# 好办法 AI 档案管理桌面端

这是 AI 档案管理 EXE 的第一版工程骨架。

## 当前已完成

- Electron + Vue 桌面界面
- Python 本地处理进程
- 本机序列号生成，编号带 `AIDOC` 后缀
- 无账号注册模式，按现有桌面软件方式登记设备
- 免费页额度默认 `50 页`
- 本地密码设置/验证
- 本地资料库目录设置
- 本地 SQLite 资料库
- 递归扫描文件夹
- PDF/图片/Word/Excel/文本的页数统计入口
- 按页进度事件，前端实时进度条
- 复制导入或仅建索引两种模式
- 原始文件不上传，当前只和后台同步设备/额度

## 运行

```powershell
cd E:\SaaS\project002\desktop\aidoc-manager-electron
npm install --registry=https://registry.npmmirror.com
npm run dev
```

Python 依赖：

```powershell
pip install -r requirements.txt
```

没有安装这些 Python 依赖时，软件仍可启动；PDF、Word、Excel 页数统计会使用兜底逻辑。

## 计费口径

- PDF：每页 1 次
- 图片：每张 1 次
- Word：第一版按文字量估算页数，后续可接 Office/LibreOffice 精确分页
- Excel：第一版按 sheet 数计页
- 成功导入才计入本次可计费页
- 重复文件按 hash 跳过，不重复计费

## 后台接口

沿用图片软件的设备登记模式：

- `POST /api/desktop/device/register`
- `GET /api/desktop/device/status`

AIDOC 上报：

```json
{
  "software_id": "001122AABBCC-AIDOC",
  "app": "ai-doc",
  "version": "0.1.0",
  "quota_unit": "page",
  "free_quota": 50
}
```

后续真实识别接入时，桌面端应只发送本地 OCR/解析后的文字和结构化片段，不上传用户原始文件。
