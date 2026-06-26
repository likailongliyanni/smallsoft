# -*- coding: utf-8 -*-
"""证件识别命令行试跑工具（规则路径，免费、不连服务器）。

用法：
    python 试跑识别.py "证件文件夹路径"
    python 试跑识别.py            （不带参数会提示你输入文件夹）

对文件夹里每个证件：判断是「有文字层」还是「扫描件」，
有文字层的当场抠出 类型/证件号/公司/日期；扫描件标注"需视觉AI"。
"""

import sys
from pathlib import Path

# 让脚本无论从哪个目录运行，都能 import 同目录的 docintel
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import docintel as di
except Exception as exc:
    print("无法加载识别引擎 docintel.py：", exc)
    sys.exit(1)

SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
             ".docx", ".xlsx", ".xlsm", ".txt", ".csv"}


def main() -> None:
    if len(sys.argv) > 1:
        folder = " ".join(sys.argv[1:]).strip().strip('"')
    else:
        folder = input("请把证件文件夹路径粘进来，回车：").strip().strip('"')

    root = Path(folder).expanduser()
    if not root.is_dir():
        print(f"找不到文件夹：{root}")
        sys.exit(1)

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        print(f"该文件夹里没有支持的证件文件。支持：{'、'.join(sorted(SUPPORTED))}")
        return

    print(f"\n共 {len(files)} 份文件，开始试跑识别（规则路径，不花钱）：\n" + "=" * 60)
    text_layer = scanned = 0
    for i, path in enumerate(files, 1):
        try:
            text = di.extract_text(path)
        except Exception as exc:
            print(f"[{i}] 读取失败 {path.name[:40]}：{exc}")
            continue

        if di.needs_vision(path, text):
            scanned += 1
            try:
                imgs = di.render_pages_png(path, max_pages=1)
                kb = (len(imgs[0]) // 1024) if imgs else 0
            except Exception:
                kb = 0
            print(f"[{i}] 🖼  扫描件 → 需视觉AI   {path.name[:46]}")
            print(f"      文字层 0 字，已可渲染成页图({kb}KB)发视觉模型\n")
        else:
            text_layer += 1
            s = di.normalize_suggestion(di.rule_suggestion(text))
            print(f"[{i}] 📄  文字层 → 规则识别   {path.name[:46]}")
            print(f"      类型：{s['document_type_label']}    证件号：{s['certificate_no'] or '—'}")
            print(f"      公司：{s['company_name'] or '—'}")
            print(f"      日期：{s['issued_at'] or '—'} ~ {s['expires_at'] or '—'}    置信：{s['ai_confidence']}\n")

    print("=" * 60)
    print(f"完成：{len(files)} 份，文字层 {text_layer} 份（已出字段）、扫描件 {scanned} 份（待视觉AI）。")
    print("提示：扫描件的字段要等服务器视觉识别端点上线后才能出。")


if __name__ == "__main__":
    main()
