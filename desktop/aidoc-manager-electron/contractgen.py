"""基于库存合同 PDF 生成新合同 PDF。

原则：只替换乙方、乙方收款资料和商品明细，原合同其余条款取自模板文字层，
不让大模型重写条款，避免“口头说保持不变，实际却新增/删改内容”。
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import fitz


def _font_path() -> Path | None:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/Deng.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return path
    # PyMuPDF 自带简体中文基础字体，保证换到没有中文字体的新电脑仍能生成 PDF。
    return None


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cn_upper_money(value: Decimal) -> str:
    """人民币金额转大写，覆盖合同常见的亿元以内金额。"""
    if value < 0:
        raise ValueError("金额不能为负数")
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    fen_total = int(value * 100)
    if fen_total == 0:
        return "零元整"
    digits = "零壹贰叁肆伍陆柒捌玖"
    units = ["分", "角", "元", "拾", "佰", "仟", "万", "拾", "佰", "仟", "亿"]
    result: list[str] = []
    zero_pending = False
    for index in range(len(units)):
        digit = (fen_total // (10 ** index)) % 10
        unit = units[index]
        if digit:
            if zero_pending and result and not result[-1].startswith("零"):
                result.append("零")
            result.append(digits[digit] + unit)
            zero_pending = False
        else:
            if unit in {"元", "万", "亿"}:
                if unit == "元" and (not result or not any(x.endswith("元") for x in result)):
                    result.append("元")
                elif unit in {"万", "亿"} and fen_total >= 10 ** index:
                    result.append(unit)
                zero_pending = False
            elif result:
                zero_pending = True
    text = "".join(reversed(result))
    text = re.sub(r"零+", "零", text)
    text = text.replace("零万", "万").replace("零亿", "亿").replace("亿万", "亿零")
    if fen_total % 100 == 0:
        text += "整"
    elif fen_total % 10 == 0:
        text = text.replace("零分", "")
    return text


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, re.M)
    if not match:
        raise RuntimeError(f"模板合同缺少{label}，无法可靠生成新合同。")
    return match.group(1).strip()


def _support_value(texts: list[str], labels: list[str]) -> str:
    for text in texts:
        for label in labels:
            # 标签必须独占一行或后接冒号，防止把“银行账户测试资料”误读成账号。
            inline = re.search(rf"^\s*{re.escape(label)}\s*[:：]\s*([^\n\r]+)$", text, re.M)
            following = re.search(rf"^\s*{re.escape(label)}\s*$\s*\n\s*([^\n\r]+)$", text, re.M)
            match = inline or following
            if match:
                value = match.group(1).strip(" ：:")
                if value:
                    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()
    return ""


def _clause_blocks(text: str) -> list[str]:
    """把 PDF 视觉换行合并回逻辑段落，文字本身不做改写。"""
    starts = re.compile(
        r"^(?:\d+(?:\.\d+)?\s*|（\d+）|收款单位|开户银行|银行账号|"
        r"甲方（盖章）|法定代表人|或授权代表|日期|附件)"
    )
    blocks: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        previous_is_heading = bool(blocks and re.match(r"^\d+\.(?!\d)", blocks[-1]))
        if not blocks or starts.match(line) or previous_is_heading:
            blocks.append(line)
        else:
            blocks[-1] += line
    return blocks


class _PdfWriter:
    def __init__(self, output: Path):
        self.output = output
        self.doc = fitz.open()
        self.page_width, self.page_height = fitz.paper_size("a4")
        self.left = 42.0
        self.right = 42.0
        self.top = 38.0
        self.bottom = 40.0
        self.font_path = _font_path()
        self.measure_font = fitz.Font(fontfile=str(self.font_path)) if self.font_path else fitz.Font(fontname="china-s")
        self.font_name = "contractfont" if self.font_path else "china-s"
        self.page: fitz.Page | None = None
        self.y = self.top
        self.new_page()

    @property
    def usable_width(self) -> float:
        return self.page_width - self.left - self.right

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=self.page_width, height=self.page_height)
        if self.font_path:
            self.page.insert_font(fontname=self.font_name, fontfile=str(self.font_path))
        self.page.draw_rect(
            fitz.Rect(28, 28, self.page_width - 28, self.page_height - 28),
            color=(0.88, 0.9, 0.89), width=0.6,
        )
        self.y = self.top

    def ensure(self, height: float) -> None:
        if self.y + height > self.page_height - self.bottom:
            self.new_page()

    def _wrap(self, text: str, width: float, size: float) -> list[str]:
        if not text:
            return [""]
        lines: list[str] = []
        current = ""
        for char in text:
            trial = current + char
            if current and self.measure_font.text_length(trial, fontsize=size) > width:
                lines.append(current)
                current = char
            else:
                current = trial
        if current or not lines:
            lines.append(current)
        return lines

    def text(self, text: str, size: float = 9.5, gap: float = 3.0, indent: float = 0,
             color: tuple[float, float, float] = (0.08, 0.11, 0.1)) -> None:
        line_height = size * 1.55
        lines = self._wrap(text, self.usable_width - indent, size)
        self.ensure(len(lines) * line_height + gap)
        for line in lines:
            assert self.page is not None
            self.page.insert_text(
                (self.left + indent, self.y + size), line,
                fontname=self.font_name, fontfile=str(self.font_path) if self.font_path else None, fontsize=size, color=color,
            )
            self.y += line_height
        self.y += gap

    def title(self, text: str) -> None:
        size = 18.0
        width = self.measure_font.text_length(text, fontsize=size)
        assert self.page is not None
        self.page.insert_text(
            ((self.page_width - width) / 2, self.y + size), text,
            fontname=self.font_name, fontfile=str(self.font_path) if self.font_path else None, fontsize=size, color=(0.05, 0.12, 0.17),
        )
        self.y += 33

    def right_text(self, text: str, size: float = 9.0) -> None:
        width = self.measure_font.text_length(text, fontsize=size)
        assert self.page is not None
        self.page.insert_text(
            (self.page_width - self.right - width, self.y + size), text,
            fontname=self.font_name, fontfile=str(self.font_path) if self.font_path else None, fontsize=size,
        )
        self.y += size * 1.7

    def heading(self, text: str) -> None:
        self.ensure(28)
        self.y += 4
        self.text(text, size=13.2, gap=5, color=(0.05, 0.13, 0.18))

    def table(self, items: list[dict[str, Any]]) -> None:
        widths = [142, 96, 42, 36, 48, 55, 50]
        widths[-1] += self.usable_width - sum(widths)
        headers = ["产品名称", "规格型号", "数量", "单位", "单价", "总价", "备注"]
        rows: list[list[str]] = [headers]
        for item in items:
            quantity = Decimal(str(item["quantity"]))
            price = _money(item["unit_price"])
            total = (quantity * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rows.append([
                str(item["name"]), str(item.get("specification") or ""),
                f"{quantity.normalize():f}", str(item.get("unit") or ""),
                f"{price:f}", f"{total:f}", str(item.get("remark") or ""),
            ])
        size = 8.2
        line_h = 11.5
        row_heights: list[float] = []
        wrapped: list[list[list[str]]] = []
        for row in rows:
            cells = [self._wrap(value, widths[i] - 8, size) for i, value in enumerate(row)]
            wrapped.append(cells)
            row_heights.append(max(25, max(len(lines) for lines in cells) * line_h + 8))
        self.ensure(sum(row_heights) + 5)
        assert self.page is not None
        y = self.y
        for row_index, cells in enumerate(wrapped):
            height = row_heights[row_index]
            x = self.left
            fill = (0.94, 0.96, 0.95) if row_index == 0 else None
            for col_index, lines in enumerate(cells):
                rect = fitz.Rect(x, y, x + widths[col_index], y + height)
                self.page.draw_rect(rect, color=(0.2, 0.24, 0.22), fill=fill, width=0.55)
                text_y = y + (height - len(lines) * line_h) / 2 + size
                for line in lines:
                    text_w = self.measure_font.text_length(line, fontsize=size)
                    text_x = x + max(4, (widths[col_index] - text_w) / 2)
                    self.page.insert_text(
                        (text_x, text_y), line, fontname=self.font_name,
                        fontfile=str(self.font_path) if self.font_path else None, fontsize=size,
                    )
                    text_y += line_h
                x += widths[col_index]
            y += height
        self.y = y + 7

    def signature(self, buyer: str, supplier: str) -> None:
        self.ensure(120)
        self.y += 10
        assert self.page is not None
        columns = [
            (self.left, f"甲方（盖章）：{buyer}"),
            (self.left + self.usable_width / 2 + 8, f"乙方（盖章）：{supplier}"),
        ]
        size = 9.3
        line_h = 22
        for x, first_line in columns:
            for index, line in enumerate([first_line, "法定代表人：", "或授权代表：", "日期："]):
                self.page.insert_text(
                    (x, self.y + size + index * line_h), line,
                    fontname=self.font_name, fontfile=str(self.font_path) if self.font_path else None, fontsize=size,
                )
        self.y += line_h * 4 + 10
        self.text("附件：", size=9.3, gap=0)

    def save(self, metadata: dict[str, str]) -> None:
        self.doc.set_metadata(metadata)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        # Some Windows/Python combinations cannot pass a Unicode path to
        # PyMuPDF. Build the PDF in memory, then let pathlib write the bytes.
        try:
            payload = self.doc.tobytes(garbage=4, deflate=True)
        finally:
            self.doc.close()
        self.output.write_bytes(payload)


def generate_contract_pdf(
    template_text: str,
    output_path: Path,
    supplier_name: str,
    support_texts: list[str],
    line_items: list[dict[str, Any]],
    delivery_address: str = "",
    delivery_deadline: str = "",
    payment_terms: str = "",
) -> dict[str, Any]:
    """生成新合同并返回关键信息。只改用户明确指定的字段，其余模板条款保持原文。"""
    text = template_text.replace("\u2f8f", "行")
    contract_no = _extract(r"合同编号\s*[:：]\s*([^\n\r]+)", text, "合同编号")
    buyer = _extract(r"买方\s*[:：]\s*(.*?)\s*（以下简称", text, "买方")
    old_supplier = _extract(r"卖方\s*[:：]\s*(.*?)\s*（以下简称", text, "卖方")
    intro_match = re.search(r"卖方[^\n\r]+\n(.*?)\n\s*1\.标的物", text, re.S)
    intro = re.sub(r"\s+", "", intro_match.group(1)) if intro_match else (
        "根据《中华人民共和国民法典》及相关法律、法规的规定，本着平等、互利、公平、公正的原则，"
        "双方就物资采购事宜协商一致，自愿签订本合同。"
    )
    clause_index = text.find("1.1交付地点")
    if clause_index < 0:
        raise RuntimeError("模板合同未找到第 1.1 条，无法保证其它条款保持不变。")
    clauses = text[clause_index:].replace(old_supplier, supplier_name)

    delivery_address = str(delivery_address or "").strip()[:300]
    delivery_deadline = str(delivery_deadline or "").strip()[:300]
    payment_terms = str(payment_terms or "").strip()[:500]
    if delivery_address:
        clauses, count = re.subn(
            r"(?ms)^\s*1\.1交付地点\s*[:：].*?(?=^\s*1\.2)",
            f"1.1交付地点：{delivery_address}\n",
            clauses,
            count=1,
        )
        if count != 1:
            raise RuntimeError("模板未找到可替换的交付地点条款，已停止生成。")
    if delivery_deadline:
        clauses, count = re.subn(
            r"(?ms)^\s*1\.2交货时间\s*[:：].*?(?=^\s*1\.3)",
            f"1.2交货时间：{delivery_deadline}\n",
            clauses,
            count=1,
        )
        if count != 1:
            raise RuntimeError("模板未找到可替换的交货时间条款，已停止生成。")
    if payment_terms:
        clauses, count = re.subn(
            r"(?ms)^\s*2\.2付款时间\s*[:：].*?(?=^\s*2\.3)",
            f"2.2付款时间：{payment_terms}\n",
            clauses,
            count=1,
        )
        if count != 1:
            raise RuntimeError("模板未找到可替换的付款时间条款，已停止生成。")

    support_joined = "\n".join(support_texts)
    if support_joined and supplier_name not in support_joined:
        raise RuntimeError("选择的供应商资料与新乙方名称不一致，请重新确认。")
    bank_name = _support_value(support_texts, ["开户银行", "开户行"])
    bank_account = _support_value(support_texts, ["银行账号", "银行账户", "账号"])
    if supplier_name != old_supplier and (not bank_name or not bank_account):
        raise RuntimeError("未能从供应商开户/税务资料中读取开户银行和银行账号，已停止生成，避免写入错误财务信息。")
    if bank_name:
        clauses = re.sub(r"开户银行\s*[:：]\s*[^\n\r]+", f"开户银行：{bank_name}", clauses)
    if bank_account:
        clauses = re.sub(r"银行账号\s*[:：]\s*[^\n\r]+", f"银行账号：{bank_account}", clauses)
    clauses = re.sub(r"收款单位\s*[:：]\s*[^\n\r]+", f"收款单位：{supplier_name}", clauses)
    signature_index = clauses.find("甲方（盖章）")
    if signature_index >= 0:
        clauses = clauses[:signature_index].rstrip()

    normalized_items: list[dict[str, Any]] = []
    total_amount = Decimal("0")
    for raw in line_items[:30]:
        quantity = Decimal(str(raw.get("quantity") or 0))
        price = _money(raw.get("unit_price"))
        if not str(raw.get("name") or "").strip() or quantity <= 0 or price < 0:
            continue
        total_amount += quantity * price
        normalized_items.append({
            "name": str(raw.get("name") or "").strip()[:200],
            "specification": str(raw.get("specification") or "").strip()[:200],
            "quantity": quantity,
            "unit": str(raw.get("unit") or "").strip()[:20],
            "unit_price": price,
            "remark": str(raw.get("remark") or "").strip()[:200],
        })
    total_amount = total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not normalized_items:
        raise RuntimeError("新合同缺少有效商品明细，无法生成。")

    note_match = re.search(r"备注\s*[:：][^\n\r]+", text)
    note = note_match.group(0).strip() if note_match else "备注：价格含税，发票及交付要求沿用原合同约定。"
    if payment_terms:
        note = re.sub(
            r"乙方发票交付时间\s*[:：]\s*[^\n\r]+",
            "乙方应在付款前提供合法有效发票。",
            note,
        )

    writer = _PdfWriter(output_path)
    writer.title("产品购销合同")
    writer.right_text(f"合同编号：{contract_no}")
    writer.text(f"买方：{buyer}（以下简称“甲方”）", size=10.2, gap=2)
    writer.text(f"卖方：{supplier_name}（以下简称“乙方”）", size=10.2, gap=5)
    writer.text(intro, size=9.6, gap=8, indent=18)
    writer.heading("1.标的物名称、数量、价格、型号等")
    writer.table(normalized_items)
    writer.text(note, size=9.2, gap=3)
    writer.text(
        f"合 计（大写）{_cn_upper_money(total_amount)}（￥{total_amount:f} 元）",
        size=10.0, gap=7,
    )

    for block in _clause_blocks(clauses):
        if re.match(r"^\d+\.(?!\d)", block):
            writer.heading(block)
        else:
            writer.text(block, size=9.1, gap=2.5)
    writer.signature(buyer, supplier_name)
    writer.save({
        "title": output_path.stem,
        "subject": "由 AI 档案秘书基于库存合同模板生成",
        "author": "好办法 AI 档案管理",
        "keywords": "合同,档案,采购",
    })
    # 生成后再从 PDF 文字层回读核对，防止模型回复说“已修改”但文件仍保留旧值。
    verify_doc = fitz.open(str(output_path))
    try:
        rendered_text = "\n".join(page.get_text() for page in verify_doc)
    finally:
        verify_doc.close()
    compact_rendered = re.sub(r"\s+", "", rendered_text)
    expected_values = {
        "交付地点": delivery_address,
        "交货时间": delivery_deadline,
        "付款条件": payment_terms,
    }
    verified_fields: list[str] = []
    for label, expected in expected_values.items():
        if not expected:
            continue
        if re.sub(r"\s+", "", expected) not in compact_rendered:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(f"合同生成后核对失败：{label}未正确写入，已停止交付文件。")
        verified_fields.append(label)
    return {
        "buyer": buyer,
        "supplier": supplier_name,
        "contract_no": contract_no,
        "total_amount": f"{total_amount:f}",
        "bank_name": bank_name,
        "bank_account": bank_account,
        "item_count": len(normalized_items),
        "delivery_address": delivery_address,
        "delivery_deadline": delivery_deadline,
        "payment_terms": payment_terms,
        "verified_fields": verified_fields,
    }


def generate_text_pdf(title: str, content: str, output_path: Path) -> dict[str, Any]:
    """把 AI 已给出的完整合同/文书正文可靠落地为 PDF，不依赖 Office 或外装字体。"""
    heading = str(title or "新文书").strip()[:100]
    body = str(content or "").strip()
    if len(body) < 20:
        raise RuntimeError("文书正文过短，无法生成 PDF。")
    writer = _PdfWriter(output_path)
    writer.title(heading)
    lines = body.splitlines()
    if lines and lines[0].strip() == heading:
        lines = lines[1:]
    for raw in lines:
        line = raw.strip()
        if not line:
            writer.text("", size=9.5, gap=4)
        elif re.match(r"^(第[一二三四五六七八九十百]+[条章节]|[一二三四五六七八九十]+、|\d+[.、])", line):
            writer.heading(line)
        else:
            writer.text(line, size=10.2, gap=4, indent=18)
    writer.save({
        "title": heading,
        "subject": "由好办法 AI 档案秘书生成",
        "author": "好办法 AI 档案管理",
        "keywords": "合同,文书,档案",
    })
    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise RuntimeError("PDF 文件生成失败。")
    check = fitz.open(str(output_path))
    try:
        page_count = len(check)
    finally:
        check.close()
    return {"page_count": page_count, "font": "system" if _font_path() else "builtin-china-s"}
