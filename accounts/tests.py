"""accounts アプリの権限・認証まわりのテスト。

テストの観点は3つ:
  1. User モデルの権限プロパティ（can_manage など）が正しいか
  2. 各画面が「ログイン状態」と「ロール」で正しく許可/拒否されるか
  3. ロックアウト防止（自分自身を無効化・降格・削除できない）が効いているか

Django のテストは各メソッドごとに専用DBが作られ、自動でロールバックされる。
そのため他テストへの影響を気にせず自由にデータを作ってよい。
"""

from django.test import TestCase
from django.urls import reverse

from .models import User


def make_user(username, role, password="pass12345", **extra):
    """指定ロールのユーザーを作るテスト用ヘルパー。"""
    user = User.objects.create_user(username=username, password=password, **extra)
    user.role = role
    user.save(update_fields=["role"])
    return user


class RolePropertyTests(TestCase):
    """User モデルの権限判定プロパティの真偽値を確認する（DB・画面に依存しない単体テスト）。"""

    def test_admin_has_all_permissions(self):
        admin = make_user("admin", User.Role.ADMIN)
        self.assertTrue(admin.is_admin)
        self.assertTrue(admin.can_manage)
        self.assertTrue(admin.can_manage_accounts)

    def test_leader_can_manage_but_not_accounts(self):
        # リーダーは管理機能は使えるが、アカウント管理だけは不可。
        leader = make_user("leader", User.Role.LEADER)
        self.assertFalse(leader.is_admin)
        self.assertTrue(leader.is_leader)
        self.assertTrue(leader.can_manage)
        self.assertFalse(leader.can_manage_accounts)

    def test_crew_cannot_manage(self):
        crew = make_user("crew", User.Role.CREW)
        self.assertFalse(crew.can_manage)
        self.assertFalse(crew.can_manage_accounts)


class ManagerAccessTests(TestCase):
    """manager_required の画面（例: 期間管理）への入退室を、ログイン状態とロール別に確認する。"""

    def setUp(self):
        self.url = reverse("manage_periods")
        self.admin = make_user("admin", User.Role.ADMIN)
        self.leader = make_user("leader", User.Role.LEADER)
        self.crew = make_user("crew", User.Role.CREW)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("login"))

    def test_crew_denied_redirected_home(self):
        self.client.force_login(self.crew)
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("home"))

    def test_leader_allowed(self):
        self.client.force_login(self.leader)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_allowed(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)


class AdminAccessTests(TestCase):
    """admin_required の画面（アカウント管理）。リーダーでも入れない点が manager_required との違い。"""

    def setUp(self):
        self.url = reverse("manage_accounts")
        self.admin = make_user("admin", User.Role.ADMIN)
        self.leader = make_user("leader", User.Role.LEADER)
        self.crew = make_user("crew", User.Role.CREW)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("login"))

    def test_crew_denied(self):
        self.client.force_login(self.crew)
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("home"))

    def test_leader_denied(self):
        # リーダーは管理権限はあるが、アカウント管理は管理者専用なので弾かれる。
        self.client.force_login(self.leader)
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("home"))

    def test_admin_allowed(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)


class LockoutPreventionTests(TestCase):
    """管理者が自分をロックアウトする操作を防げているかを確認する（最重要のセキュリティロジック）。"""

    def setUp(self):
        self.admin = make_user("admin", User.Role.ADMIN, name="管理者")
        self.crew = make_user("crew", User.Role.CREW, name="クルー")
        self.client.force_login(self.admin)

    def test_cannot_deactivate_self(self):
        self.client.post(reverse("manage_account_toggle", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)  # 無効化されず有効のまま

    def test_cannot_delete_self(self):
        self.client.post(reverse("manage_account_delete", args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_cannot_demote_self_via_edit(self):
        # 自分のロールをクルーへ下げようとしても拒否され、admin のまま。
        self.client.post(
            reverse("manage_account_edit", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "name": self.admin.name,
                "email": "",
                "role": User.Role.CREW,
                "is_active": "on",
            },
        )
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)

    def test_can_deactivate_other_user(self):
        # 対照テスト: 他人(クルー)は問題なく無効化できる＝制限は「自分」に限定されている。
        self.client.post(reverse("manage_account_toggle", args=[self.crew.pk]))
        self.crew.refresh_from_db()
        self.assertFalse(self.crew.is_active)

    def test_cannot_reset_own_password(self):
        # 自分への再発行は認証ハッシュが変わって即ログアウトし、表示された
        # 新パスワードを見逃すと自分で復旧できなくなるためブロックする。
        old_hash = self.admin.password
        self.client.post(reverse("manage_account_reset", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.password, old_hash)  # パスワードは変わらない

    def test_can_reset_other_password(self):
        # 対照テスト: 他人の再発行は通る（パスワードハッシュが変わる）。
        old_hash = self.crew.password
        self.client.post(reverse("manage_account_reset", args=[self.crew.pk]))
        self.crew.refresh_from_db()
        self.assertNotEqual(self.crew.password, old_hash)
