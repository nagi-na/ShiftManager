"""ログイン・ログアウトを監査ログに記録する。"""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import AuditLog
from .utils import client_ip, record


@receiver(user_logged_in)
def on_logged_in(sender, request, user, **kwargs):
    record(user, AuditLog.Action.LOGIN, "ログインしました", ip=client_ip(request))


@receiver(user_logged_out)
def on_logged_out(sender, request, user, **kwargs):
    if user is not None:  # 未ログインでのログアウト呼び出しは無視
        record(user, AuditLog.Action.LOGOUT, "ログアウトしました", ip=client_ip(request))
