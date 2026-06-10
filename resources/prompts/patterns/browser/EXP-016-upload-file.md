### EXP-016 文件/图片上传 - 普通文件用 `upload`，素材库走 EXP-025

当 step.action_type=upload 或 step.description 含「上传」/「图片」/「附件」时，**先判断是不是素材库弹窗**。

## 优先级最高：素材库弹窗不是普通上传

如果录制步骤里出现这些特征中的 2 条以上：
- 先点击 `.el-upload` / `.el-icon-plus` / 「商品图片」区域打开弹窗
- 弹窗里有「点击上传」/「上传图片」按钮
- 后面点击了 `label.material-name` 或 `pic1.jpg`、`01.png` 这类图片文件名
- 最后点击「确 定」/「确定」

这不是普通单文件上传，**必须交给 EXP-025 合并为 3 步**：
1. click 打开素材库
2. `upload_folder_to_library` 批量上传目录并自动勾选
3. click「确 定」

---

## 普通文件上传（runner 已经支持「目录自动展开」）

除了素材库场景，统一用 `upload` 类型 + `from_excel`：

```json
{
  "type": "upload",
  "selector": "input[type=\"file\"]",
  "from_excel": "<excel_column 的值>",
  "wait_after": 600
}
```

### 🔑 runner 行为说明（自动识别文件 vs 文件夹）

**用户在 Excel 里既可以填单个文件，也可以填整个文件夹路径**，runner 会自动识别：

- 如果路径是文件：上传那一个文件
- 如果路径是文件夹：扫描文件夹里所有支持的文件，一次性批量投递给 `input[type=file]`
  - 如果 input 有 `multiple` 属性：所有文件一次性提交
  - 如果没有 `multiple`：runner 自动逐个调用 `set_input_files`，保证每个文件都上传

支持的扩展名（默认）：
- 图片：jpg, jpeg, png, gif, webp, bmp, svg
- 文档：pdf, doc, docx, txt, csv
- 表格：xls, xlsx
- 视频：mp4, mov, avi

也可以通过 `file_extensions` 字段定制：

```json
{
  "type": "upload",
  "selector": "input[type=\"file\"]",
  "from_excel": "图片文件夹",
  "file_extensions": ["jpg", "png", "webp"],
  "wait_after": 1200
}
```

### Excel 列名建议

优先用「XXX_文件夹」「XXX_目录」格式，提示用户填文件夹路径，例如：
- `主图_文件夹`
- `详情图_目录`
- `附件_文件夹`

如果业务场景就是单文件（比如「身份证正面」），也可以叫「身份证正面_路径」，runner 同样能处理。

### click 上传按钮的处理

如果 step 是「点击上传按钮」（不是真正的文件 input），输出为 click 即可：

```json
{"type": "click", "selector": "button:has-text(\"点击上传\")", "wait_after": 800}
```

通常一次完整的上传序列：
1. click「点击上传」按钮（打开文件对话框）
2. upload 类型给 input[type=file] 设置文件/文件夹路径
3. click「确定」/「保存」

如果整理后只有 1 个 upload 步骤，直接生成 upload action 即可，runner 会用 `expect_file_chooser` 自动拦截浏览器弹的文件选择框。

### `wait_after` 建议

- 单文件上传：600ms
- 文件夹批量上传：1500ms+（让浏览器处理完所有文件）
