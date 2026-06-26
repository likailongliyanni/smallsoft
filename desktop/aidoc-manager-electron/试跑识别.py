# -*- coding: utf-8 -*-
"""证件识别命令行试跑工具。

用法：
    python 试跑识别.py "证件文件夹路径"          规则路径，免费、不连服务器
    python 试跑识别.py "证件文件夹路径" --ai      连服务器走真 AI 识别（扫描件也出字段，按页扣额度）
    python 试跑识别.py                            不带参数会提示你输入文件夹

规则路径：有文字层的当场抠 类型/证件号/公司/日期；扫描件标注"需视觉AI"。
--ai 路径：先注册取 token，再把文字/页图发服务器识别端点，返回完整字段（部署服务器端点后才可用）。
"""

import sys
from pathlib import Path

# 让脚本无论从哪个目录运行，都能 import 同目录的 docintel / backend
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import docintel as di
except Exception as exc:
    print("无法加载识别引擎 docintel.py：", exc)
    sys.exit(1)

SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
             ".docx", ".xlsx", ".xlsm", ".txt", ".csv"}


def _print_fields(prefix: str, s: dict) -> None:
    # 按「版面样式.xlsx」定义的类型字段顺序显示
    print(f"      类型：{s['document_type_label']}    置信：{s['ai_confidence']}")
    for row in di.project_to_profile(s):
        print(f"      {row['label']}：{str(row['value'])[:70] or '—'}")
    print()


def run_ai(files: list) -> None:
    """连服务器走真 AI 识别。"""
    import backend as b
    reg = b.command_register({})
    if not b.STATE.get("token"):
        print("注册失败，拿不到 token，无法连服务器：", reg.get("message") or reg)
        return
    print(f"已注册，可用额度：{(reg.get('quota') or {}).get('available', '?')} 页\n" + "=" * 60)

    for i, path in enumerate(files, 1):
        text = di.extract_text(path)
        use_vision = di.needs_vision(path, text)
        rule = di.rule_suggestion(text)
        tag = "🖼 扫描件" if use_vision else "📄 文字层"
        print(f"[{i}] {tag} → AI 识别中…   {path.name[:46]}")
        try:
            if use_vision:
                imgs = di.render_pages_png(path, max_pages=2)
                ai = b.recognize_via_server("vision", "", imgs, max(1, len(imgs)), path.name)
            else:
                ai = b.recognize_via_server("text", text, [], 1, path.name)
        except Exception as exc:
            print(f"      识别失败：{exc}\n")
            continue
        if ai is None:
            print(f"      ⚠ AI 失败：{getattr(b, 'LAST_RECOGNIZE_ERROR', '') or '未知'}　→ 退回规则：")
            _print_fields("", di.normalize_suggestion(rule))
            continue
        _print_fields("", di.merge_rule_and_ai(rule, ai))


def run_rule(files: list) -> None:
    """纯规则路径，不连服务器。"""
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
            print(f"[{i}] 📄  文字层 → 规则识别   {path.name[:46]}")
            _print_fields("", di.normalize_suggestion(di.rule_suggestion(text)))
    print("=" * 60)
    print(f"完成：{len(files)} 份，文字层 {text_layer} 份（已出字段）、扫描件 {scanned} 份（待视觉AI）。")
    print("提示：要让扫描件也出字段、字段更准，加 --ai 连服务器（需先部署识别端点）。")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    ai_mode = "--ai" in args
    args = [a for a in args if a != "--ai"]
    folder = (" ".join(args).strip().strip('"')
              if args else input("请把证件文件夹路径粘进来，回车：").strip().strip('"'))

    root = Path(folder).expanduser()
    if not root.is_dir():
        print(f"找不到文件夹：{root}")
        sys.exit(1)

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        print(f"该文件夹里没有支持的证件文件。支持：{'、'.join(sorted(SUPPORTED))}")
        return

    mode_label = "连服务器 AI 识别" if ai_mode else "规则路径，不花钱"
    print(f"\n共 {len(files)} 份文件，开始试跑识别（{mode_label}）：\n" + "=" * 60)
    if ai_mode:
        run_ai(files)
    else:
        run_rule(files)


if __name__ == "__main__":
    main()
