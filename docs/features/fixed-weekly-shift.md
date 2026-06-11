# 固定シフトのコピー反映（曜日別デフォルトシフト）

## 1. 目的・背景

パートタイムのクルーなど、**毎週ほぼ同じ曜日・同じ時間に入る人**は、希望提出のたびに各日のプルダウンを選び直すのが負担。
そこで、クルーごとに **曜日（月〜日）ごとの「固定シフト」** を持たせ、希望提出フォームで **ボタン一つで対象期間の各日付に反映**できるようにする。固定どおりでよければそのまま提出、違う日だけ手で直す、という流れにする。

## 2. 仕様

### 2-1. 固定シフトの保持内容
- クルー1人につき **月〜日の7曜日** 分を保持。
- 各曜日は次のどちらか：
  - **出勤**：開始時刻・終了時刻（既存の `TIME_CHOICES` = 8:00〜24:00 / 30分刻みと同じ）。
  - **休み**：出勤不可（`is_available=False`）。
- 未登録のクルーもいる（その場合は反映ボタンを使えない／無効表示）。

### 2-2. 編集権限（重要）
| 操作者 | 自分の固定シフト | 他クルーの固定シフト |
| --- | --- | --- |
| リーダー / 管理者 | 常に編集可 | **常に編集可（代理）** |
| クルー | **許可されているときのみ**編集可 | 不可 |

- 「クルー本人が編集してよいか」は **クルーごとの許可フラグ**（`fixed_shift_editable_by_crew`）で制御する。
  - ⚠️ **実装上、切り替えできるのはシステム管理者（admin）のみ**（クルー管理画面内のため `@admin_required`。リーダーは切替不可）。リーダーにも切らせるかは未決（[コード精査レポート C-4](../reviews/コード精査レポート_2026-06-11.md)）。
- **アカウント作成時は既定で「不可」**（モデルの `default=False`）。新規クルーは最初、本人編集できない。
- 切り替えの場所（クルー管理画面 `accounts.account_list` ＝ `manage/accounts/`）：
  - **個別トグル**：各クルー行で1人ずつ許可/不許可（既存の `account_toggle_active` と同じ作り）。
  - **一斉トグル**：「**全クルーを一括で許可／不許可**」にするボタンを管理画面上部に置く（誤操作防止に確認ダイアログ）。
- 許可されていないクルーは、自分の固定シフトを直接は変更できないが、**変更を「申請」**できる（リーダー承認で反映。下記 2-6）。コピー反映は許可に関係なく使える（閲覧と利用は別）。

### 2-3. 「固定シフトを反映」ボタン（希望提出フォーム）
- 提出フォーム（`shifts/templates/shifts/*` の希望入力画面）に **「固定シフトを反映」ボタン**を置く。
- 押すと **確認ダイアログ**（「現在の入力内容を固定シフトで上書きします。よろしいですか？」）。
- OKで、**対象期間の全日付**について、その日付の**曜日に対応する固定シフト**で各日の入力を埋める：
  - 出勤の曜日 → 出勤可＋開始/終了時刻をセット。
  - 休みの曜日 → 出勤不可をセット。
- **既存の手入力も上書き**する（差分は反映後に手で直す前提）。
- 反映は**画面上の入力欄を書き換えるだけ**で、保存は通常どおり「提出」ボタンで行う（反映＝即保存ではない）。
- 固定シフト未登録のクルーにはボタンを**無効化**し、「固定シフトが未登録です（リーダーに設定を依頼）」と表示。

### 2-4. 締切・表示ルール
- ボタンは、その期間がそのクルーにとって**提出・編集可能なとき**だけ表示（既存の `ShiftPeriod.status` / `post_deadline_policy` / `edit_deadline` の判定に従う）。締切後で編集不可なら出さない。

### 2-5. 画面構成（UI）

**クルー本人向け：自分の固定シフトページ**
- ホーム（または `profile`）に **「固定シフトを確認」ボタン**を置き、専用ページへ遷移。
- ページでは月〜日の固定シフト（出勤/休み・時刻）を**一覧表示**。
- `fixed_shift_editable_by_crew=True` の人だけ、その場で**編集・保存**できる（Falseなら閲覧のみ＝編集UIを出さない）。
- 未登録のときは「まだ登録されていません（リーダーに設定を依頼してください）」と表示。

**リーダー/管理者向け：全クルーの固定シフト一覧・編集**
- 管理メニュー（`manage_top`）に「固定シフト管理」を追加。
- **全クルー分を一覧**で表示（クルー名 × 月〜日の早見表）。未登録のクルーも分かるように。
- 各クルーの固定シフトを**編集**できる（代理編集）。
- この一覧またはクルー管理画面に、2-2 の**一斉許可/不許可ボタン**を置く。

| 画面 | 誰が見る | できること |
| --- | --- | --- |
| 自分の固定シフトページ | クルー本人 | 閲覧（常時）／編集（許可時）／変更申請（未許可時, 2-6） |
| 固定シフト一覧（管理） | リーダー・管理者 | 全クルーの閲覧・代理編集・一斉許可切替 |
| 固定シフト申請（管理） | リーダー・管理者 | クルーの変更申請の承認/却下（2-6） |
| 希望提出フォーム | クルー本人 | 「固定シフトを反映」ボタン（2-3） |

### 2-6. 固定シフトの変更申請（承認制）

直接編集を許可されていないクルーでも、固定シフトの変更を**申請**でき、リーダーが承認すると反映される。

- クルー側（自分の固定シフトページ）：7曜日の希望を入力し、**コメント（任意）**を添えて「変更を申請」。
  - **1人1件の保留**。保留中は内容が**読み取り専用**になり、変えたいときは**自分で申請を取り消して**から新しく申請する（上書き再申請はしない）。
  - 保留中の状態と、前回の処理結果（承認/却下とリーダーのコメント）を表示。
- リーダー側（管理メニュー「固定シフト申請」）：
  - 承認待ち一覧（管理メニューに**保留件数バッジ**）。
  - 申請の詳細で**現在値と提案を並べて比較**（変更行をハイライト）、申請者コメントを確認。
  - **承認**＝提案内容（週まるごと）で固定シフトを全置換／**却下**＝反映しない。どちらでも**コメント（任意）**をクルーに返せる。

## 3. データモデルの変更

### 3-1. 新モデル `WeeklyFixedShift`（`shifts/models.py`）
```python
class WeeklyFixedShift(models.Model):
    """クルーの曜日別固定シフト。(user, weekday) で1件。"""

    class Weekday(models.IntegerChoices):
        MON = 0, "月"
        TUE = 1, "火"
        WED = 2, "水"
        THU = 3, "木"
        FRI = 4, "金"
        SAT = 5, "土"
        SUN = 6, "日"     # Python の date.weekday() に合わせる（月=0〜日=6）

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="fixed_shifts", verbose_name="クルー")
    weekday = models.IntegerField("曜日", choices=Weekday.choices)
    is_available = models.BooleanField("出勤可", default=True)
    start_time = models.CharField("開始時刻", max_length=5, null=True, blank=True, choices=TIME_CHOICES)
    end_time = models.CharField("終了時刻", max_length=5, null=True, blank=True, choices=TIME_CHOICES)

    class Meta:
        verbose_name = "固定シフト"
        verbose_name_plural = "固定シフト"
        ordering = ["user", "weekday"]
        constraints = [
            models.UniqueConstraint(fields=["user", "weekday"], name="unique_fixed_shift_per_weekday"),
        ]

    def clean(self):
        # ShiftRequestDay と同じバリデーション
        if self.is_available:
            if not self.start_time or not self.end_time:
                raise ValidationError("出勤可の曜日は開始・終了時刻が必須です。")
            if self.start_time >= self.end_time:
                raise ValidationError("開始時刻は終了時刻より前にしてください。")
```

### 3-2. 編集許可フラグ（`accounts/models.py` の `User`）
```python
fixed_shift_editable_by_crew = models.BooleanField(
    "本人による固定シフト編集を許可", default=False,
    help_text="オンにすると、このクルー本人が自分の固定シフトを編集できます。",
)
```
- ヘルパー（任意）：
```python
def can_edit_fixed_shift_of(self, target) -> bool:
    """actor(self) が target の固定シフトを編集してよいか。"""
    if self.can_manage:                 # リーダー/管理者は常に可
        return True
    return self == target and target.fixed_shift_editable_by_crew
```

> 🔰 `weekday` を **月=0〜日=6** にしておくと、反映時に `date.weekday()` の戻り値でそのまま引けるので実装が単純になる。

### 3-3. 変更申請モデル `FixedShiftChangeRequest`（`shifts/models.py`）
```python
class FixedShiftChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "保留"
        APPROVED = "approved", "承認"
        REJECTED = "rejected", "却下"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="fixed_shift_requests")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payload = models.JSONField()              # [{weekday,is_available,start_time,end_time}, ...] 7曜日分
    crew_comment = models.TextField(blank=True)   # 申請時のクルーコメント
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="reviewed_fixed_shift_requests")
    review_comment = models.TextField(blank=True) # 承認/却下時のリーダーコメント
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
```
- 保留は1人1件。保留中は新規申請をブロックし、本人が取り消す（保留を削除）と再申請できる。
- 承認時に `payload` の内容で `WeeklyFixedShift` を全置換する。
- 処理済み（承認/却下）は**クルーごとに直近10件**だけ保持し、処理のたびに古いものを削除する（`_prune_processed_requests`）。

## 4. 実装メモ（変更ファイルの見込み）

- `accounts/models.py` … `fixed_shift_editable_by_crew`（`default=False`）追加（＋`can_edit_fixed_shift_of`）。
- `shifts/models.py` … `WeeklyFixedShift`・`FixedShiftChangeRequest` 追加。
- フォーム … 固定シフト編集フォームセット（7曜日分。`ShiftRequestDay` 同様の出勤可否＋時刻）。
- ビュー / ルート（実装は `shifts` 側）
  - **クルー本人ページ**：`my_fixed_shift`（`/fixed-shift/`）。許可時は直接保存（edit）、未許可時は**変更申請**（request, コメント＋保留状態表示）。保留中は読み取り専用で、`my_fixed_shift_cancel`（`/fixed-shift/cancel/`）で取り消し→再申請。
  - **管理一覧／代理編集**：`manage_fixed_shifts`（`/manage/fixed-shifts/`）＋ `manage_fixed_shift_edit`（`.../<user_pk>/edit/`）。`@manager_required`。
  - **申請の承認**：`manage_fixed_shift_requests`（`/manage/fixed-shift-requests/` 一覧）＋ `manage_fixed_shift_request_review`（`.../<pk>/review/` 比較＋承認/却下）。`@manager_required`。
  - **個別/一斉トグル**：`accounts` に `manage/accounts/<pk>/toggle-fixed-edit/`（個別）と `manage/accounts/fixed-edit/bulk/`（全クルー一括、POST＋確認）。`@admin_required`。
  - **反映用データ**：`shift_submit` で対象ユーザーの固定シフトを **JSON でテンプレートへ渡す**（曜日→{off,start,end}）。
- テンプレート
  - `fixed_shift_edit.html`（本人/代理 兼用：edit/request モード）、`manage_fixed_shifts.html`、`manage_fixed_shift_requests.html`、`manage_fixed_shift_request_review.html`。
  - `home.html` に「固定シフトを確認」ボタン、`manage_top.html` に「固定シフト管理」「固定シフト申請（保留件数バッジ）」、クルー管理(`account_list.html`)に個別/一斉トグル。
  - `submit.html` に「固定シフトを反映」ボタン＋確認ダイアログ＋埋め込んだJSONから入力欄を書き換える小さなJS。
- `shifts/admin.py` … `WeeklyFixedShift`・`FixedShiftChangeRequest` を管理画面に登録。
- `shifts/tests.py` … 権限・コピー反映・申請/承認/却下/再申請・コメントをテスト化。

### 反映ロジック（擬似コード）
```
fixed = { ws.weekday: ws for ws in target.fixed_shifts.all() }   # 曜日→固定
for d in 各日付(period.start_date .. period.end_date):
    f = fixed.get(d.weekday())
    if f is None:            # その曜日が未登録なら触らない（基本は7曜日揃える運用）
        continue
    日入力[d].available = f.is_available
    日入力[d].start     = f.start_time if f.is_available else None
    日入力[d].end       = f.end_time   if f.is_available else None
```
（実反映はクライアント側JSで画面の入力欄に適用。保存は「提出」時に既存処理で行う）

## 5. アップデート手順（本番反映）

このバージョンは **新テーブル追加＋User列追加** だけで、既存データは保持される（[2章 2-4](../lecture/02_データモデルとマイグレーション.md) のとおり `migrate` は差分のみ適用）。`fixed_shift_editable_by_crew` は既定 `False` なので、既存クルーの挙動は変わらない（最初は全員「本人編集不可」）。

```bash
# --- 開発側（このファイルの実装後） ---
python manage.py makemigrations          # accounts, shifts の新マイグレーションを生成
python manage.py migrate                 # 手元で確認
python manage.py test shifts             # テスト
git add -A && git commit -m "feat: 曜日別固定シフトとコピー反映" && git push
```

```bash
# --- 本番(systemd) ---
mysqldump -u shift -p shift_manager > backup_$(date +%F).sql   # ① バックアップ
git pull                                                       # ② コード＋新マイグレーション取得
./venv/bin/python manage.py migrate                            # ③ 新テーブル/列を追加（データ保持）
DJANGO_DEBUG=0 ./venv/bin/python manage.py collectstatic --noinput  # ④ JS等の静的更新があれば
sudo systemctl restart shiftmanager                            # ⑤ 反映
```

```bash
# --- 本番(Docker) ---
docker compose exec -T db sh -c 'exec mysqldump -ushift -p"$MYSQL_PASSWORD" shift_manager' > backup_$(date +%F).sql
git pull
docker compose up -d --build
docker compose exec web python manage.py migrate
```

> ⚠️ このマイグレーションは追加のみで破壊的変更（列・表の削除）は無いため、通常はデータ消失なし。ロールバックする場合はコードを戻すだけでよい（新テーブルは残しても無害。完全に戻すなら `migrate shifts <前の番号>` / `migrate accounts <前の番号>`）。

## 6. 確認項目

- [ ] リーダーは任意クルーの固定シフトを編集・保存できる（管理一覧から代理編集）。
- [ ] クルーは自分の固定シフトページを**常に閲覧**でき、`fixed_shift_editable_by_crew=True` のときだけ直接編集できる。
- [ ] 許可が無いクルーは「変更を申請」でき（コメント任意）。保留中は読み取り専用で、**取り消してから**再申請できる（1人1件）。
- [ ] リーダーは申請一覧から承認/却下でき、**承認で固定シフトに全置換**、却下は未反映。どちらもコメントを返せ、クルー側に表示される。
- [ ] 管理メニューに承認待ちの**保留件数**が出る。
- [ ] 処理済み申請はクルーごとに直近10件だけ残り、超過分は古いものから削除される。
- [ ] 新規アカウントは既定で `fixed_shift_editable_by_crew=False`。
- [ ] クルー管理画面の**個別トグル**で1人ずつ、**一斉ボタン**で全クルーまとめて許可/不許可を切り替えられる（確認あり）。
- [ ] 出勤/休みの両方を曜日ごとに保存できる（休みは `is_available=False`）。
- [ ] 提出フォームの「固定シフトを反映」→確認→**期間内の全日付**が曜日対応で埋まる（同じ曜日が複数あれば全部）。休みの曜日は出勤不可になる。
- [ ] 反映後に一部の日を手で直して提出でき、反映は保存と独立している。
- [ ] 固定シフト未登録のクルーはボタンが無効＆案内が出る。
- [ ] 締切後（編集不可ポリシー）はボタンが出ない。
- [ ] `migrate` 後、既存の希望データ・ユーザーが保持されている。
