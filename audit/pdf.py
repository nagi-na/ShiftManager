"""監査ログを A4縦 の PDF に出力する（ReportLab）。

日本語は内蔵 CID フォント ``HeiseiKakuGo-W5`` を使用（フォント同梱不要）。
列: 日時 / 操作者 / 操作 / 内容。件数が多ければ自動で改ページし、
見出し行を各ページで繰り返す。
"""

from io import BytesIO

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_NAME = "HeiseiKakuGo-W5"

_font_registered = False


def _ensure_font():
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
        _font_registered = True


def build_audit_pdf(logs, generated_at):
    """logs: AuditLog のイテラブル（新しい順）。bytes を返す。"""
    _ensure_font()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title="操作ログ",
    )

    title_style = ParagraphStyle("title", fontName=FONT_NAME, fontSize=14, leading=18, spaceAfter=2)
    meta_style = ParagraphStyle("meta", fontName=FONT_NAME, fontSize=8.5, leading=12,
                                textColor=colors.HexColor("#444444"))
    head_style = ParagraphStyle("head", fontName=FONT_NAME, fontSize=8, leading=10, alignment=1)
    cell_style = ParagraphStyle("cell", fontName=FONT_NAME, fontSize=7.5, leading=10)

    elements = [
        Paragraph("操作ログ", title_style),
        Paragraph(
            f"出力日時 {generated_at:%Y/%m/%d %H:%M}　／　件数 {len(logs)} 件",
            meta_style,
        ),
        Spacer(1, 4 * mm),
    ]

    header = [Paragraph(h, head_style) for h in ("日時", "操作者", "操作", "内容")]
    data = [header]
    for log in logs:
        when = timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M")
        detail = log.summary
        if log.target:
            detail = f"{detail}（{log.target}）"
        data.append([
            Paragraph(when, cell_style),
            Paragraph(log.actor_label or "—", cell_style),
            Paragraph(log.get_action_display(), cell_style),
            Paragraph(detail, cell_style),
        ])

    col_widths = [26 * mm, 28 * mm, 34 * mm, doc.width - 88 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bdbdbd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECECEC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)

    if not logs:
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph("該当するログはありません。", cell_style))

    doc.build(elements)
    return buf.getvalue()
