"""audit アプリのテスト。

  - 記録: log_action / ログインシグナル / 5000件での自動削除
  - 閲覧: admin のみ可、検索フィルタ、PDF/CSV 出力
"""

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import AuditLog
from .utils import log_action, record


class RecordTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.name = "管理 太郎"
        self.admin.save()

    def test_log_action_records_actor_and_ip(self):
        req = RequestFactory().post("/x/", REMOTE_ADDR="203.0.113.9")
        req.user = self.admin
        log_action(req, AuditLog.Action.ACCOUNT_CREATE, "アカウントを作成", target="山田")
        log = AuditLog.objects.get()
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.actor_label, "管理 太郎")
        self.assertEqual(log.action, AuditLog.Action.ACCOUNT_CREATE)
        self.assertEqual(log.target, "山田")
        self.assertEqual(log.ip_address, "203.0.113.9")

    def test_forwarded_for_is_used(self):
        req = RequestFactory().get("/x/", HTTP_X_FORWARDED_FOR="198.51.100.7, 10.0.0.1")
        req.user = self.admin
        log_action(req, AuditLog.Action.LOGIN, "ログイン")
        self.assertEqual(AuditLog.objects.get().ip_address, "198.51.100.7")

    def test_prune_keeps_latest_max_rows(self):
        AuditLog.MAX_ROWS  # 5000 が既定
        # 上限+5 件入れて、最新 MAX_ROWS 件だけ残ることを確認（高速化のため一時的に縮小）
        original = AuditLog.MAX_ROWS
        try:
            AuditLog.MAX_ROWS = 10
            for i in range(15):
                record(self.admin, AuditLog.Action.LOGIN, f"ログイン{i}")
            self.assertEqual(AuditLog.objects.count(), 10)
            # 最新（ログイン14）が残り、古い（ログイン0）が消えている
            self.assertTrue(AuditLog.objects.filter(summary="ログイン14").exists())
            self.assertFalse(AuditLog.objects.filter(summary="ログイン0").exists())
        finally:
            AuditLog.MAX_ROWS = original

    def test_login_signal_creates_log(self):
        self.client.login(username="admin", password="x")
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.LOGIN, actor=self.admin).exists()
        )


class ViewAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.save()
        self.leader = User.objects.create_user("leader", password="x")
        self.leader.role = User.Role.LEADER
        self.leader.save()
        self.crew = User.objects.create_user("crew", password="x")  # 既定 crew
        record(self.admin, AuditLog.Action.ACCOUNT_CREATE, "アカウントを作成", target="クルーA")
        record(self.leader, AuditLog.Action.PERIOD_CREATE, "対象期間を作成", target="6月前半")
        self.url = reverse("audit_log_list")

    def test_admin_can_view(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "操作ログ")

    def test_leader_is_blocked(self):
        self.client.force_login(self.leader)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_crew_is_blocked(self):
        self.client.force_login(self.crew)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_filter_by_action(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url, {"action": AuditLog.Action.PERIOD_CREATE})
        self.assertContains(resp, "6月前半")
        self.assertNotContains(resp, "クルーA")

    def test_filter_by_actor(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url, {"actor": self.admin.pk})
        self.assertContains(resp, "クルーA")
        self.assertNotContains(resp, "6月前半")

    def test_pdf_export(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("audit_log_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF-"))

    def test_csv_export(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("audit_log_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = resp.content.decode("utf-8-sig")
        self.assertIn("対象期間を作成", body)
        self.assertIn("6月前半", body)

    def test_csv_blocked_for_crew(self):
        self.client.force_login(self.crew)
        self.assertEqual(self.client.get(reverse("audit_log_csv")).status_code, 302)


class IntegrationTests(TestCase):
    """実際のビュー操作がログを残すか（代表として、管理者のアカウント作成）。"""

    def setUp(self):
        self.admin = User.objects.create_user("admin", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.save()

    def test_account_create_is_logged(self):
        self.client.force_login(self.admin)
        before = AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_CREATE).count()
        self.client.post(reverse("manage_accounts"), {
            "username": "newcrew", "name": "新人 花子", "role": User.Role.CREW, "email": "",
        })
        after = AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_CREATE).count()
        self.assertEqual(after, before + 1)
