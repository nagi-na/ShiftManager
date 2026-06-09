from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """アプリ利用者。スタッフ／リーダー共通。

    - ``username`` をログインID（リーダーが配布）として利用する。
    - ``email`` は AbstractUser のものを任意項目のまま利用（将来の通知用）。
    - 無効化は AbstractUser の ``is_active`` を利用する（退職者など）。
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "システム管理者"
        LEADER = "leader", "リーダー"
        CREW = "crew", "クルー"

    name = models.CharField("表示名", max_length=100)
    role = models.CharField(
        "ロール", max_length=16, choices=Role.choices, default=Role.CREW
    )
    fixed_shift_editable_by_crew = models.BooleanField(
        "本人による固定シフト編集を許可",
        default=False,
        help_text="オンにすると、このクルー本人が自分の固定シフトを編集できます。",
    )

    class Meta:
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"

    def __str__(self):
        return f"{self.name}（{self.username}）"

    @property
    def is_admin(self) -> bool:
        """システム管理者。アカウント管理を含む全権限。"""
        return self.role == self.Role.ADMIN

    @property
    def is_leader(self) -> bool:
        return self.role == self.Role.LEADER

    @property
    def can_manage(self) -> bool:
        """管理機能（アカウント管理を除く）にアクセスできるか。"""
        return self.role in (self.Role.ADMIN, self.Role.LEADER)

    @property
    def can_manage_accounts(self) -> bool:
        """アカウント管理ができるか（システム管理者のみ）。"""
        return self.role == self.Role.ADMIN

    def can_edit_fixed_shift_of(self, target) -> bool:
        """自分(self)が target の固定シフトを編集してよいか。

        リーダー/管理者は誰のでも編集可。クルーは自分のだけ、かつ許可フラグが立つときのみ。
        """
        if self.can_manage:
            return True
        return self.pk == target.pk and target.fixed_shift_editable_by_crew
