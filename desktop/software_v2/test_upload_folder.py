"""
测试 upload action 的文件夹自动展开功能
========================================

无依赖，独立运行：
    cd software_v2
    python test_upload_folder.py

会做这些事：
  1. 在系统临时目录创建测试文件夹 + 3 张 png + 1 个无关文件 + 1 个子目录
  2. 创建本地测试 HTML（含 multiple / 非 multiple 两个 input）
  3. 启动 Chrome
  4. 模拟 dsl.py upload action 的逻辑，跑 3 个场景
     - 场景 A：填单个文件路径 → 上传 1 个
     - 场景 B：填文件夹路径 + multiple input → 一次性上传 3 个
     - 场景 C：填文件夹路径 + 非 multiple input → iterative 模式逐个传

不需要服务器，不需要登录，不消耗 AI 额度。
"""

import os
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


# ════════════════════════════════════════
#  1. 准备测试文件夹和测试文件
# ════════════════════════════════════════
TEST_DIR = Path(tempfile.gettempdir()) / "hbf_upload_test"
TEST_DIR.mkdir(exist_ok=True)

# 清理上次的残留
for f in TEST_DIR.iterdir():
    if f.is_file():
        f.unlink()

# 最小有效 PNG（1x1 红色像素，66 字节）
MIN_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8cfc0f01f000005000100ce1f4c98"
    "0000000049454e44ae426082"
)

# 3 张应该被扫描到的图片
for i in range(1, 4):
    (TEST_DIR / f"test_{i}.png").write_bytes(MIN_PNG)

# 一个不该被扫描的扩展名
(TEST_DIR / "ignore.unknown").write_text("not an image")

# 子目录里的文件也不该被扫描（dsl.py 只扫一级）
subdir = TEST_DIR / "subfolder"
subdir.mkdir(exist_ok=True)
(subdir / "nested.png").write_bytes(MIN_PNG)

print(f"📂 测试文件夹: {TEST_DIR}")
print(f"   ├── test_1.png      ← 应被扫描")
print(f"   ├── test_2.png      ← 应被扫描")
print(f"   ├── test_3.png      ← 应被扫描")
print(f"   ├── ignore.unknown  ← 不该被扫描（扩展名不在白名单）")
print(f"   └── subfolder/")
print(f"       └── nested.png  ← 不该被扫描（子目录）")
print()


# ════════════════════════════════════════
#  2. 创建测试 HTML
# ════════════════════════════════════════
TEST_HTML = TEST_DIR / "upload_test.html"
TEST_HTML.write_text("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Upload Test</title>
<style>
  body { font-family: 'Microsoft YaHei', sans-serif; padding: 24px; max-width: 720px; margin: 0 auto; }
  h2 { color: #16a34a; }
  h3 { color: #0c4a6e; margin-top: 24px; }
  .result { padding: 10px; background: #f0fdf4; border: 1px solid #16a34a; border-radius: 6px;
            margin-top: 8px; min-height: 24px; font-family: Consolas, monospace; }
  input[type=file] { padding: 8px; border: 1px dashed #94a3b8; border-radius: 6px; width: 100%; }
</style></head>
<body>
  <h2>📁 文件上传测试页（dsl.py upload 自动展开验证）</h2>

  <h3>① input[type=file multiple]</h3>
  <input id="multi" type="file" multiple accept="image/*">
  <div class="result" id="multi-result">还没选择文件</div>

  <h3>② input[type=file]（不支持 multiple）</h3>
  <input id="single" type="file" accept="image/*">
  <div class="result" id="single-result">还没选择文件</div>

  <script>
    function showFiles(input, resultId) {
      const files = Array.from(input.files);
      const names = files.map(f => f.name).join(', ');
      document.getElementById(resultId).textContent =
        files.length === 0 ? '还没选择文件' : `✓ 已选 ${files.length} 个文件: ${names}`;
    }
    document.getElementById('multi').onchange = e => showFiles(e.target, 'multi-result');
    document.getElementById('single').onchange = e => showFiles(e.target, 'single-result');
  </script>
</body></html>
""", encoding="utf-8")

print(f"📄 测试 HTML: {TEST_HTML}")
print()


# ════════════════════════════════════════
#  3. 模拟 dsl.py 的 upload 逻辑
# ════════════════════════════════════════
def simulate_upload(page, selector: str, raw_path: str):
    """完全复刻 dsl.py 里 upload action 的核心逻辑"""

    # ---- 路径清洗（dsl.py 新加的）----
    path = raw_path.strip().strip('"').strip("'").strip()
    if not path:
        raise RuntimeError("路径为空")

    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"路径不存在: {path}")

    # ---- 自动识别：文件 vs 文件夹 ----
    if p.is_dir():
        extensions = {
            "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg",
            "pdf", "doc", "docx", "txt", "csv",
            "xls", "xlsx",
            "mp4", "mov", "avi",
        }
        files = []
        for fname in sorted(os.listdir(path)):
            fp = p / fname
            if fp.is_file():
                ext = fp.suffix.lower().lstrip(".")
                if ext in extensions:
                    files.append(str(fp))
        if not files:
            raise RuntimeError(f"目录下没找到可上传的文件: {path}")
        paths_to_upload = files
        print(f"  → 检测到目录，扫到 {len(files)} 个文件")
        for f in files:
            print(f"      {Path(f).name}")
    elif p.is_file():
        paths_to_upload = [str(p)]
        print(f"  → 单文件 {p.name}")
    else:
        raise RuntimeError(f"既不是文件也不是目录: {path}")

    multi_count = len(paths_to_upload)
    locator = page.locator(selector)

    # ---- multiple 检测 + 投递 ----
    if multi_count <= 1:
        locator.set_input_files(paths_to_upload)
        return ("single", multi_count)

    is_multi = locator.evaluate("el => !!el.multiple")
    print(f"  → input.multiple = {is_multi}")

    if is_multi:
        locator.set_input_files(paths_to_upload)
        return ("batch", multi_count)

    # iterative fallback
    for i, fp in enumerate(paths_to_upload, 1):
        locator.set_input_files(fp)
        page.wait_for_timeout(300)
        print(f"      [{i}/{multi_count}] iterative 投递 {Path(fp).name}")
    return ("iterative", multi_count)


# ════════════════════════════════════════
#  4. 跑 3 个场景
# ════════════════════════════════════════
print("=" * 60)
print("启动浏览器...")
print("=" * 60)
print()

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(f"file:///{TEST_HTML.as_posix()}")
    page.wait_for_load_state("domcontentloaded")

    passed = 0
    failed = 0

    def check(name: str, expected: str, actual: str):
        global passed, failed
        if expected in actual:
            print(f"  ✅ {name} 通过")
            passed += 1
        else:
            print(f"  ❌ {name} 失败")
            print(f"     期望包含: {expected!r}")
            print(f"     实际:     {actual!r}")
            failed += 1

    # ---- 场景 A：单文件路径 ----
    print("━" * 60)
    print("场景 A：Excel 填单个文件路径 → 上传 1 个")
    print("━" * 60)
    raw = str(TEST_DIR / "test_1.png")
    print(f"  Excel 单元格内容: {raw!r}")
    mode, count = simulate_upload(page, "#single", raw)
    print(f"  → 投递模式 = {mode}, 文件数 = {count}")
    page.wait_for_timeout(500)
    result = page.locator("#single-result").text_content()
    print(f"  浏览器显示: {result}")
    check("A. 单文件上传", "已选 1 个文件: test_1.png", result)
    print()

    # ---- 场景 B：文件夹 + multiple ----
    print("━" * 60)
    print("场景 B：Excel 填文件夹路径 + multiple input → 一次性 3 个")
    print("━" * 60)
    raw = f'  "{TEST_DIR}"  '   # 故意带空格和引号，验证清洗
    print(f"  Excel 单元格内容（带引号+空格）: {raw!r}")
    mode, count = simulate_upload(page, "#multi", raw)
    print(f"  → 投递模式 = {mode}, 文件数 = {count}")
    page.wait_for_timeout(500)
    result = page.locator("#multi-result").text_content()
    print(f"  浏览器显示: {result}")
    check("B. multiple 批量上传", "已选 3 个文件", result)
    print()

    # ---- 场景 C：文件夹 + 非 multiple ----
    print("━" * 60)
    print("场景 C：Excel 填文件夹路径 + 非 multiple input → iterative 模式")
    print("━" * 60)
    raw = str(TEST_DIR)
    print(f"  Excel 单元格内容: {raw!r}")
    mode, count = simulate_upload(page, "#single", raw)
    print(f"  → 投递模式 = {mode}, 文件数 = {count}")
    page.wait_for_timeout(500)
    result = page.locator("#single-result").text_content()
    print(f"  浏览器显示: {result}")
    # 非 multiple 的 input 实际只能保留最后一个文件，这是浏览器规则
    check("C. iterative 模式", "已选 1 个文件: test_3.png", result)
    print()

    # ---- 错误路径测试 ----
    print("━" * 60)
    print("场景 D：路径不存在 → 应抛出明确错误")
    print("━" * 60)
    try:
        simulate_upload(page, "#multi", r"D:\绝对不存在的路径\xxx")
        print("  ❌ 应该报错但没有")
        failed += 1
    except RuntimeError as e:
        print(f"  ✅ 正确抛错: {e}")
        passed += 1
    print()

    # ---- 总结 ----
    print("=" * 60)
    print(f"测试完成: ✅ 通过 {passed}  ❌ 失败 {failed}")
    print("=" * 60)

    if failed == 0:
        print("\n🎉 全部通过！dsl.py 的 upload 文件夹展开功能工作正常")
    else:
        print(f"\n⚠️  有 {failed} 个失败，看上面的输出排查")

    print(f"\n浏览器留着方便你检查，按 Enter 关闭...")
    input()
    browser.close()
