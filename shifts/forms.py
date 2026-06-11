from django import forms
from django.core.exceptions import ValidationError

from .models import (
    TIME_CHOICES,
    Announcement,
    AnnouncementSettings,
    ConfirmedShift,
    ShiftPeriod,
)

# 空（未選択）を先頭に加えた時刻の選択肢
TIME_FIELD_CHOICES = [("", "----")] + TIME_CHOICES

MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB


class ConfirmedShiftForm(forms.ModelForm):
    class Meta:
        model = ConfirmedShift
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "application/pdf"}
            )
        }

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".pdf"):
            raise ValidationError("PDFファイルを選択してください。")
        if f.size > MAX_PDF_SIZE:
            raise ValidationError("ファイルサイズは10MBまでにしてください。")
        return f


class ShiftDayForm(forms.Form):
    """各日の希望（1日1枠）。"""

    work_date = forms.DateField(widget=forms.HiddenInput)
    is_day_off = forms.BooleanField(
        required=False,
        label="休み",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input dayoff-toggle"}),
    )
    start_time = forms.ChoiceField(
        required=False,
        label="開始",
        choices=TIME_FIELD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm time-input"}),
    )
    end_time = forms.ChoiceField(
        required=False,
        label="終了",
        choices=TIME_FIELD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm time-input"}),
    )

    def clean(self):
        cleaned = super().clean()
        # 「休み」にチェックが無い日＝出勤する日なので、時刻が必須。
        if not cleaned.get("is_day_off"):
            start = cleaned.get("start_time")
            end = cleaned.get("end_time")
            if not start or not end:
                raise ValidationError(
                    "出勤する日は開始・終了時刻を選択してください（休みの日は「休み」にチェック）。"
                )
            if start >= end:
                raise ValidationError("開始時刻は終了時刻より前にしてください。")
        return cleaned


class BaseShiftDayFormSet(forms.BaseFormSet):
    """各日フォームの集合検証。隠しフィールド(work_date)の改ざんに備える。

    画面を普通に操作する限り起きないが、POST を細工すると日付の重複（DBのユニーク
    制約に当たって500）や期間外の日付（不正データ）を送れてしまうため、ここで弾く。
    """

    def __init__(self, *args, valid_dates=None, **kwargs):
        # 期間内の日付の集合。None のときは範囲チェックをしない。
        self.valid_dates = set(valid_dates) if valid_dates is not None else None
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            work_date = form.cleaned_data.get("work_date")
            if work_date is None:
                continue
            if work_date in seen:
                raise ValidationError(
                    "同じ日付が重複しています。画面を開き直してから提出してください。"
                )
            seen.add(work_date)
            if self.valid_dates is not None and work_date not in self.valid_dates:
                raise ValidationError(
                    "対象期間外の日付が含まれています。画面を開き直してから提出してください。"
                )


ShiftDayFormSet = forms.formset_factory(
    ShiftDayForm, formset=BaseShiftDayFormSet, extra=0
)


class FixedShiftDayForm(forms.Form):
    """曜日ごとの固定シフト（1曜日1枠）。ShiftDayForm の曜日版。"""

    weekday = forms.IntegerField(widget=forms.HiddenInput)
    is_day_off = forms.BooleanField(
        required=False,
        label="休み",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input dayoff-toggle"}),
    )
    start_time = forms.ChoiceField(
        required=False,
        label="開始",
        choices=TIME_FIELD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm time-input"}),
    )
    end_time = forms.ChoiceField(
        required=False,
        label="終了",
        choices=TIME_FIELD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm time-input"}),
    )

    def clean(self):
        cleaned = super().clean()
        # 「休み」でない曜日＝出勤する曜日なので、時刻が必須。
        if not cleaned.get("is_day_off"):
            start = cleaned.get("start_time")
            end = cleaned.get("end_time")
            if not start or not end:
                raise ValidationError(
                    "出勤する曜日は開始・終了時刻を選択してください（休みの曜日は「休み」にチェック）。"
                )
            if start >= end:
                raise ValidationError("開始時刻は終了時刻より前にしてください。")
        return cleaned


class BaseFixedShiftFormSet(forms.BaseFormSet):
    """曜日フォームの集合検証。隠しフィールド(weekday)の改ざんに備える。

    曜日の重複（ユニーク制約に当たって500）や範囲外（0〜6以外）の値を弾く。
    特に変更申請の payload は、後でリーダーが承認した瞬間に反映されるため、
    作成時点で正しい曜日だけを通しておく。
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            weekday = form.cleaned_data.get("weekday")
            if weekday is None:
                continue
            if weekday not in range(7):
                raise ValidationError("曜日の値が不正です。画面を開き直してください。")
            if weekday in seen:
                raise ValidationError(
                    "同じ曜日が重複しています。画面を開き直してください。"
                )
            seen.add(weekday)


FixedShiftFormSet = forms.formset_factory(
    FixedShiftDayForm, formset=BaseFixedShiftFormSet, extra=0
)


class PeriodForm(forms.ModelForm):
    """対象期間の作成・編集（S7）。"""

    class Meta:
        model = ShiftPeriod
        fields = [
            "title",
            "start_date",
            "end_date",
            "deadline",
            "status",
            "post_deadline_policy",
            "edit_deadline",
            "is_visible",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例: 6/9〜6/15分"}
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
            "deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "post_deadline_policy": forms.Select(attrs={"class": "form-select"}),
            "edit_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "is_visible": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # HTML の date / datetime-local 入力を受け取れるようにする
        self.fields["start_date"].input_formats = ["%Y-%m-%d"]
        self.fields["end_date"].input_formats = ["%Y-%m-%d"]
        self.fields["deadline"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["edit_deadline"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["edit_deadline"].required = False


class NoteForm(forms.Form):
    note = forms.CharField(
        required=False,
        label="備考・連絡事項",
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )


class AnnouncementForm(forms.ModelForm):
    """アナウンスの手動投稿（タイトル・レベル・本文。添付はビューで request.FILES から処理）。"""

    class Meta:
        model = Announcement
        fields = ["title", "level", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "level": forms.Select(attrs={"class": "form-select"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class AnnouncementSettingsForm(forms.ModelForm):
    """自動投稿のオンオフ設定。"""

    class Meta:
        model = AnnouncementSettings
        fields = ["auto_on_period"]
        widgets = {
            "auto_on_period": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
