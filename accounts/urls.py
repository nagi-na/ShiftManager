from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    # スタッフ自身の設定（メール変更・パスワード変更）
    path("profile/", views.profile, name="profile"),
    path(
        "profile/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url=reverse_lazy("password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "profile/password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("manage/accounts/", views.account_list, name="manage_accounts"),
    path("manage/accounts/<int:pk>/edit/", views.account_edit, name="manage_account_edit"),
    path(
        "manage/accounts/<int:pk>/reset-password/",
        views.account_reset_password,
        name="manage_account_reset",
    ),
    path(
        "manage/accounts/<int:pk>/toggle-active/",
        views.account_toggle_active,
        name="manage_account_toggle",
    ),
    path(
        "manage/accounts/<int:pk>/delete/",
        views.account_delete,
        name="manage_account_delete",
    ),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
