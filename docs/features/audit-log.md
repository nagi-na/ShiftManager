# 操作ログ（監査ログ）

## 1. 目的・背景

「**誰が・いつ・何をしたか**」を記録し、システム管理者が後から確認できるようにする。トラブル時の原因追跡、不正・誤操作の抑止、運用の透明性のため。ログ機能は特定アプリに属さず横断的なので、**専用の `audit` アプリ**に分離する。

## 2. 仕様

- **閲覧権限**: システム管理者（admin）のみ（`admin_required` / `can_manage_accounts`）。リーダー・クルーは不可。
- **記録対象**: 主要操作すべて（ログイン/ログアウト＋データを変える操作）。一覧は §4。
- **記録項目**: 操作者（＋削除後も残る名前スナップショット）、操作の種類、内容、対象、IPアドレス、日時。
- **検索**: 操作の種類（プルダウン）／操作者（プルダウン）／日付範囲（開始日・終了日）。一覧は50件ページング。
- **出力**: 現在の検索条件のまま **PDF（A4縦・印刷/保存用）** と **CSV（Excel用にBOM付き）** をダウンロード。
- **保持件数**: **5000件**で頭打ち。記録のたびに件数を確認し、超えたら新しい順に5000件を残して古いものを自動削除（cron不要）。

### 2-1. IPアドレスの取得
リバースプロキシ（Nginx/Cloudflare）越しでも実IPを残せるよう、`X-Forwarded-For` の先頭→なければ `REMOTE_ADDR`。

## 3. データモデルの変更

- **新規モデル `audit.AuditLog`**（マイグレーション**あり** → 本番で `migrate` 必須）。
  - `actor`（FK, SET_NULL）／ `actor_label`（名前のスナップショット）／ `action`（choices, index）／ `summary` ／ `target` ／ `ip_address` ／ `created_at`（index, ordering=-created_at）。
  - クラス定数 `MAX_ROWS = 5000`。

## 4. 実装メモ

| ファイル | 役割 |
| --- | --- |
| `audit/models.py` | `AuditLog` ＋ `Action`（24種の操作種別） |
| `audit/utils.py` | `log_action(request, action, summary, target="")` / `record(...)` / `_prune()`（5000件維持） / `client_ip()` |
| `audit/signals.py` | `user_logged_in` / `user_logged_out` を受けて記録 |
| `audit/apps.py` | `ready()` で `signals` を import（受信登録） |
| `audit/views.py` | `audit_log_list`（検索＋ページング）/ `audit_log_pdf` / `audit_log_csv`。すべて `@admin_required`、`_filtered_logs()` を共用 |
| `audit/pdf.py` | `build_audit_pdf(logs, generated_at)`（ReportLab・A4縦・日本語内蔵フォント） |
| `audit/urls.py` | `manage/logs/`・`manage/logs/pdf/`・`manage/logs/csv/` |
| `audit/templates/audit/log_list.html` | 検索フォーム＋表＋出力ボタン＋ページング |
| `audit/admin.py` | 予備の閲覧用（追加/変更不可の read-only） |
| `settings.py` / `shift_manager/urls.py` | `audit` を INSTALLED_APPS と URL に追加 |
| `shifts/templates/shifts/manage_top.html` | admin限定の「操作ログ」カード |

### 記録の差し込み箇所（`log_action` 呼び出し）
成功処理の直後（`form.is_valid()` 通過後・`redirect` 前）に1行ずつ追加。

| ファイル | 操作 → action |
| --- | --- |
| `accounts/views.py` | 作成→`ACCOUNT_CREATE` / 編集→`ACCOUNT_EDIT` / 削除→`ACCOUNT_DELETE` / PW再発行→`ACCOUNT_RESET_PW` / 有効無効→`ACCOUNT_TOGGLE_ACTIVE` / 固定編集許可（個別・一括）→`ACCOUNT_TOGGLE_FIXED` |
| `shifts/views.py` | シフト提出→`SHIFT_SUBMIT` / 期間 作成→`PERIOD_CREATE`・編集→`PERIOD_EDIT`・締切再開→`PERIOD_CLOSE`・表示切替→`PERIOD_VISIBILITY`・削除→`PERIOD_DELETE` / 確定 アップロード→`CONFIRMED_UPLOAD`・削除→`CONFIRMED_DELETE` / アナウンス 投稿→`ANNOUNCE_CREATE`・編集→`ANNOUNCE_EDIT`・削除→`ANNOUNCE_DELETE`・設定→`ANNOUNCE_SETTINGS`・確定公開告知→`ANNOUNCE_CREATE` / 固定シフト 編集（本人/代理）→`FIXED_EDIT`・申請→`FIXED_REQUEST`・取消→`FIXED_REQUEST_CANCEL`・承認却下→`FIXED_REQUEST_REVIEW` |
| `audit/signals.py` | ログイン→`LOGIN` / ログアウト→`LOGOUT` |

### 依存の向き（循環回避）
`audit` は `accounts`/`shifts` を import しない（一方向）。各ビューが `from audit.utils import log_action` を import する。

## 5. アップデート手順（本番反映）

**新しいテーブルが増える**ので `migrate` が必須。reportlabは導入済み（PDF機能）で新依存なし・静的追加なし。

```bash
# ① 開発側でコミット＆push
git add audit/ accounts/views.py shifts/views.py shift_manager/ \
        shifts/templates/shifts/manage_top.html
git commit -m "feat(audit): 操作ログ（誰が何時に何をしたか）の記録・検索・PDF/CSV出力を追加"
git push origin main

# ② 本番(Docker)マシンで
git pull
docker compose up -d --build
docker compose run --rm web python manage.py migrate
```

> systemd（非Docker）構成なら `pip install -r requirements.txt`（不要だが念のため）→ `migrate` → サービス再起動。

## 6. 確認項目

- adminだけが管理メニューに「操作ログ」カードを見られる（リーダー/クルーには出ない）。
- 各操作後にログが増える。ログインで `LOGIN` が残る。
- 種類/操作者/日付範囲で絞れる。PDF・CSVが絞り込み結果のまま落ちる（CSVはExcelで文字化けしない）。
- リーダー/クルーで `…/manage/logs/`（pdf/csv）を直叩きするとリダイレクト。
- 5000件を超えると古いものから消える。
- `python manage.py test audit` が通る。
