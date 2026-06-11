"""監査ログの閲覧・検索・PDF/CSV出力（システム管理者のみ）。"""

import csv
from datetime import datetime

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import admin_required
from accounts.models import User

from .models import AuditLog
from .pdf import build_audit_pdf


def _parse_date(value):
    """'YYYY-MM-DD' を date に。不正・空なら None。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _filtered_logs(request):
    """GETパラメータ（操作種別・操作者・日付範囲）でログを絞り込む。"""
    logs = AuditLog.objects.select_related("actor")

    action = (request.GET.get("action") or "").strip()
    if action:
        logs = logs.filter(action=action)

    actor = (request.GET.get("actor") or "").strip()
    if actor.isdigit():
        logs = logs.filter(actor_id=int(actor))

    d_from = _parse_date((request.GET.get("from") or "").strip())
    if d_from:
        logs = logs.filter(created_at__date__gte=d_from)

    d_to = _parse_date((request.GET.get("to") or "").strip())
    if d_to:
        logs = logs.filter(created_at__date__lte=d_to)

    return logs


@admin_required
def audit_log_list(request):
    logs = _filtered_logs(request)
    paginator = Paginator(logs, 50)
    page = paginator.get_page(request.GET.get("page"))

    # ページ送りリンク用に、page以外の検索条件を引き継ぐクエリ文字列
    params = request.GET.copy()
    params.pop("page", None)
    context = {
        "page": page,
        "total": paginator.count,
        "actions": AuditLog.Action.choices,
        "actors": User.objects.order_by("name", "username"),
        "f": {
            "action": (request.GET.get("action") or "").strip(),
            "actor": (request.GET.get("actor") or "").strip(),
            "from": (request.GET.get("from") or "").strip(),
            "to": (request.GET.get("to") or "").strip(),
        },
        "querystring": params.urlencode(),
        "max_rows": AuditLog.MAX_ROWS,
    }
    return render(request, "audit/log_list.html", context)


@admin_required
def audit_log_pdf(request):
    logs = list(_filtered_logs(request))
    pdf_bytes = build_audit_pdf(logs, timezone.localtime())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="audit-log-{stamp}.pdf"'
    return response


@admin_required
def audit_log_csv(request):
    logs = _filtered_logs(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="audit-log-{stamp}.csv"'
    response.write("﻿")  # Excelで文字化けしないよう先頭にBOMを付与

    writer = csv.writer(response)
    writer.writerow(["日時", "操作者", "操作の種類", "内容", "対象", "IPアドレス"])
    for log in logs.iterator():
        writer.writerow([
            timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            log.actor_label,
            log.get_action_display(),
            log.summary,
            log.target,
            log.ip_address or "",
        ])
    return response
