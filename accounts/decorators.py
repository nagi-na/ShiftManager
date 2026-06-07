from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def manager_required(view):
    """ログイン済み かつ 管理権限（システム管理者 または リーダー）のみ許可。"""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.can_manage:
            messages.error(request, "この画面は管理権限が必要です。")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapper


def admin_required(view):
    """ログイン済み かつ システム管理者のみ許可（アカウント管理用）。"""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.can_manage_accounts:
            messages.error(request, "この画面はシステム管理者のみ利用できます。")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapper
