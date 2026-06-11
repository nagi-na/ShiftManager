"""監査ログの記録ヘルパー。

ビューからは ``log_action(request, action, summary, target="")`` を呼ぶ。
ログイン/ログアウトのシグナルからは ``record(...)`` を直接呼ぶ。
"""

from .models import AuditLog


def client_ip(request):
    """リバースプロキシ(Nginx/Cloudflare)越しでも実IPを拾う。"""
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record(actor, action, summary, target="", ip=None):
    """ログを1件記録し、上限を超えていれば古いものを掃除する。"""
    is_user = bool(actor) and getattr(actor, "is_authenticated", False)
    label = ""
    if actor is not None:
        label = (getattr(actor, "name", "") or getattr(actor, "username", "")) or ""

    AuditLog.objects.create(
        actor=actor if is_user else None,
        actor_label=label[:150],
        action=action,
        summary=(summary or "")[:255],
        target=(target or "")[:255],
        ip_address=ip,
    )
    _prune()


def log_action(request, action, summary, target=""):
    """リクエスト中の操作を記録する（操作者・IPは request から取得）。"""
    record(request.user, action, summary, target, client_ip(request))


def _prune():
    """最新 MAX_ROWS 件だけ残し、古いものを削除する。"""
    count = AuditLog.objects.count()
    if count <= AuditLog.MAX_ROWS:
        return
    old_ids = list(
        AuditLog.objects.order_by("-created_at").values_list("id", flat=True)[AuditLog.MAX_ROWS:]
    )
    if old_ids:
        AuditLog.objects.filter(id__in=old_ids).delete()
