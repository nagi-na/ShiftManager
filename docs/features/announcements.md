# お知らせ機能（手動投稿＋自動投稿＋未読管理）

## 1. 目的・背景

確定シフトの公開や新しい期間の追加を、クルーに**まとめて周知**したい。
手動のお知らせ（画像・PDF添付可）に加え、よくある通知は**自動投稿**し、クルーには**未読バッジ**で気づいてもらう。

## 2. 仕様

### 2-1. お知らせの種別
| 種別 | 投稿のされ方 |
| --- | --- |
| お知らせ（manual） | リーダー/管理者が手動投稿（タイトル・本文・添付） |
| 確定シフト（confirmed） | 各期間の「確定シフト」ページの**「お知らせを投稿」ボタン**を押したとき |
| 期間追加（period） | 対象期間を追加（表示ON）したとき自動 |

### 2-2. クルー側
- ホームに「お知らせ」ボタン＋**未読件数バッジ**。
- お知らせ一覧を**開いた時点で既読**になり、バッジが消える（クルーごとに既読を記録）。
- 添付は画像はインライン表示、それ以外（PDF等）はダウンロードリンク。**ログイン必須の認証付き配信**（確定シフトと同じ X-Accel-Redirect 方式）。

### 2-3. リーダー/管理者側
- 「お知らせ管理」：タイトル・本文・**添付（画像/PDFを複数・各10MBまで）**で投稿、一覧、削除。
- 「確定シフト」ページに**「お知らせを投稿」ボタン**（押すたびに確定シフト公開のお知らせを投稿）。
- 「自動投稿の設定」：**期間追加のオンオフ**（確定シフトはボタン投稿のため設定なし）。
- 権限は `@manager_required`（リーダー・管理者）。

## 3. データモデル（`shifts/models.py`）
- `Announcement`（title / body / category / related_period / created_by / created_at）
- `AnnouncementAttachment`（announcement / file / original_name、`is_image` プロパティ）
- `AnnouncementRead`（announcement / user / read_at、`unique(announcement, user)`）
- `AnnouncementSettings`（シングルトン：auto_on_period、`load()`）

## 4. 実装メモ（変更ファイル）
- `shifts/models.py` … 上記4モデル。
- `shifts/forms.py` … `AnnouncementForm`（title/body）、`AnnouncementSettingsForm`。添付はビューで `request.FILES.getlist("files")` を処理。
- `shifts/views.py`
  - クルー：`announcements`（一覧＋既読化）、`announcement_attachment`（認証付き配信）、`home` に未読数。
  - 管理：`manage_announcements`（投稿＋一覧＋削除入口）、`manage_announcement_delete`、`manage_announcement_settings`。
  - 自動：`_auto_announce()` ヘルパー。`manage_periods` 作成時に呼ぶ（期間追加のみ）。確定シフトは `confirmed_shift` の `announce` POST で投稿。
- テンプレート：`announcements.html`、`manage_announcements.html`、`manage_announcement_settings.html`、`home.html`（お知らせボタン＋バッジ）、`manage_top.html`（お知らせ管理カード）。
- `shifts/admin.py` … `Announcement`（添付インライン）・`AnnouncementSettings` を登録。
- 添付の配信は既存の nginx `/protected/`（internal, mediaルート）をそのまま利用（nginx設定の追加変更は不要）。

## 5. アップデート手順（本番反映）

新テーブル追加のみ（既存データ保持）。定期実行は不要。

```bash
# 反映（systemd 例）
mysqldump -u shift -p shift_manager > backup_$(date +%F).sql
git pull
./venv/bin/python manage.py migrate
DJANGO_DEBUG=0 ./venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart shiftmanager
```

## 6. 確認項目
- [ ] リーダーは画像/PDFを複数添付してお知らせを投稿でき、クルーは一覧で閲覧できる（画像はインライン）。
- [ ] クルーに未読バッジが出て、一覧を開くと消える（クルーごとに既読）。
- [ ] 添付は未ログインだと開けず（login へ）、ログイン時は認証付きで配信される。
- [ ] 「確定シフト」ページの「お知らせを投稿」ボタンで確定シフト公開のお知らせが投稿される。
- [ ] 期間追加で、設定ON時のみ自動投稿される（管理画面でオンオフできる）。
- [ ] `migrate` 後、既存データが保持されている。
