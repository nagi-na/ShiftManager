from django.contrib import admin

from .models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementSettings,
    ConfirmedShift,
    FixedShiftChangeRequest,
    ShiftPeriod,
    ShiftRequest,
    ShiftRequestDay,
    ShiftRequestHistory,
    WeeklyFixedShift,
)


@admin.register(ShiftPeriod)
class ShiftPeriodAdmin(admin.ModelAdmin):
    list_display = ("__str__", "start_date", "end_date", "deadline", "status", "created_by")
    list_filter = ("status",)
    date_hierarchy = "start_date"


class ShiftRequestDayInline(admin.TabularInline):
    model = ShiftRequestDay
    extra = 0


@admin.register(ShiftRequest)
class ShiftRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "period", "submitted_at")
    list_filter = ("period",)
    search_fields = ("user__username", "user__name")
    inlines = [ShiftRequestDayInline]


@admin.register(ShiftRequestHistory)
class ShiftRequestHistoryAdmin(admin.ModelAdmin):
    list_display = ("request", "version_no", "created_at")


@admin.register(ConfirmedShift)
class ConfirmedShiftAdmin(admin.ModelAdmin):
    list_display = ("period", "original_name", "uploaded_by", "uploaded_at")


@admin.register(WeeklyFixedShift)
class WeeklyFixedShiftAdmin(admin.ModelAdmin):
    list_display = ("user", "get_weekday_display", "is_available", "start_time", "end_time")
    list_filter = ("weekday", "is_available")
    search_fields = ("user__username", "user__name")


@admin.register(FixedShiftChangeRequest)
class FixedShiftChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created_at", "reviewer", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__name")


class AnnouncementAttachmentInline(admin.TabularInline):
    model = AnnouncementAttachment
    extra = 0


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "level", "created_by", "created_at")
    list_filter = ("category", "level")
    inlines = [AnnouncementAttachmentInline]


@admin.register(AnnouncementSettings)
class AnnouncementSettingsAdmin(admin.ModelAdmin):
    list_display = ("auto_on_period",)
