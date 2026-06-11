from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "監査ログ"

    def ready(self):
        # ログイン/ログアウトのシグナル受信を登録する
        from . import signals  # noqa: F401
