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

from .models import ShiftPeriod, ShiftRequest, ShiftRequestDay
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
