### EXP-025 素材库/图片选择弹窗 → 3 步合并（**强制规则**，runner 已支持 `upload_folder_to_library`）

> ⚠️ **本规则优先级高于 EXP-016/EXP-020/EXP-024**。识别到素材库模式时，必须合并、必须去重、必须生成 `upload_folder_to_library`。EXP-016 只管普通单文件上传，EXP-020 只管普通 click，素材库流程是**特例**。

**场景识别**：很多后台系统上传图片不是直接 `<input type="file">`，而是打开一个**素材库弹窗**，流程是：

```
1. click 上传区域（如 .el-upload）→ 打开素材库弹窗
2. click「点击上传」按钮（把本地图片传到素材库）
3. click 具体图片名（如 01.jpg、pic1.jpg）→ 勾选图片
4. click「确 定」→ 关闭弹窗，图片选入表单
```

**判断方法**（满足 **任意 2 条** 立即按本规则合并，不要怀疑）：
1. 有一个 click 的 scoped_selector / selector 含 `.el-upload` / `.ant-upload` / `upload` / 「商品图片」+ upload 字样
2. 紧跟一个 click，selector 含 `"点击上传"` / `"上传图片"` / `"选择文件"`
3. 后面 **任意一个** click 的 selector / label / text 含文件名模式（`*.jpg` / `*.png` / `*.jpeg` / `*.gif` / `*.webp` / `*.bmp`）**或** class 含 `material-name` / `material` / `media` / `file-item`
4. 之后某个 click 是 `"确 定"` / `"确定"` / `"提交"` 按钮
5. 这些步骤的 excel_column 全为空（录制时未绑定 Excel 列）

**典型识别示例**（看到下面这种结构 → **立即合并**）：

录制的 8 步（用户实际操作）：
```
step  6: click `.el-form-item:has-text("商品图片") .el-upload`      ← 条件 1 ✓
step  7: click `button:has-text("点击上传")`                         ← 条件 2 ✓
step  8: click `label.material-name:has-text("01.jpg")`              ← 条件 3 ✓
step  9: click `label.material-name:has-text("01.jpg")`  ← 重复点击  ← 条件 3 ✓（也是文件名）
step 10: click `label.material-name:has-text("03.jpg")`              ← 条件 3 ✓
step 11: click `label.material-name:has-text("03.jpg")`  ← 重复点击
step 12: click `label.material-name:has-text("02.jpg")`
step 13: click `label.material-name:has-text("02.jpg")`  ← 重复点击
step 14: click `button:has-text("确 定")`                            ← 条件 4 ✓
```

→ **必须** 合并为 **3 个 actions**（**而不是保留 9 个 click**）：

```json
[
  // 1. 打开素材库
  {"type": "click",
   "selector": ".el-form-item:has-text(\"商品图片\") .el-upload",
   "xpath": "<step 6 xpath>",
   "wait_after": 1000},

  // 2. ⭐ 批量上传整个文件夹（核心！新列用 "商品图片目录"，已有旧列也可复用）
  {"type": "upload_folder_to_library",
   "selector": ".el-dialog__wrapper input[type=\"file\"]",
   "xpath": "",
   "from_excel": "商品图片目录",
   "file_extensions": ["jpg", "jpeg", "png", "gif", "webp"],
   "select_strategy": "first_n",
   "wait_timeout": 300000,
   "wait_after": 1000},

  // 3. 点击确定
  {"type": "click",
   "selector": "button:has-text(\"确 定\")",
   "xpath": "<step 14 xpath>",
   "wait_after": 800}
]
```

**绝对禁止**（违反本规则）：
- ❌ 保留 step 7 的「点击上传」click —— runner 不需要点这个按钮就能传文件
- ❌ 保留 step 8-13 任何一个文件名 click —— 文件名是录制时硬编码的，跑别的商品就废了
- ❌ 把素材库当普通流程用 EXP-020 不去重 —— 那会保留 9 个 click 还都是错的
- ❌ 不设置 from_excel —— 用户拿到 Excel 没列怎么填？没有现成列时必须发明「<label>目录」

---

**核心规则**：把整个素材库流程合并为 **3 步**，**第 2 步用 `upload_folder_to_library`** 让 runner 自动扫文件夹 + 上传所有图 + 等完成 + 自动勾选最近 N 张。

```json
[
  // 第 1 步：打开素材库弹窗
  {
    "type": "click",
    "selector": ".el-form-item:has-text(\"商品图片\") .el-upload",
    "xpath": "<原始 xpath>",
    "wait_after": 1000
  },

  // 第 2 步：批量上传整个文件夹 + 自动勾选
  {
    "type": "upload_folder_to_library",
    "selector": ".el-dialog__wrapper input[type=\"file\"]",
    "xpath": "",
    "from_excel": "商品图片目录",
    "file_extensions": ["jpg", "jpeg", "png", "gif", "webp"],
    "item_selector": "label.material-name",
    "select_strategy": "last_n",
    "wait_timeout": 300000,
    "wait_after": 1000
  },

  // 第 3 步：点击确定（关闭弹窗，自动勾选的 N 张图填入表单）
  {
    "type": "click",
    "selector": "button:has-text(\"确 定\")",
    "xpath": "<原始 xpath>",
    "wait_after": 800
  }
]
```

**中间的步骤全部跳过**：
- ❌ 跳过「点击上传」按钮的 click（runner 直接对 input[type=file] 调用 set_input_files，不需要点按钮）
- ❌ 跳过所有点击具体图片名的 click（pic1.jpg / pic2.jpg 等录制时硬编码的文件名）
- ❌ 跳过重复的 click

---

## `from_excel` 列名规则

- 优先复用现有 Excel 列：如果模板/Excel 已经有「商品图片路径」「主图路径」这类列，并且这个素材库字段对应它，可以继续用该列作为 `from_excel`（用户实际填文件夹路径即可）
- 没有现成列时，用 step 1 的 `label` 字段 + "目录" 后缀新建列
- 例如 label="商品图片" → 新列 `"from_excel": "商品图片目录"`；旧模板已有 `"商品图片路径"` 时也允许保留
- 例如 label="详情图" → `"from_excel": "详情图目录"`
- 如果 label 为空，用 "图片目录" 作为默认列名
- 新建列名推荐包含「目录」二字，表示用户填文件夹；旧列名含「路径」时 runner 会兼容

用户在 Excel 里**一格填一个文件夹路径**：
| 商品名 | 商品图片目录 / 商品图片路径 |
|--------|-----------------------------|
| 商品A | D:\商品图\商品A\ |
| 商品B | D:\商品图\商品B\ |

文件夹下放几张图都行，runner 自动数 + 自动上传 + 自动勾选刚传的那几张。

---

## runner 的执行逻辑（v2.0 实测验证过）

1. 点击 `.el-upload` → 素材库弹窗打开（等 1000ms）
2. runner 扫描 Excel 列指向的文件夹下所有 .jpg/.png 等
3. 快照上传前页面上 `input[type=file]` 数量
4. 调用 `set_input_files(...)` **一次性投递所有图片**（投递失败时自动回退到最新出现的 input）
5. 等浏览器处理上传（每张 250ms，至少 800ms）
6. 动态轮询 4 种 checkbox selector，找到 `span.el-checkbox__inner`（≥ N 个）
   - 优先：`//div[contains(@class,'el-dialog')]//span[contains(@class,'el-checkbox__inner')]`
   - 备用：`.el-dialog__wrapper label.el-checkbox`、`.el-drawer__wrapper span.el-checkbox__inner`
7. 按 `select_strategy=first_n`（新图在顶部）真实 Playwright click 勾选 N 个
8. 点击「确 定」→ 弹窗关闭，N 张图填入表单

---

## 多个独立素材库（如主图 + 详情图）

每个用一组 3 步，列名分开：

```json
// 主图组（3 步）
{"type":"click", "selector":".el-form-item:has-text(\"主图\") .el-upload", "xpath":"...", "wait_after":1000},
{"type":"upload_folder_to_library", "selector":"...", "from_excel":"主图目录", "item_selector":"label.material-name", ...},
{"type":"click", "selector":"button:has-text(\"确 定\")", "xpath":"...", "wait_after":800},

// 详情图组（3 步）
{"type":"click", "selector":".el-form-item:has-text(\"详情\") .el-upload", "xpath":"...", "wait_after":1000},
{"type":"upload_folder_to_library", "selector":"...", "from_excel":"详情图目录", "item_selector":"label.material-name", ...},
{"type":"click", "selector":"button:has-text(\"确 定\")", "xpath":"...", "wait_after":800}
```

---

**铁律**：
- ✅ 识别到素材库模式 → 必须合并为 3 步（开弹窗 + upload_folder_to_library + 确定）
- ✅ 第 2 步 **type 必须是 `upload_folder_to_library`**（runner 已实现，扫文件夹 + 自动勾选）
- ✅ 第 2 步的 selector 优先 `.el-dialog__wrapper input[type="file"]`
- ✅ **不要带 `item_selector` 字段**（v2.0 起 runner 内置 4 个 checkbox selector 自动尝试，不需要 AI 指定）
- ✅ **不要带 `select_strategy` 字段**（v2.0+ 默认 `auto_diff`：上传前/后 snapshot 比较，自动识别新图位置，不管在 top-left 还是 bottom-right 都对）；如果你确实知道目标站只能用 first_n / last_n 才显式写
- ✅ 新建 `from_excel` 列名用「<label>目录」；已有旧列「<label>路径」且里面填文件夹路径时可以复用
- ✅ 保留开弹窗和确定的 xpath（EXP-023）
- ❌ 不要保留中间点击具体图片名的 click
- ❌ 不要拆成多个 `upload`（runner 一次性投递所有图，效率更高）
- ❌ 不要用 `upload_dir` 这种类型（runner 不认识）

**特殊情况**：
- 如果用户在整理页**已经手动给某个图片点击步骤绑了 excel_column**，说明用户有自己的意图，按正常 click + from_excel 输出，不要合并
- 如果素材库弹窗内没有 `.el-dialog__wrapper`，用更宽泛的 `.el-overlay-dialog input[type="file"]` 或 `input[type="file"]` 兜底
