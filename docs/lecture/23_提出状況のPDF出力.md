# 23章 提出状況のA4 PDF出力（ReportLabで帳票を作る）

> 発展編（付録）。**6章（提出状況一覧 `period_status`）** が終わっている前提です。
> 機能追加の「簡潔版」。Python は全文、テンプレートは要点を載せます。設計詳細は [`../features/status-pdf.md`](../features/status-pdf.md) を参照。

---

## 23-0. この章で作るもの

リーダーが調整・保存・印刷に使えるよう、**提出状況一覧（S4）をA4横のPDFでダウンロード**できるようにします。

- 画面右上に **［PDFで出力］** ボタン。
- 行＝クルー、列＝対象期間の各日。出勤可は「開始｜終了」、不可は `×`、未入力は空欄、**未提出は網掛け**。
- 上部に期間・締切・提出人数・出力日時、下部に凡例。
- **権限は管理権限のみ**（画面と同じ判定）。

> 🔰 集計は画面（`period_status`）と**同じクエリ**を使います。PDFは「同じデータを別の見た目で出す」だけなので、画面とPDFで内容がずれません。

---

## 23-1. ライブラリの追加（ReportLab）

PDF生成に **ReportLab** を使います。`requirements.txt` に追記してインストール。

```
# 提出状況のA4 PDF出力に使用。pip wheel のみで入りOS依存なし。
# 日本語フォント(HeiseiKakuGo-W5)を内蔵しており別途フォント同梱は不要。
reportlab>=4,<5
```

```
$ pip install -r requirements.txt
```

> 🔰 **なぜReportLabか**: pipだけで入り（OSのライブラリ追加が不要）、**日本語フォントを内蔵**しています。HTML→PDF系（WeasyPrint等）は pango/cairo などOS側の依存が必要で、Dockerイメージが重くなります。表組みの帳票なら ReportLab が手軽です。

---

## 23-2. PDF生成モジュール（`shifts/pdf.py` 新規）

描画ロジックはビューに混ぜず、**独立した純粋関数**に切り出します。テストや将来の別帳票から呼びやすくなります。全文を作成します。

```python
"""提出状況一覧を A4横 の PDF に出力する。

ReportLab(Platypus) を使用。日本語は内蔵の CID フォント
``HeiseiKakuGo-W5`` を登録して描画するため、フォントファイルの同梱は不要。
列幅はフレーム幅ぴったりに割り付けるので、日数が多くても横にはみ出さない。
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
        buf, pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title="提出状況一覧",
    )

    # 列数に応じてセル文字を小さくして詰まりを防ぐ
    n_dates = len(dates)
    cell_fs = 7 if n_dates <= 16 else (6 if n_dates <= 24 else 5)

    title_style = ParagraphStyle("title", fontName=FONT_NAME, fontSize=14, leading=18, spaceAfter=2)
    meta_style = ParagraphStyle("meta", fontName=FONT_NAME, fontSize=8.5, leading=12,
                                textColor=colors.HexColor("#444444"))
    head_style = ParagraphStyle("head", fontName=FONT_NAME, fontSize=cell_fs, leading=cell_fs + 1, alignment=1)
    name_style = ParagraphStyle("name", fontName=FONT_NAME, fontSize=cell_fs + 0.5, leading=cell_fs + 2)
    cell_style = ParagraphStyle("cell", fontName=FONT_NAME, fontSize=cell_fs, leading=cell_fs + 1, alignment=1)
    legend_style = ParagraphStyle("legend", fontName=FONT_NAME, fontSize=8, leading=11,
                                  textColor=colors.HexColor("#555555"))

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
        header.append(Paragraph(f"{dt.month}/{dt.day}<br/>{WEEKDAYS_JP[dt.weekday()]}", head_style))
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

    # ---- 列幅をフレーム幅にぴったり割り付け（日数が多くてもはみ出さない）----
    name_w = 26 * mm
    note_w = 28 * mm
    date_w = (doc.width - name_w - note_w) / n_dates if n_dates else doc.width
    col_widths = [name_w] + [date_w] * n_dates + [note_w]

    table = Table(data, colWidths=col_widths, repeatRows=1)  # 改ページ時は見出し行を繰り返す
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bdbdbd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECECEC")),  # 見出し行
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
    elements.append(Paragraph("× = 出勤不可　／　空欄 = 入力なし　／　網掛け = 未提出", legend_style))

    doc.build(elements)
    return buf.getvalue()
```

> 🔰 **Platypus（プラティパス）** は ReportLab の高水準API。`Paragraph`（段落）や `Table`（表）といった「部品（flowable）」を並べて `doc.build()` すると、自動で改ページしながら配置してくれます。`repeatRows=1` で、ページをまたいでも見出し行が各ページに出ます。
>
> 🔰 セル内の改行は `<br/>`、強調は `<b>` のように**ミニHTML**で書けます（`Paragraph` がXML風タグを解釈）。

---

## 23-3. ビュー（`shifts/views.py`）

`period_status` と**同じ集計**を行い、`build_status_pdf` に渡して `application/pdf` で返します。先頭の import に1行足します。

```python
from .pdf import build_status_pdf
```

```python
@login_required
def period_status_pdf(request, pk):
    """S4 提出状況一覧を A4横 の PDF で出力する（管理権限のみ）。"""
    if not request.user.can_manage:
        messages.error(request, "この画面は管理権限が必要です。")
        return redirect("home")

    period = get_object_or_404(ShiftPeriod, pk=pk)
    dates = _date_range(period.start_date, period.end_date)

    staff_list = User.objects.filter(
        role=User.Role.CREW, is_active=True
    ).order_by("name", "username")
    requests = {
        r.user_id: r
        for r in ShiftRequest.objects.filter(period=period).prefetch_related("days")
    }

    rows = []
    for staff in staff_list:
        req = requests.get(staff.id)
        name = staff.name or staff.username
        if req:
            days_map = {d.work_date: d for d in req.days.all()}
            rows.append({
                "name": name, "submitted": True, "note": req.note,
                "cells": [days_map.get(dt) for dt in dates],
            })
        else:
            rows.append({"name": name, "submitted": False, "note": "", "cells": [None] * len(dates)})

    submitted_count = sum(1 for r in rows if r["submitted"])
    pdf_bytes = build_status_pdf(period, dates, rows, submitted_count, len(rows), timezone.localtime())

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = f"shift-status-{period.start_date}_{period.end_date}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
```

> 🔰 `Content-Type: application/pdf` と `Content-Disposition: attachment; filename="..."` の2つで、ブラウザは「PDFを名前付きでダウンロード」と判断します。`prefetch_related("days")` で各クルーの日次データをまとめて取り、N+1クエリを防いでいます。

---

## 23-4. URL（`shifts/urls.py`）

```python
    path("periods/<int:pk>/status/pdf/", views.period_status_pdf, name="period_status_pdf"),
```

---

## 23-5. ボタンを置く（`shifts/templates/shifts/status.html`）

提出状況一覧の見出し横に［PDFで出力］を足します。

```html
<div class="d-flex justify-content-between align-items-center mb-2">
  <h1 class="h4 mb-0">提出状況一覧</h1>
  <div class="d-flex gap-2">
    <a class="btn btn-primary btn-sm" href="{% url 'period_status_pdf' period.pk %}">PDFで出力</a>
    <a class="btn btn-outline-secondary btn-sm" href="{% url 'home' %}">← ホーム</a>
  </div>
</div>
```

---

## 23-6. ✅ 動作確認

```
$ python manage.py runserver
```

1. リーダーでログイン → 管理メニュー → 期間の「提出状況を見る」→ **［PDFで出力］**。
2. A4横のPDFがDLされ、出勤可は時刻、不可は `×`、未入力は空欄、未提出は網掛け＋「（未提出）」になっている。
3. クルーのアカウントで `…/status/pdf/` を直接開くと、ホームへリダイレクトされる。
4. 期間を1か月など長くしても、列が用紙からはみ出さない。

### テスト（`shifts/tests.py`）

```python
class StatusPdfTests(TestCase):
    """提出状況のA4 PDF出力（period_status_pdf）の権限と中身を検証。"""

    def setUp(self):
        self.leader = User.objects.create_user("leader", password="x")
        self.leader.role = User.Role.LEADER
        self.leader.save()
        self.crew = User.objects.create_user("crew", password="x")  # 既定 crew
        today = timezone.localdate()
        self.period = make_period(
            self.leader, timezone.now() + timedelta(days=1),
            start=today, end=today + timedelta(days=6),
        )
        req = ShiftRequest.objects.create(period=self.period, user=self.crew)
        ShiftRequestDay.objects.create(
            request=req, work_date=today, is_available=True,
            start_time="09:00", end_time="17:00",
        )
        self.url = reverse("period_status_pdf", args=[self.period.pk])

    def test_manager_gets_pdf(self):
        self.client.force_login(self.leader)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF-"))

    def test_crew_is_blocked(self):
        self.client.force_login(self.crew)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)  # ホームへリダイレクト
```

```
$ python manage.py test shifts.tests.StatusPdfTests
```

---

## つまずきポイント

- **日本語が□（豆腐）になる**: `pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))` を呼び、各 `ParagraphStyle` と `TableStyle` の `fontName` をそのフォントにしているか確認。
- **表が用紙からはみ出す**: 列幅を固定値で足すとオーバーします。本章のように **`doc.width` を日数で割って割り付け**ると常に収まります。
- **本番（Docker）で `ModuleNotFoundError: reportlab`**: `requirements.txt` に追記後、**イメージを再ビルド**（`docker compose up -d --build`）。reportlab は新しい依存なので、`git pull` だけでは入りません（モデル変更はないので `migrate` は不要）。
- **0件でエラー**: クルーが1人もいない/期間が0日のケース。本章のコードは空でも見出し＋空表を出すだけで落ちません。

> これで講義は、UIテーマ（22章）と帳票出力（23章）まで含めて現行アプリをカバーします。
