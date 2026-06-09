from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("periods/<int:pk>/submit/", views.shift_submit, name="shift_submit"),
    path("periods/<int:pk>/status/", views.period_status, name="period_status"),
    path("requests/<int:pk>/history/", views.request_history, name="request_history"),
    path("periods/<int:pk>/confirmed/", views.confirmed_shift, name="confirmed_shift"),
    path("confirmed-files/<int:pk>/", views.confirmed_shift_file, name="confirmed_shift_file"),
    # 固定シフト（曜日別デフォルト）
    path("fixed-shift/", views.my_fixed_shift, name="my_fixed_shift"),
    # 管理系（リーダー専用）
    path("manage/", views.manage_top, name="manage_top"),
    path("manage/fixed-shifts/", views.manage_fixed_shifts, name="manage_fixed_shifts"),
    path("manage/fixed-shifts/<int:user_pk>/edit/", views.manage_fixed_shift_edit, name="manage_fixed_shift_edit"),
    path("manage/periods/", views.manage_periods, name="manage_periods"),
    path("manage/periods/<int:pk>/edit/", views.manage_period_edit, name="manage_period_edit"),
    path("manage/periods/<int:pk>/close/", views.manage_period_close, name="manage_period_close"),
    path("manage/periods/<int:pk>/visibility/", views.manage_period_toggle_visible, name="manage_period_toggle_visible"),
    path("manage/periods/<int:pk>/delete/", views.manage_period_delete, name="manage_period_delete"),
]
