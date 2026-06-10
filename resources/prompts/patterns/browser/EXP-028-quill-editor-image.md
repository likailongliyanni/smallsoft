### EXP-028 富文本编辑器图片上传识别（Quill / WangEditor / TinyMCE）

**问题场景**：商品后台经常有「商品图片」+「详情图」两个上传位置，**详情图通过富文本编辑器的"插图"按钮上传**。常见编辑器特征：

| 编辑器 | 工具栏图片按钮 selector |
|---|---|
| Quill (ql-*) | `button.ql-image` |
| WangEditor (w-e-*) | `.w-e-toolbar [data-menukey="image"]` |
| TinyMCE (tox-*) | `button.tox-tbtn[title*="image" i]` |
| 通用 ProseMirror | `[class*="image"]` in toolbar |

---

## 识别 + 合并规则

**特征识别**（满足任意 2 条就当作富文本图片上传）：
1. 有一个 click 的 selector 含 `ql-image` / `w-e-toolbar` + image / `tox-` + image
2. 该 click 的 user_note / description 含「详情图」/「编辑器」/「插图」/「富文本」
3. 紧跟一个 input action_type，selector 含 `ql-editor` / `w-e-text` / `tox-edit-area` / class 含 `editor`
4. 该 input 的 label 为空 / 是 "描述" / 是 "详情" / 是 "内容"

**合并方案**（把 click + 后续 input 合并为 **1 个 upload_folder_to_library**）：

录制 2 步：
```
step 38: click button.ql-image  (description="输入详情图的按钮")
step 39: input div.ql-editor    (excel_column="输入字段_39")
```

→ 应该生成 1 个 action：
```json
{
  "type": "upload_folder_to_library",
  "selector": ".el-dialog__wrapper input[type=\"file\"], input[type=\"file\"][accept*=\"image\"]",
  "xpath": "<step 38 的 xpath>",
  "from_excel": "详情图目录",
  "file_extensions": ["jpg", "jpeg", "png", "gif", "webp"],
  "item_selector": "label.material-name, .ql-editor img",
  "select_strategy": "last_n",
  "wait_timeout": 300000,
  "wait_after": 1500
}
```

---

## from_excel 列名规则

- 命名 `<label>目录` 或 `详情图目录`
- 如果是 ql-image：用 `详情图目录`
- 如果整个 form-item 的 label 是「描述」或「内容」：仍叫 `详情图目录`
- ❌ **绝对不要**生成 `输入字段_39` 这种废名
- ❌ **绝对不要**保留原 input 步骤的 fill action

---

## 与 EXP-025 的关系

一个商品上架页通常**同时有 2 个上传**：
- 主图（商品图片）→ 走 EXP-025（素材库弹窗模式）
- 详情图（描述/详情）→ 走 EXP-028（富文本编辑器模式）

→ Excel 模板里**两列都要**：「商品图片目录」+ 「详情图目录」

**绝对禁止**：
- ❌ 只识别主图，跳过详情图（用户看 Excel 列就懵了）
- ❌ 把详情图当普通 input 处理（生成 `输入字段_N` 这种废名）
- ❌ 把主图和详情图合并到同一列（两个目录应该是不同的）

---

## 完整示例（用户的真实案例 daoyeshan.com）

录制 40 步，关键段落：

```
step 4:  click i (scoped: .el-form-item:has-text("商品图片") .el-icon-plus)
         description="点击添加图片"
step 5:  click button:has-text("点击上传")
         description="点击上传图片按钮打开本地文件夹"
step 6-11: click label.material-name:has-text("01.jpg/02.jpg/03.jpg") (重复点)
         description="勾选上传的图片"
step 12: click button:has-text("确 定")
         description="确认图片上传"

step 38: click button.ql-image
         description="输入详情图的按钮"
step 39: input div.ql-editor
         description="在「输入框」输入内容"
```

→ AI 输出（主图走 EXP-025，详情图走 EXP-028）：

```json
[
  // 主图（EXP-025）
  {"type":"click", "selector":".el-form-item:has-text(\"商品图片\") .el-icon-plus", "wait_after":1000},
  {"type":"upload_folder_to_library", "from_excel":"商品图片目录", ...},
  {"type":"click", "selector":"button:has-text(\"确 定\")", "wait_after":800},

  // ... 中间步骤 ...

  // 详情图（EXP-028）
  {"type":"upload_folder_to_library", "from_excel":"详情图目录",
   "selector":"input[type=\"file\"][accept*=\"image\"], .el-dialog__wrapper input[type=\"file\"]",
   "item_selector":"label.material-name, .ql-editor img",
   ...}
]
```

**结果**：Excel 模板正确包含 `商品图片目录` 和 `详情图目录` 两列，用户填两个路径就能跑 ✅
