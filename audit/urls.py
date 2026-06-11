from django.urls import path

from . import views

urlpatterns = [
    path("manage/logs/", views.audit_log_list, name="audit_log_list"),
    path("manage/logs/pdf/", views.audit_log_pdf, name="audit_log_pdf"),
    path("manage/logs/csv/", views.audit_log_csv, name="audit_log_csv"),
]
