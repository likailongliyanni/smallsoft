### EXP-024 多图上传

**runner 已支持 `upload_folder_to_library`**：用户在 Excel **一格填文件夹路径**，runner 自动扫描目录里所有图片 → 全部上传 → 等待完成 → 自动勾选最近 N 张。

> 本规则优先级低于 EXP-025。只要识别到“点击上传区域 → 素材库弹窗 → 点击/勾选图片名 → 确定”的素材库流程，就不要按普通多图拆分，必须走 EXP-025 的 3 步合并。

---

## 两种多图场景

### 场景 1：素材库（弹窗式上传）→ 走 EXP-025 的 3 步合并模板

典型特征：点上传按钮 → 弹出素材库弹窗 → 弹窗里选「点击上传」→ 上传完成出现在弹窗列表里 → 勾选后点「确定」回填表单。

```json
[
  // 第 1 步：点开素材库弹窗（用 scoped_selector 锚定 form-item label）
  {"type":"click", "selector":".el-form-item:has-text(\"商品图片\") .el-upload",
   "xpath":"...", "wait_after":1000},

  // 第 2 步：批量上传（扫文件夹 + 等完成 + 自动勾选）
  {"type":"upload_folder_to_library",
   "selector":".el-dialog__wrapper input[type=\"file\"]",
   "from_excel":"商品图片目录",
   "file_extensions":["jpg","jpeg","png","gif","webp"],
   "item_selector":"label.material-name",
   "select_strategy":"last_n",
   "wait_timeout":300000,
   "wait_after":1000},

  // 第 3 步：点「确定」关闭弹窗
  {"type":"click", "selector":"button:has-text(\"确 定\")", "xpath":"...", "wait_after":500}
]
```

用户 Excel：
| 商品名 | 商品图片目录 |
|--------|---|
| 商品A | D:\图\A\ |
| 商品B | D:\图\B\ |

兼容旧模板：如果现有 Excel 已经有「商品图片路径」「主图路径」这类列，并且用户实际填的是文件夹路径，可以继续用这个现有列名作为 `from_excel`；新建列时优先命名为「<label>目录」。

### 场景 2：普通多图（无素材库，直接是 `<input type=file multiple>`）

`upload_folder_to_library` 同样适用——`input[type=file]` 不在弹窗里也没关系，selector 指过去就行。`item_selector` 用页面上展示已上传图的容器。

如果实在没有"已上传"列表能监测（极少情况），退化用多个 `upload`：

```json
{"type":"upload","selector":"input[type=\"file\"]","from_excel":"主图路径1","wait_after":1500},
{"type":"upload","selector":"input[type=\"file\"]","from_excel":"主图路径2","wait_after":1500}
```

---

## DSL 字段速查（`upload_folder_to_library`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `type` | ✓ | 固定 `"upload_folder_to_library"` |
| `selector` | ✓ | `input[type=file]` 的 selector（弹窗里推荐 `.el-dialog__wrapper input[type="file"]`） |
| `xpath` | ✓ | 同上 xpath 兜底（EXP-023 强制） |
| `from_excel` | ✓ | Excel 列名，用户填**文件夹路径** |
| `file_extensions` |   | 默认 `["jpg","jpeg","png","gif","webp","bmp"]` |
| `item_selector` |   | 已上传素材项 selector，默认 `label.material-name` |
| `select_strategy` |   | `last_n`（默认）/ `first_n`，最近上传的位置 |
| `wait_timeout` |   | 等上传完成最长 ms，默认 300000（5 分钟，上传大量图够用）|
| `wait_after` |   | 勾选前额外等 ms，默认 1000 |

---

**铁律**：
- ✅ 凡是录制时**一次性上传了多张图**，都生成 `upload_folder_to_library`（不要拆成多个 `upload`）
- ✅ 新建 Excel 列名用「<label>目录」（比如「商品图片目录」「详情图目录」）；已有旧列「<label>路径」且里面填文件夹路径时可以复用
- ✅ xpath 必须输出（EXP-023）
- ❌ 不要把多张图路径写死在 selector 里（如 `pic1.jpg / pic2.jpg`）
- ❌ 不要拆成 N 个单文件 upload（运行 N 倍慢，用户填表也累）
- ❌ 不要用 `upload_dir` 这种类型（runner 不认识，只认 `upload_folder_to_library`）
