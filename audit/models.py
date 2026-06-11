from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """操作ログ（誰が・いつ・何をしたか）。システム管理者だけが閲覧する。

    記録は ``audit.utils.log_action`` / シグナル（ログイン・ログアウト）から行う。
    件数は ``MAX_ROWS`` 件で頭打ちにし、超えたら古いものから自動削除する。
    """

    MAX_ROWS = 5000  # この件数を超えたら古いものから消す

    class Action(models.TextChoices):
        LOGIN = "login", "ログイン"
        LOGOUT = "logout", "ログアウト"
        # アカウント
        ACCOUNT_CREATE = "account_create", "アカウント作成"
        ACCOUNT_EDIT = "account_edit", "アカウント編集"
        ACCOUNT_DELETE = "account_delete", "アカウント削除"
        ACCOUNT_RESET_PW = "account_reset_pw", "パスワード再発行"
        ACCOUNT_TOGGLE_ACTIVE = "account_toggle_active", "有効/無効化"
        ACCOUNT_TOGGLE_FIXED = "account_toggle_fixed", "固定シフト編集許可の変更"
        # 対象期間
        PERIOD_CREATE = "period_create", "期間作成"
        PERIOD_EDIT = "period_edit", "期間編集"
        PERIOD_CLOSE = "period_close", "期間の締切/再開"
        PERIOD_VISIBILITY = "period_visibility", "期間の表示/非表示"
        PERIOD_DELETE = "period_delete", "期間削除"
        # シフト提出
        SHIFT_SUBMIT = "shift_submit", "シフト希望の提出/編集"
        # 確定シフト
        CONFIRMED_UPLOAD = "confirmed_upload", "確定シフトのアップロード"
        CONFIRMED_DELETE = "confirmed_delete", "確定シフトの削除"
        # アナウンス
        ANNOUNCE_CREATE = "announce_create", "アナウンス投稿"
        ANNOUNCE_EDIT = "announce_edit", "アナウンス編集"
        ANNOUNCE_DELETE = "announce_delete", "アナウンス削除"
        ANNOUNCE_SETTINGS = "announce_settings", "アナウンス自動投稿設定"
        # 固定シフト
        FIXED_EDIT = "fixed_edit", "固定シフトの編集"
        FIXED_REQUEST = "fixed_request", "固定シフト変更申請"
        FIXED_REQUEST_CANCEL = "fixed_request_cancel", "固定シフト申請の取消"
        FIXED_REQUEST_REVIEW = "fixed_request_review", "固定シフト申請の承認/却下"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="操作者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    # 操作者が後で削除されてもログ上の名前を残すためのスナップショット
    actor_label = models.CharField("操作者名", max_length=150, blank=True)
    action = models.CharField("操作の種類", max_length=32, choices=Action.choices, db_index=True)
    summary = models.CharField("内容", max_length=255)
    target = models.CharField("対象", max_length=255, blank=True)
    ip_address = models.GenericIPAddressField("IPアドレス", null=True, blank=True)
    created_at = models.DateTimeField("日時", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "監査ログ"
        verbose_name_plural = "監査ログ"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor_label} {self.get_action_display()}"
