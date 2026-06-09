"""shifts アプリのテスト。

  ② 提出フロー  : shift_submit ビューが提出・休み・バリデーション・履歴・締切後read-onlyを正しく扱うか
  ③ 締切ポリシー: _submission_permission 等のロジック関数が締切前後の可否を正しく返すか

締切ポリシーのような「条件分岐が多い純粋な関数」は、ビュー経由ではなく
関数を直接呼ぶ単体テストにすると、網羅も原因特定も簡単になる。
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import (
    ConfirmedShift,
    ShiftPeriod,
    ShiftRequest,
    ShiftRequestDay,
    WeeklyFixedShift,
)
from .views import _is_closed, _manually_closed, _submission_permission

Policy = ShiftPeriod.PostDeadlinePolicy
Status = ShiftPeriod.Status


def make_period(creator, deadline, *, status=Status.OPEN, policy=Policy.LATE_SUBMIT,
                edit_deadline=None, start=None, end=None):
    """テスト用の対象期間を作る。日付は未指定なら当日1日分。"""
    today = timezone.localdate()
    return ShiftPeriod.objects.create(
        title="テスト期間",
        start_date=start or today,
        end_date=end or today,
        deadline=deadline,
        status=status,
        post_deadline_policy=policy,
        edit_deadline=edit_deadline,
        created_by=creator,
    )


class DeadlineLogicTests(TestCase):
    """③ 締切ポリシー: _submission_permission / _is_closed / _manually_closed の単体テスト。

    _submission_permission(period, now, submitted) は (新規提出可?, 編集可?) を返す。
    """

    def setUp(self):
        self.creator = User.objects.create_user("leader", password="x")
        self.now = timezone.now()
        self.past = self.now - timedelta(hours=1)    # 締切=過去 → 締切後
        self.future = self.now + timedelta(hours=1)  # 締切=未来 → 締切前

    # --- 締切前・手動締切（ポリシー以前の大前提） ---

    def test_before_deadline_anyone_can_submit_and_edit(self):
        period = make_period(self.creator, self.future)
        self.assertEqual(_submission_permission(period, self.now, submitted=False), (True, True))
        self.assertEqual(_submission_permission(period, self.now, submitted=True), (True, True))

    def test_manual_close_locks_everything_even_before_deadline(self):
        period = make_period(self.creator, self.future, status=Status.CLOSED)
        self.assertEqual(_submission_permission(period, self.now, submitted=False), (False, False))

    # --- 締切後の3ポリシー ---

    def test_after_deadline_lock_all(self):
        period = make_period(self.creator, self.past, policy=Policy.LOCK_ALL)
        self.assertEqual(_submission_permission(period, self.now, submitted=False), (False, False))

    def test_after_deadline_late_submit(self):
        # 未提出者だけ提出可、編集は不可。
        period = make_period(self.creator, self.past, policy=Policy.LATE_SUBMIT)
        self.assertEqual(_submission_permission(period, self.now, submitted=False), (True, False))
        self.assertEqual(_submission_permission(period, self.now, submitted=True), (False, False))

    def test_after_deadline_editable_manual(self):
        # 編集最終期限なし＝管理者が締め切るまで提出・編集可。
        period = make_period(self.creator, self.past, policy=Policy.EDITABLE, edit_deadline=None)
        self.assertEqual(_submission_permission(period, self.now, submitted=True), (True, True))

    def test_after_deadline_editable_within_edit_deadline(self):
        period = make_period(self.creator, self.past, policy=Policy.EDITABLE,
                             edit_deadline=self.future)
        self.assertEqual(_submission_permission(period, self.now, submitted=True), (True, True))

    def test_after_deadline_editable_past_edit_deadline(self):
        # 編集最終期限も過ぎていれば締切扱い。
        period = make_period(self.creator, self.past - timedelta(hours=2), policy=Policy.EDITABLE,
                             edit_deadline=self.past)
        self.assertEqual(_submission_permission(period, self.now, submitted=True), (False, False))

    # --- 締切状態の判定ヘルパー ---

    def test_is_closed(self):
        self.assertFalse(_is_closed(make_period(self.creator, self.future), self.now))
        self.assertTrue(_is_closed(make_period(self.creator, self.past), self.now))
        self.assertTrue(_is_closed(make_period(self.creator, self.future, status=Status.CLOSED), self.now))

    def test_manually_closed_only_when_closed_before_deadline(self):
        self.assertTrue(_manually_closed(make_period(self.creator, self.future, status=Status.CLOSED), self.now))
        self.assertFalse(_manually_closed(make_period(self.creator, self.past, status=Status.CLOSED), self.now))
        self.assertFalse(_manually_closed(make_period(self.creator, self.future), self.now))


def formset_post_data(days, note=""):
    """shift_submit へ送る POST データ（フォームセット）を組み立てる。

    days: [{"work_date": date, "day_off": bool, "start": "HH:MM", "end": "HH:MM"}, ...]
    フォームセットには管理用の TOTAL_FORMS 等が必須。
    """
    data = {
        "day-TOTAL_FORMS": str(len(days)),
        "day-INITIAL_FORMS": "0",
        "day-MIN_NUM_FORMS": "0",
        "day-MAX_NUM_FORMS": "1000",
        "note": note,
    }
    for i, d in enumerate(days):
        data[f"day-{i}-work_date"] = d["work_date"].isoformat()
        if d.get("day_off"):
            data[f"day-{i}-is_day_off"] = "on"
        if d.get("start"):
            data[f"day-{i}-start_time"] = d["start"]
        if d.get("end"):
            data[f"day-{i}-end_time"] = d["end"]
    return data


class SubmitFlowTests(TestCase):
    """② 提出フロー: クルーが shift_submit で希望を提出・編集する流れ。"""

    def setUp(self):
        self.leader = User.objects.create_user("leader", password="x")
        self.crew = User.objects.create_user("crew", password="x")
        self.crew.role = User.Role.CREW
        self.crew.save(update_fields=["role"])
        today = timezone.localdate()
        # 締切は未来＝募集中、2日分の期間
        self.period = make_period(
            self.leader, timezone.now() + timedelta(days=3),
            start=today, end=today + timedelta(days=1),
        )
        self.d0 = today
        self.d1 = today + timedelta(days=1)
        self.client.force_login(self.crew)
        self.url = reverse("shift_submit", args=[self.period.pk])

    def test_submit_creates_request_days_and_history(self):
        data = formset_post_data([
            {"work_date": self.d0, "start": "09:00", "end": "17:00"},
            {"work_date": self.d1, "start": "10:00", "end": "18:00"},
        ], note="よろしくお願いします")
        resp = self.client.post(self.url, data)
        self.assertRedirects(resp, reverse("home"))

        req = ShiftRequest.objects.get(period=self.period, user=self.crew)
        self.assertEqual(req.note, "よろしくお願いします")
        self.assertEqual(req.days.count(), 2)
        self.assertEqual(req.histories.count(), 1)            # スナップショット v1
        self.assertEqual(req.histories.first().version_no, 1)

    def test_day_off_saved_without_times(self):
        data = formset_post_data([
            {"work_date": self.d0, "day_off": True},
            {"work_date": self.d1, "start": "10:00", "end": "18:00"},
        ])
        self.client.post(self.url, data)

        day = ShiftRequestDay.objects.get(request__period=self.period, work_date=self.d0)
        self.assertFalse(day.is_available)   # 休み
        self.assertIsNone(day.start_time)
        self.assertIsNone(day.end_time)

    def test_working_day_without_times_is_rejected(self):
        # 出勤日なのに時刻未選択 → フォーム不正 → 提出は保存されない。
        data = formset_post_data([
            {"work_date": self.d0},  # 休みでないのに時刻なし
            {"work_date": self.d1, "start": "10:00", "end": "18:00"},
        ])
        resp = self.client.post(self.url, data)
        self.assertEqual(resp.status_code, 200)  # 再表示（リダイレクトしない）
        self.assertFalse(ShiftRequest.objects.filter(period=self.period, user=self.crew).exists())

    def test_start_after_end_is_rejected(self):
        data = formset_post_data([
            {"work_date": self.d0, "start": "18:00", "end": "10:00"},  # 逆転
            {"work_date": self.d1, "start": "10:00", "end": "18:00"},
        ])
        self.client.post(self.url, data)
        self.assertFalse(ShiftRequest.objects.filter(period=self.period, user=self.crew).exists())

    def test_resubmit_adds_history_version(self):
        base = [
            {"work_date": self.d0, "start": "09:00", "end": "17:00"},
            {"work_date": self.d1, "start": "10:00", "end": "18:00"},
        ]
        self.client.post(self.url, formset_post_data(base))
        # 2回目の提出（編集）
        self.client.post(self.url, formset_post_data(base, note="変更しました"))

        req = ShiftRequest.objects.get(period=self.period, user=self.crew)
        self.assertEqual(req.histories.count(), 2)
        self.assertEqual(
            list(req.histories.values_list("version_no", flat=True)), [2, 1]  # 降順
        )

    def test_readonly_after_deadline_lock_all_blocks_submit(self):
        # 締切後 LOCK_ALL の期間では、POST しても保存されない（閲覧のみ）。
        closed = make_period(
            self.leader, timezone.now() - timedelta(hours=1), policy=Policy.LOCK_ALL,
            start=self.d0, end=self.d0,
        )
        url = reverse("shift_submit", args=[closed.pk])
        resp = self.client.post(url, formset_post_data([
            {"work_date": self.d0, "start": "09:00", "end": "17:00"},
        ]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ShiftRequest.objects.filter(period=closed, user=self.crew).exists())

    def test_hidden_period_blocks_crew(self):
        # 非表示期間はクルーがアクセスできずホームへ戻される。
        hidden = make_period(self.leader, timezone.now() + timedelta(days=3),
                             start=self.d0, end=self.d0)
        hidden.is_visible = False
        hidden.save(update_fields=["is_visible"])
        resp = self.client.get(reverse("shift_submit", args=[hidden.pk]))
        self.assertRedirects(resp, reverse("home"))


class ConfirmedFileAccessTests(TestCase):
    """確定シフトPDFの配信が「ログイン必須」になっているかの検証。

    無認証で直リンクから取得できると情報漏洩になるため、
    未ログインは login へ飛ばし、ログイン済みのみ X-Accel-Redirect を返す。
    """

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.leader = User.objects.create_user("leader", password="x")
        self.cs = ConfirmedShift.objects.create(
            period=make_period(self.leader, timezone.now() + timedelta(days=3)),
            file=SimpleUploadedFile("確定.pdf", b"%PDF-1.4 dummy", content_type="application/pdf"),
            original_name="確定.pdf",
            uploaded_by=self.leader,
        )
        self.url = reverse("confirmed_shift_file", args=[self.cs.pk])

    def tearDown(self):
        self.cs.file.delete(save=False)

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_logged_in_user_gets_x_accel_redirect(self):
        # テスト実行時は DEBUG=False なので本番経路（X-Accel-Redirect）を通る。
        self.client.force_login(self.leader)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["X-Accel-Redirect"].startswith("/protected/"))
        self.assertEqual(resp["Content-Type"], "application/pdf")


def fixed_formset_data(days):
    """my_fixed_shift / manage_fixed_shift_edit へ送る固定シフトのPOSTデータ。

    days: 月〜日(0..6)の順で7件 [{"day_off":bool,"start":"HH:MM","end":"HH:MM"}, ...]
    """
    data = {
        "fx-TOTAL_FORMS": "7",
        "fx-INITIAL_FORMS": "0",
        "fx-MIN_NUM_FORMS": "0",
        "fx-MAX_NUM_FORMS": "1000",
    }
    for i, d in enumerate(days):
        data[f"fx-{i}-weekday"] = str(i)
        if d.get("day_off"):
            data[f"fx-{i}-is_day_off"] = "on"
        if d.get("start"):
            data[f"fx-{i}-start_time"] = d["start"]
        if d.get("end"):
            data[f"fx-{i}-end_time"] = d["end"]
    return data


class FixedShiftTests(TestCase):
    """固定シフト：編集権限・代理編集・許可トグル・提出画面への受け渡し。"""

    def setUp(self):
        self.admin = User.objects.create_user("admin", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.save(update_fields=["role"])
        self.leader = User.objects.create_user("leader", password="x")
        self.leader.role = User.Role.LEADER
        self.leader.save(update_fields=["role"])
        self.crew = User.objects.create_user("crew", password="x")  # 既定 role=crew

    # --- 権限ヘルパー ---

    def test_permission_helper(self):
        other = User.objects.create_user("crew2", password="x")
        # リーダー/管理者は誰のでも編集可
        self.assertTrue(self.leader.can_edit_fixed_shift_of(self.crew))
        self.assertTrue(self.admin.can_edit_fixed_shift_of(self.crew))
        # クルーは許可が無いと自分のも不可
        self.assertFalse(self.crew.can_edit_fixed_shift_of(self.crew))
        # 許可されれば自分のは可、他人のは不可
        self.crew.fixed_shift_editable_by_crew = True
        self.assertTrue(self.crew.can_edit_fixed_shift_of(self.crew))
        self.assertFalse(self.crew.can_edit_fixed_shift_of(other))

    def test_new_account_default_not_editable(self):
        self.assertFalse(User.objects.create_user("new", password="x").fixed_shift_editable_by_crew)

    # --- 本人編集（許可フラグで制御） ---

    def test_crew_without_permission_cannot_save(self):
        self.client.force_login(self.crew)
        days = [{"start": "09:00", "end": "17:00"} for _ in range(7)]
        resp = self.client.post(reverse("my_fixed_shift"), fixed_formset_data(days))
        self.assertEqual(resp.status_code, 200)  # 保存せず再表示
        self.assertEqual(WeeklyFixedShift.objects.filter(user=self.crew).count(), 0)

    def test_crew_with_permission_saves(self):
        self.crew.fixed_shift_editable_by_crew = True
        self.crew.save(update_fields=["fixed_shift_editable_by_crew"])
        self.client.force_login(self.crew)
        days = [{"start": "09:00", "end": "17:00"} for _ in range(7)]
        days[6] = {"day_off": True}  # 日曜は休み
        resp = self.client.post(reverse("my_fixed_shift"), fixed_formset_data(days))
        self.assertRedirects(resp, reverse("my_fixed_shift"))
        self.assertEqual(WeeklyFixedShift.objects.filter(user=self.crew).count(), 7)
        sun = WeeklyFixedShift.objects.get(user=self.crew, weekday=6)
        self.assertFalse(sun.is_available)
        self.assertIsNone(sun.start_time)
        mon = WeeklyFixedShift.objects.get(user=self.crew, weekday=0)
        self.assertEqual((mon.start_time, mon.end_time), ("09:00", "17:00"))

    # --- リーダーの代理編集 ---

    def test_leader_can_edit_crew(self):
        self.client.force_login(self.leader)
        days = [{"start": "10:00", "end": "18:00"} for _ in range(7)]
        resp = self.client.post(
            reverse("manage_fixed_shift_edit", args=[self.crew.pk]),
            fixed_formset_data(days),
        )
        self.assertRedirects(resp, reverse("manage_fixed_shifts"))
        self.assertEqual(WeeklyFixedShift.objects.filter(user=self.crew).count(), 7)

    def test_crew_cannot_access_manage_list(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("manage_fixed_shifts"))
        self.assertRedirects(resp, reverse("home"))

    # --- 許可トグル（個別・一斉） ---

    def test_individual_toggle(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("manage_account_toggle_fixed_edit", args=[self.crew.pk]))
        self.crew.refresh_from_db()
        self.assertTrue(self.crew.fixed_shift_editable_by_crew)

    def test_bulk_toggle_enables_only_crew(self):
        crew2 = User.objects.create_user("crew2", password="x")
        self.client.force_login(self.admin)
        self.client.post(reverse("manage_account_bulk_fixed_edit"), {"enable": "1"})
        self.crew.refresh_from_db()
        crew2.refresh_from_db()
        self.leader.refresh_from_db()
        self.assertTrue(self.crew.fixed_shift_editable_by_crew)
        self.assertTrue(crew2.fixed_shift_editable_by_crew)
        self.assertFalse(self.leader.fixed_shift_editable_by_crew)  # クルー以外は対象外

    def test_bulk_toggle_requires_admin(self):
        self.client.force_login(self.leader)  # リーダーはアカウント管理権限なし
        resp = self.client.post(reverse("manage_account_bulk_fixed_edit"), {"enable": "1"})
        self.assertRedirects(resp, reverse("home"))
        self.crew.refresh_from_db()
        self.assertFalse(self.crew.fixed_shift_editable_by_crew)

    # --- 提出画面への受け渡し ---

    def test_submit_page_exposes_fixed_shift(self):
        today = timezone.localdate()
        period = make_period(
            self.leader, timezone.now() + timedelta(days=3), start=today, end=today
        )
        WeeklyFixedShift.objects.create(
            user=self.crew, weekday=today.weekday(),
            is_available=True, start_time="09:00", end_time="17:00",
        )
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("shift_submit", args=[period.pk]))
        self.assertTrue(resp.context["has_fixed_shift"])
        self.assertIn(str(today.weekday()), resp.context["fixed_shift_json"])
        self.assertContains(resp, 'id="apply-fixed"')
        self.assertContains(resp, 'fixed-shift-data')
