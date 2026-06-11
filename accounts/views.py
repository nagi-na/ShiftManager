from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string

from .decorators import admin_required
from .forms import AccountCreateForm, AccountEditForm, ProfileEmailForm
from .models import User

# 紛らわしい文字（0/O/1/l/I など）を除いた、配布しやすい文字集合
_PW_CHARS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_password(length: int = 10) -> str:
    """配布用の初期パスワードを自動生成する。"""
    return get_random_string(length, _PW_CHARS)


@admin_required
def account_list(request):
    """S6 アカウント一覧＋新規作成（初期パスワードは自動発行）。"""
    if request.method == "POST":
        form = AccountCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            password = generate_password()
            user.set_password(password)
            user.save()
            messages.success(
                request,
                f"アカウント「{user.name}」を作成しました。"
                f"初期パスワード: {password} （本人に伝えてください。この画面でのみ表示されます）",
            )
            return redirect("manage_accounts")
    else:
        form = AccountCreateForm(initial={"role": User.Role.CREW})

    users = User.objects.order_by("role", "name", "username")
    return render(
        request, "accounts/account_list.html", {"users": users, "form": form}
    )


@admin_required
def account_edit(request, pk):
    """アカウントの編集。"""
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = AccountEditForm(request.POST, instance=target)
        if form.is_valid():
            # 自分自身の「有効」「システム管理者権限」は外せない（ロックアウト防止）
            if target == request.user and (
                not form.cleaned_data["is_active"]
                or form.cleaned_data["role"] != User.Role.ADMIN
            ):
                messages.error(
                    request, "自分自身の『有効』『システム管理者権限』は変更できません。"
                )
            else:
                form.save()
                messages.success(request, "アカウントを更新しました。")
                return redirect("manage_accounts")
    else:
        form = AccountEditForm(instance=target)
    return render(request, "accounts/account_edit.html", {"target": target, "form": form})


@admin_required
def account_reset_password(request, pk):
    """パスワードを自動再発行する。"""
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        # 自分自身に再発行すると認証ハッシュが変わり即ログアウトされ、
        # 表示された新パスワードを見逃すと自分で復旧できなくなる。
        if target == request.user:
            messages.error(
                request,
                "自分自身のパスワードはここでは再発行できません。"
                "設定画面の「パスワード変更」から変更してください。",
            )
            return redirect("manage_account_edit", pk=pk)
        password = generate_password()
        target.set_password(password)
        target.save(update_fields=["password"])
        messages.success(
            request,
            f"「{target.name}」のパスワードを再発行しました。"
            f"新パスワード: {password} （本人に伝えてください）",
        )
    return redirect("manage_account_edit", pk=pk)


@admin_required
def account_toggle_active(request, pk):
    """有効/無効の切り替え。"""
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        if target == request.user:
            messages.error(request, "自分自身は無効化できません。")
        else:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            state = "有効" if target.is_active else "無効"
            messages.success(request, f"「{target.name}」を{state}にしました。")
    return redirect("manage_accounts")


@admin_required
def account_toggle_fixed_edit(request, pk):
    """このクルー本人による固定シフト編集の許可/不許可を切り替える。"""
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        target.fixed_shift_editable_by_crew = not target.fixed_shift_editable_by_crew
        target.save(update_fields=["fixed_shift_editable_by_crew"])
        state = "許可" if target.fixed_shift_editable_by_crew else "不許可"
        messages.success(
            request, f"「{target.name}」の固定シフト本人編集を{state}にしました。"
        )
    return redirect("manage_accounts")


@admin_required
def account_bulk_fixed_edit(request):
    """全クルーの固定シフト本人編集を一括で許可/不許可にする。"""
    if request.method == "POST":
        enable = request.POST.get("enable") == "1"
        n = User.objects.filter(role=User.Role.CREW).update(
            fixed_shift_editable_by_crew=enable
        )
        state = "許可" if enable else "不許可"
        messages.success(
            request, f"全クルー {n} 名の固定シフト本人編集を{state}にしました。"
        )
    return redirect("manage_accounts")


@admin_required
def account_delete(request, pk):
    """アカウントの削除。自分自身・データ作成者は削除不可。"""
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        if target == request.user:
            messages.error(request, "自分自身は削除できません。")
        elif target.created_periods.exists() or target.uploaded_shifts.exists():
            messages.error(
                request,
                "この利用者は期間の作成や確定シフトのアップロード履歴があるため削除できません。"
                "代わりに無効化してください。",
            )
        else:
            name = target.name or target.username
            target.delete()  # 提出データ（ShiftRequest等）は一緒に削除される
            messages.success(request, f"アカウント「{name}」を削除しました。")
    return redirect("manage_accounts")


@login_required
def profile(request):
    """スタッフ自身の設定（メール登録・変更）。ログインIDは変更不可。"""
    if request.method == "POST":
        form = ProfileEmailForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "メールアドレスを更新しました。")
            return redirect("profile")
    else:
        form = ProfileEmailForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})
