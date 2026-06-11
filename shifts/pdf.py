"""提出状況一覧を A4横 の PDF に出力する。

ReportLab(Platypus) を使用。日本語は ReportLab 内蔵の CID フォント
``HeiseiKakuGo-W5`` を登録して描画するため、フォントファイルの同梱は不要。

レイアウト方針:
  行 = クルー / 列 = 各日（n/j＋曜日）。
  出勤可は「開始▲終了」（2段）、出勤不可は「×」、未入力は空欄。
  未提出のクルーは行を網掛けにして区別する（色に頼らずグレー）。
列幅はフレーム幅ぴったりに割り付けるので、日数が多くても横にはみ出さない
（縦に長い場合は自動で改ページし、見出し行を各ページで繰り返す）。
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_NAME = "HeiseiKakuGo-W5"  # ReportLab 内蔵の日本語ゴシック（外部ファイル不要）
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]

_font_registered = False


def _ensure_font():
    """日本語フォントを一度だけ登録する。"""
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
        _font_registered = True


def _cell_text(day):
    """各日セルの表示文字列。day は ShiftRequestDay または None。"""
    if day is None:
        return ""  # その日に入力なし
    if not day.is_available:
        return "×"
    if day.start_time and day.end_time:
        return f"{day.start_time}<br/>｜<br/>{day.end_time}"
    return "○"  # 出勤可だが時刻未設定


def build_status_pdf(period, dates, rows, submitted_count, total_count, generated_at):
    """提出状況の PDF を生成し bytes を返す。

    rows: [{"name": str, "submitted": bool, "note": str,
            "cells": [ShiftRequestDay|None, ...(dates と同順)]}]
    """
    _ensure_font()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="提出状況一覧",
    )

    # 列数に応じてセル文字を小さくして詰まりを防ぐ
    n_dates = len(dates)
    cell_fs = 7 if n_dates <= 16 else (6 if n_dates <= 24 else 5)

    title_style = ParagraphStyle(
        "title", fontName=FONT_NAME, fontSize=14, leading=18, spaceAfter=2
    )
    meta_style = ParagraphStyle(
        "meta", fontName=FONT_NAME, fontSize=8.5, leading=12, textColor=colors.HexColor("#444444")
    )
    head_style = ParagraphStyle(
        "head", fontName=FONT_NAME, fontSize=cell_fs, leading=cell_fs + 1, alignment=1
    )
    name_style = ParagraphStyle(
        "name", fontName=FONT_NAME, fontSize=cell_fs + 0.5, leading=cell_fs + 2
    )
    cell_style = ParagraphStyle(
        "cell", fontName=FONT_NAME, fontSize=cell_fs, leading=cell_fs + 1, alignment=1
    )
    legend_style = ParagraphStyle(
        "legend", fontName=FONT_NAME, fontSize=8, leading=11, textColor=colors.HexColor("#555555")
    )

    # ---- 見出し・メタ情報 ----
    elements = [
        Paragraph(str(period), title_style),
        Paragraph(
            f"{period.start_date} 〜 {period.end_date}　／　"
            f"締切 {period.deadline:%Y/%m/%d %H:%M}　／　"
            f"提出 {submitted_count} / {total_count} 名　／　"
            f"出力 {generated_at:%Y/%m/%d %H:%M}",
            meta_style,
        ),
        Spacer(1, 4 * mm),
    ]

    # ---- 表データ ----
    header = [Paragraph("クルー", head_style)]
    for dt in dates:
        header.append(
            Paragraph(f"{dt.month}/{dt.day}<br/>{WEEKDAYS_JP[dt.weekday()]}", head_style)
        )
    header.append(Paragraph("備考", head_style))

    data = [header]
    unsubmitted_row_idx = []
    for i, row in enumerate(rows, start=1):  # 0 は見出し行
        if row["submitted"]:
            name_para = Paragraph(row["name"], name_style)
            cells = [Paragraph(_cell_text(c), cell_style) for c in row["cells"]]
            note_para = Paragraph((row["note"] or "").replace("\n", "<br/>"), cell_style)
        else:
            name_para = Paragraph(f'{row["name"]}<br/><b>（未提出）</b>', name_style)
            cells = [Paragraph("", cell_style) for _ in dates]
            note_para = Paragraph("—", cell_style)
            unsubmitted_row_idx.append(i)
        data.append([name_para, *cells, note_para])

    # ---- 列幅をフレーム幅にぴったり割り付け ----
    name_w = 26 * mm
    note_w = 28 * mm
    date_w = (doc.width - name_w - note_w) / n_dates if n_dates else doc.width
    col_widths = [name_w] + [date_w] * n_dates + [note_w]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bdbdbd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECECEC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-2, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    for idx in unsubmitted_row_idx:  # 未提出行を網掛け
        style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#E0E0E0")))
    table.setStyle(TableStyle(style))
    elements.append(table)

    elements.append(Spacer(1, 3 * mm))
    elements.append(
        Paragraph("× = 出勤不可　／　空欄 = 入力なし　／　網掛け = 未提出", legend_style)
    )

    doc.build(elements)
    return buf.getvalue()
