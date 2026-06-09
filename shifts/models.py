from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def generate_time_choices():
    """8:00〜24:00を30分刻みで選択肢にする（"HH:MM"）。"""
    choices = []
    for hour in range(8, 24):
        choices.append((f"{hour:02d}:00", f"{hour:02d}:00"))
        choices.append((f"{hour:02d}:30", f"{hour:02d}:30"))
    choices.append(("24:00", "24:00"))
    return choices


TIME_CHOICES = generate_time_choices()


class ShiftPeriod(models.Model):
    """対象期間。リーダーが作成する募集単位。複数を同時に open にできる。"""

    class Status(models.TextChoices):
        OPEN = "open", "募集中"
        CLOSED = "closed", "締切後"

    class PostDeadlinePolicy(models.TextChoices):
        LOCK_ALL = "lock_all", "締切後は提出・編集とも不可"
        LATE_SUBMIT = "late_submit", "未提出者は提出可・編集は不可"
        EDITABLE = "editable", "締切後も編集可（編集最終期限まで）"

    title = models.CharField("タイトル", max_length=100, blank=True)
    start_date = models.DateField("開始日")
    end_date = models.DateField("終了日")
    deadline = models.DateTimeField("締切日時")
    status = models.CharField(
        "状態", max_length=16, choices=Status.choices, default=Status.OPEN
    )
    post_deadline_policy = models.CharField(
        "締切後の扱い",
        max_length=16,
        choices=PostDeadlinePolicy.choices,
        default=PostDeadlinePolicy.LATE_SUBMIT,
    )
    edit_deadline = models.DateTimeField(
        "編集最終期限",
        null=True,
        blank=True,
        help_text="「締切後も編集可」のとき、ここまで編集可能（自動締切）。空なら手動で締め切るまで編集可。",
    )
    is_visible = models.BooleanField(
        "スタッフに表示",
        default=True,
        help_text="オフにするとスタッフのホームに表示されません（リーダーは管理画面で操作できます）。",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="作成者",
        on_delete=models.PROTECT,
        related_name="created_periods",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "対象期間"
        verbose_name_plural = "対象期間"
        ordering = ["-start_date"]

    def __str__(self):
        return self.title or f"{self.start_date}〜{self.end_date}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "終了日は開始日以降にしてください。"})
        if self.edit_deadline and self.deadline and self.edit_deadline < self.deadline:
            raise ValidationError(
                {"edit_deadline": "編集最終期限は締切日時以降にしてください。"}
            )


class ShiftRequest(models.Model):
    """シフト希望（提出ヘッダ）。(period, user) で1件。行が無い＝未提出。"""

    period = models.ForeignKey(
        ShiftPeriod,
        verbose_name="対象期間",
        on_delete=models.CASCADE,
        related_name="requests",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="提出者",
        on_delete=models.CASCADE,
        related_name="shift_requests",
    )
    note = models.TextField("備考・連絡事項", blank=True)
    submitted_at = models.DateTimeField("最終提出日時", auto_now=True)
    created_at = models.DateTimeField("初回提出日時", auto_now_add=True)

    class Meta:
        verbose_name = "シフト希望"
        verbose_name_plural = "シフト希望"
        constraints = [
            models.UniqueConstraint(
                fields=["period", "user"], name="unique_request_per_user_period"
            )
        ]

    def __str__(self):
        return f"{self.user} / {self.period}"


class ShiftRequestDay(models.Model):
    """各日の希望（1日1枠）。"""

    request = models.ForeignKey(
        ShiftRequest,
        verbose_name="提出",
        on_delete=models.CASCADE,
        related_name="days",
    )
    work_date = models.DateField("対象日")
    is_available = models.BooleanField("出勤可", default=True)
    start_time = models.CharField(
        "開始時刻", max_length=5, null=True, blank=True, choices=TIME_CHOICES
    )
    end_time = models.CharField(
        "終了時刻", max_length=5, null=True, blank=True, choices=TIME_CHOICES
    )

    class Meta:
        verbose_name = "各日の希望"
        verbose_name_plural = "各日の希望"
        ordering = ["work_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "work_date"], name="unique_day_per_request"
            )
        ]

    def __str__(self):
        if not self.is_available:
            return f"{self.work_date}: 不可"
        return f"{self.work_date}: {self.start_time}〜{self.end_time}"

    def clean(self):
        if self.is_available:
            if not self.start_time or not self.end_time:
                raise ValidationError("出勤可の日は開始・終了時刻が必須です。")
            if self.start_time >= self.end_time:
                raise ValidationError("開始時刻は終了時刻より前にしてください。")


class ShiftRequestHistory(models.Model):
    """変更履歴。締切前の変更ごとにスナップショットを残す。"""

    request = models.ForeignKey(
        ShiftRequest,
        verbose_name="提出",
        on_delete=models.CASCADE,
        related_name="histories",
    )
    version_no = models.PositiveIntegerField("バージョン")
    snapshot = models.JSONField("内容スナップショット")
    created_at = models.DateTimeField("変更日時", auto_now_add=True)

    class Meta:
        verbose_name = "変更履歴"
        verbose_name_plural = "変更履歴"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "version_no"], name="unique_version_per_request"
            )
        ]

    def __str__(self):
        return f"{self.request} v{self.version_no}"


class WeeklyFixedShift(models.Model):
    """クルーの曜日別固定シフト。(user, weekday) で1件。

    希望提出フォームの「固定シフトを反映」で、各日付の曜日に対応する内容をコピーする元になる。
    """

    class Weekday(models.IntegerChoices):
        MON = 0, "月"
        TUE = 1, "火"
        WED = 2, "水"
        THU = 3, "木"
        FRI = 4, "金"
        SAT = 5, "土"
        SUN = 6, "日"  # Python の date.weekday()（月=0〜日=6）に合わせる

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="クルー",
        on_delete=models.CASCADE,
        related_name="fixed_shifts",
    )
    weekday = models.IntegerField("曜日", choices=Weekday.choices)
    is_available = models.BooleanField("出勤可", default=True)
    start_time = models.CharField(
        "開始時刻", max_length=5, null=True, blank=True, choices=TIME_CHOICES
    )
    end_time = models.CharField(
        "終了時刻", max_length=5, null=True, blank=True, choices=TIME_CHOICES
    )

    class Meta:
        verbose_name = "固定シフト"
        verbose_name_plural = "固定シフト"
        ordering = ["user", "weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "weekday"], name="unique_fixed_shift_per_weekday"
            )
        ]

    def __str__(self):
        label = self.get_weekday_display()
        if not self.is_available:
            return f"{self.user} {label}: 休み"
        return f"{self.user} {label}: {self.start_time}〜{self.end_time}"

    def clean(self):
        if self.is_available:
            if not self.start_time or not self.end_time:
                raise ValidationError("出勤可の曜日は開始・終了時刻が必須です。")
            if self.start_time >= self.end_time:
                raise ValidationError("開始時刻は終了時刻より前にしてください。")


def confirmed_shift_upload_path(instance, filename):
    return f"confirmed_shifts/period_{instance.period_id}/{filename}"


class ConfirmedShift(models.Model):
    """確定シフトPDF。リーダーがアップロードし、全員が閲覧する。"""

    period = models.ForeignKey(
        ShiftPeriod,
        verbose_name="対象期間",
        on_delete=models.CASCADE,
        related_name="confirmed_shifts",
    )
    file = models.FileField("ファイル", upload_to=confirmed_shift_upload_path)
    original_name = models.CharField("元ファイル名", max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="アップロード者",
        on_delete=models.PROTECT,
        related_name="uploaded_shifts",
    )
    uploaded_at = models.DateTimeField("アップロード日時", auto_now_add=True)

    class Meta:
        verbose_name = "確定シフト"
        verbose_name_plural = "確定シフト"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.period} 確定シフト"
