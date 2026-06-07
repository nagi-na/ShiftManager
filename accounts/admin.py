from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """カスタムUser用の管理画面。パスワードはハッシュ化して保存される。"""

    list_display = ("username", "name", "role", "email", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "name", "email")

    # 既存の UserAdmin.fieldsets に name / role を追加
    fieldsets = BaseUserAdmin.fieldsets + (
        ("アプリ情報", {"fields": ("name", "role")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("アプリ情報", {"fields": ("name", "role", "email")}),
    )
