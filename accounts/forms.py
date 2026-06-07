from django import forms

from .models import User

_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class AccountCreateForm(forms.ModelForm):
    """スタッフ等のアカウント新規作成。パスワードは作成時に自動発行する。"""

    class Meta:
        model = User
        fields = ["username", "name", "email", "role"]
        widgets = {
            "username": forms.TextInput(attrs=_TEXT),
            "name": forms.TextInput(attrs=_TEXT),
            "email": forms.EmailInput(attrs=_TEXT),
            "role": forms.Select(attrs=_SELECT),
        }
        labels = {"username": "ログインID"}


class AccountEditForm(forms.ModelForm):
    """アカウントの編集（ログインID・名前・メール・ロール・状態）。"""

    class Meta:
        model = User
        fields = ["username", "name", "email", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs=_TEXT),
            "name": forms.TextInput(attrs=_TEXT),
            "email": forms.EmailInput(attrs=_TEXT),
            "role": forms.Select(attrs=_SELECT),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {"username": "ログインID", "is_active": "有効"}


class ProfileEmailForm(forms.ModelForm):
    """スタッフ自身によるメールアドレスの登録・変更（IDは変更不可）。"""

    class Meta:
        model = User
        fields = ["email"]
        widgets = {"email": forms.EmailInput(attrs=_TEXT)}
        labels = {"email": "メールアドレス"}
