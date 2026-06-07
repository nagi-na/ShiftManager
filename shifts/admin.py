from django.contrib import admin

from .models import (
    ConfirmedShift,
    ShiftPeriod,
    ShiftRequest,
    ShiftRequestDay,
    ShiftRequestHistory,
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
