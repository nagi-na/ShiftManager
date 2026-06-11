from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """予備の確認用。基本はアプリ内の専用画面を使う。閲覧のみ（追加/編集不可）。"""

    list_display = ("created_at", "actor_label", "action", "summary", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("actor_label", "summary", "target")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
