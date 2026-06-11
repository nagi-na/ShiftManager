# 提出状況のA4 PDF出力

## 1. 目的・背景

リーダーがシフトを調整する際、提出状況一覧（S4）を**紙に印刷して書き込みたい**、あるいは**手元に保存・配布したい**ことがある。ブラウザの印刷では表が崩れやすく余白も整わないため、サーバー側で**A4横の整ったPDF**を生成してダウンロードできるようにする。

## 2. 仕様

- 「提出状況一覧（S4）」画面の右上に **［PDFで出力］** ボタンを置く。
- 押すと、その対象期間の提出状況を **A4横1枚以上のPDF**としてダウンロードする（`attachment`）。
- **権限**: 管理権限（リーダー/管理者）のみ。クルーがURLを直叩きしてもホームへリダイレクト（画面と同じ判定 `request.user.can_manage`）。
- **レイアウト**: 行＝クルー（氏名・五十音/ユーザー名順）、列＝対象期間の各日（`n/j` ＋曜日）。
  - 出勤可 → 「開始｜終了」（2段表示）。
  - 出勤不可 → `×`。
  - 入力なし（その日に行なし）→ 空欄。
  - **未提出のクルー** → 行を**網掛け**にし、氏名欄に「（未提出）」。
  - 末尾に **備考**列（`ShiftRequest.note`）。
- **上部**に期間タイトル・期間（開始〜終了）・締切・提出人数（`提出 x / y 名`）・出力日時。**下部**に凡例（`× = 出勤不可 ／ 空欄 = 入力なし ／ 網掛け = 未提出`）。
- **日数が多い期間でも横にはみ出さない**: 列幅をページ幅ぴったりに割り付け、日数に応じてセル文字サイズを自動縮小（16日以下=7pt / 24日以下=6pt / それ以上=5pt）。縦に長い場合は自動改ページし、見出し行を各ページで繰り返す。
- **日本語**: ReportLab 内蔵の CID フォント `HeiseiKakuGo-W5` を使う（フォントファイルの同梱は不要）。

> 集計ロジックは画面（`period_status`）とまったく同じ（同じクエリ・同じ並び）。PDFは「同じデータを別の見た目で出す」だけなので、画面とPDFで内容がずれない。

## 3. データモデルの変更

**なし**。既存の `ShiftPeriod` / `ShiftRequest` / `ShiftRequestDay` を読むだけ。マイグレーション不要。

## 4. 実装メモ

| ファイル | 変更 |
| --- | --- |
| `requirements.txt` | `reportlab>=4,<5` を追加（**新規依存**。pip wheelのみ・OS依存なし・日本語フォント内蔵） |
| `shifts/pdf.py` | **新規**。`build_status_pdf(period, dates, rows, submitted_count, total_count, generated_at) -> bytes`。ReportLab(Platypus)で描画 |
| `shifts/views.py` | `period_status_pdf(request, pk)` を追加（`period_status` と同じ集計→`build_status_pdf`→`HttpResponse(content_type="application/pdf")`） |
| `shifts/urls.py` | `periods/<int:pk>/status/pdf/`（name=`period_status_pdf`） |
| `shifts/templates/shifts/status.html` | 見出し横に［PDFで出力］ボタン |
| `shifts/tests.py` | `StatusPdfTests`（リーダーは200/`application/pdf`、クルーはリダイレクト） |

### PDF生成を別モジュール（`shifts/pdf.py`）に分けた理由
ビューは「リクエスト→集計→レスポンス」に集中させ、**描画ロジック（フォント登録・テーブル組み立て・列幅計算）は再利用可能な純粋関数**に切り出す。テストや将来の別帳票（確定シフトの台紙など）から呼びやすくなる。

## 5. アップデート手順（本番反映）

**新しい依存（reportlab）が増えた**ので、Dockerはイメージの**再ビルド**が必要。モデル変更・静的ファイル追加はないので `migrate` と `collectstatic` は不要。

```bash
# ① 開発側でコミット＆push
git add requirements.txt shifts/pdf.py shifts/views.py shifts/urls.py \
        shifts/templates/shifts/status.html shifts/tests.py
git commit -m "feat(shifts): 提出状況をA4 PDFで出力する機能を追加"
git push origin main

# ② 本番(Docker)マシンで
git pull
docker compose up -d --build     # reportlab を含めて再ビルド
```

> systemd（非Docker）構成の場合は `pip install -r requirements.txt` → サービス再起動（13章参照）。

## 6. 確認項目

- 管理メニュー → 期間の「提出状況を見る」→ ［PDFで出力］でPDFがDLされる。
- 出勤可は時刻、不可は`×`、未入力は空欄、未提出は網掛け＋「（未提出）」。
- クルーのアカウントで `…/status/pdf/` を開くとホームへリダイレクトされる。
- 期間を長く（1か月など）しても列が用紙からはみ出さない。
- `python manage.py test shifts.tests.StatusPdfTests` が通る。
