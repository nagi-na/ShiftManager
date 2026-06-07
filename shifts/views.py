from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import manager_required
from accounts.models import User

from .forms import ConfirmedShiftForm, NoteForm, PeriodForm, ShiftDayFormSet
from .models import (
    ConfirmedShift,
    ShiftPeriod,
    ShiftRequest,
    ShiftRequestDay,
    ShiftRequestHistory,
)

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


@login_required
def home(request):
    """S2 ホーム（対象期間選択）。"""
    now = timezone.now()
    # スタッフに表示する期間のみ（非表示はホームに出さない）
    periods = list(ShiftPeriod.objects.filter(is_visible=True))

    if request.user.can_manage:
        items = [
            {
                "period": p,
                "is_closed": _is_closed(p, now),
                "manually_closed": _manually_closed(p, now),
            }
            for p in periods
        ]
        return render(request, "shifts/home.html", {"items": items, "is_manager": True})

    submitted_period_ids = set(
        ShiftRequest.objects.filter(user=request.user).values_list("period_id", flat=True)
    )
    items = []
    for p in periods:
        submitted = p.id in submitted_period_ids
        is_closed = _is_closed(p, now)
        can_submit_new, can_edit = _submission_permission(p, now, submitted)
        # このユーザーが今この期間に対して操作（提出 or 編集）できるか
        can_act = can_edit if submitted else can_submit_new
        items.append(
            {
                "period": p,
                "submitted": submitted,
                "is_closed": is_closed,
                "can_submit": can_act,
                "manually_closed": _manually_closed(p, now),
            }
        )
    return render(request, "shifts/home.html", {"items": items, "is_manager": False})


@login_required
def shift_submit(request, pk):
    """S3 シフト提出画面。各日1枠の希望を入力・保存する。"""
    period = get_object_or_404(ShiftPeriod, pk=pk)
    now = timezone.now()

    # 非表示の期間はクルーからアクセス不可（管理者・リーダーは確認用に閲覧可）
    if not period.is_visible and not request.user.can_manage:
        messages.error(request, "この期間は現在表示されていません。")
        return redirect("home")

    is_closed = _is_closed(period, now)

    req = ShiftRequest.objects.filter(period=period, user=request.user).first()
    submitted = req is not None
    can_submit_new, can_edit = _submission_permission(period, now, submitted)
    # 提出済みなら編集可否、未提出なら新規提出可否で、編集できるかを判定
    editable = can_edit if submitted else can_submit_new
    read_only = not editable

    dates = _date_range(period.start_date, period.end_date)

    if request.method == "POST" and not read_only:
        formset = ShiftDayFormSet(request.POST, prefix="day")
        note_form = NoteForm(request.POST)
        if formset.is_valid() and note_form.is_valid():
            _save_submission(request.user, period, formset, note_form)
            messages.success(request, "シフト希望を保存しました。")
            return redirect("home")
    else:
        existing = {d.work_date: d for d in req.days.all()} if req else {}
        initial = [
            {
                "work_date": dt,
                # 既存が「出勤不可」なら休みにチェック。新規日は出勤(チェック無し)が既定。
                "is_day_off": (not existing[dt].is_available) if dt in existing else False,
                "start_time": existing[dt].start_time if dt in existing else None,
                "end_time": existing[dt].end_time if dt in existing else None,
            }
            for dt in dates
        ]
        formset = ShiftDayFormSet(initial=initial, prefix="day")
        note_form = NoteForm(initial={"note": req.note if req else ""})

    if read_only:
        for form in formset.forms:
            for field in form.fields.values():
                field.widget.attrs["disabled"] = True
        note_form.fields["note"].widget.attrs["disabled"] = True

    rows = [
        {"form": form, "date": dt, "weekday": WEEKDAYS_JP[dt.weekday()]}
        for form, dt in zip(formset.forms, dates)
    ]
    context = {
        "period": period,
        "formset": formset,
        "note_form": note_form,
        "rows": rows,
        "read_only": read_only,
        "is_closed": is_closed,
        "manually_closed": _manually_closed(period, now),
        "submitted": submitted,
        "request_obj": req,
        "notice": _submit_notice(period, now, submitted, read_only),
    }
    return render(request, "shifts/submit.html", context)


def _submit_notice(period, now, submitted, read_only):
    """提出画面に出す案内（(bootstrapレベル, 文言) のタプル）。無ければ None。"""
    Policy = ShiftPeriod.PostDeadlinePolicy
    past_deadline = now >= period.deadline and period.status != ShiftPeriod.Status.CLOSED

    if read_only:
        if submitted:
            return ("secondary", "締切済みのため、内容は閲覧のみです（編集できません）。")
        return ("secondary", "締切済みのため、新規提出はできません。")

    if past_deadline:
        if period.post_deadline_policy == Policy.EDITABLE:
            if period.edit_deadline:
                limit = timezone.localtime(period.edit_deadline).strftime("%Y/%m/%d %H:%M")
                return ("info", f"締切後ですが、編集最終期限（{limit}）まで編集できます。")
            return ("info", "締切後ですが、管理者が締め切るまで編集できます。")
        if period.post_deadline_policy == Policy.LATE_SUBMIT:
            return ("info", "締切を過ぎていますが、未提出のため提出できます（提出後の編集は不可）。")
    return None


def _save_submission(user, period, formset, note_form):
    """提出内容を保存し、変更履歴スナップショットを1件追加する。"""
    with transaction.atomic():
        req, _ = ShiftRequest.objects.get_or_create(period=period, user=user)
        req.note = note_form.cleaned_data["note"]
        req.save()

        req.days.all().delete()
        day_objs = []
        for form in formset:
            cd = form.cleaned_data
            avail = not cd.get("is_day_off", False)
            day_objs.append(
                ShiftRequestDay(
                    request=req,
                    work_date=cd["work_date"],
                    is_available=avail,
                    start_time=cd.get("start_time") if avail else None,
                    end_time=cd.get("end_time") if avail else None,
                )
            )
        ShiftRequestDay.objects.bulk_create(day_objs)

        last = req.histories.order_by("-version_no").first()
        version_no = (last.version_no + 1) if last else 1
        snapshot = {
            "note": req.note,
            "days": [
                {
                    "work_date": d.work_date.isoformat(),
                    "is_available": d.is_available,
                    "start_time": d.start_time or None,
                    "end_time": d.end_time or None,
                }
                for d in day_objs
            ],
        }
        ShiftRequestHistory.objects.create(
            request=req, version_no=version_no, snapshot=snapshot
        )


@login_required
def period_status(request, pk):
    """S4 提出状況一覧。管理者・リーダーが全クルー×各日を表で確認する。"""
    if not request.user.can_manage:
        messages.error(request, "この画面は管理権限が必要です。")
        return redirect("home")

    period = get_object_or_404(ShiftPeriod, pk=pk)
    dates = _date_range(period.start_date, period.end_date)

    staff_list = User.objects.filter(
        role=User.Role.CREW, is_active=True
    ).order_by("name", "username")

    requests = {
        r.user_id: r
        for r in ShiftRequest.objects.filter(period=period).prefetch_related("days")
    }

    table = []
    for staff in staff_list:
        req = requests.get(staff.id)
        if req:
            days_map = {d.work_date: d for d in req.days.all()}
            cells = [days_map.get(dt) for dt in dates]
            table.append(
                {"staff": staff, "submitted": True, "cells": cells, "request": req}
            )
        else:
            table.append(
                {
                    "staff": staff,
                    "submitted": False,
                    "cells": [None] * len(dates),
                    "request": None,
                }
            )

    submitted_count = sum(1 for row in table if row["submitted"])
    date_headers = [{"date": dt, "weekday": WEEKDAYS_JP[dt.weekday()]} for dt in dates]

    context = {
        "period": period,
        "date_headers": date_headers,
        "table": table,
        "submitted_count": submitted_count,
        "total_count": len(table),
    }
    return render(request, "shifts/status.html", context)


@login_required
def request_history(request, pk):
    """変更履歴の閲覧。リーダー、または本人のみ。"""
    req = get_object_or_404(ShiftRequest.objects.select_related("user", "period"), pk=pk)
    if not request.user.can_manage and req.user_id != request.user.id:
        messages.error(request, "この履歴を閲覧する権限がありません。")
        return redirect("home")

    histories = list(req.histories.all())  # version_no 降順
    return render(
        request,
        "shifts/history.html",
        {"req": req, "histories": histories},
    )


@login_required
def confirmed_shift(request, pk):
    """S5 確定シフト閲覧。全員が閲覧、リーダーはアップロード・削除ができる。"""
    period = get_object_or_404(ShiftPeriod, pk=pk)
    form = ConfirmedShiftForm()

    if request.method == "POST":
        if not request.user.can_manage:
            messages.error(request, "アップロード/削除は管理権限が必要です。")
            return redirect("confirmed_shift", pk=pk)

        # 削除
        delete_id = request.POST.get("delete_id")
        if delete_id:
            cs = period.confirmed_shifts.filter(pk=delete_id).first()
            if cs:
                cs.file.delete(save=False)
                cs.delete()
                messages.success(request, "確定シフトを削除しました。")
            return redirect("confirmed_shift", pk=pk)

        # アップロード
        form = ConfirmedShiftForm(request.POST, request.FILES)
        if form.is_valid():
            cs = form.save(commit=False)
            cs.period = period
            cs.uploaded_by = request.user
            cs.original_name = form.cleaned_data["file"].name
            cs.save()
            messages.success(request, "確定シフトをアップロードしました。")
            return redirect("confirmed_shift", pk=pk)

    files = period.confirmed_shifts.all()
    return render(
        request,
        "shifts/confirmed.html",
        {"period": period, "files": files, "form": form},
    )


@manager_required
def manage_top(request):
    """S8 リーダー用トップ（管理メニュー）。"""
    now = timezone.now()
    staff_count = User.objects.filter(
        role=User.Role.CREW, is_active=True
    ).count()
    open_count = sum(1 for p in ShiftPeriod.objects.all() if not _is_closed(p, now))
    return render(
        request,
        "shifts/manage_top.html",
        {"staff_count": staff_count, "open_count": open_count},
    )


@manager_required
def manage_periods(request):
    """S7 期間・締切設定（一覧＋新規作成）。"""
    if request.method == "POST":
        form = PeriodForm(request.POST)
        if form.is_valid():
            period = form.save(commit=False)
            period.created_by = request.user
            period.save()
            messages.success(request, "対象期間を作成しました。")
            return redirect("manage_periods")
    else:
        form = PeriodForm()

    now = timezone.now()
    items = [
        {
            "period": p,
            "is_closed": _is_closed(p, now),
            "manually_closed": _manually_closed(p, now),
            "request_count": p.requests.count(),
        }
        for p in ShiftPeriod.objects.all()
    ]
    return render(request, "shifts/manage_periods.html", {"items": items, "form": form})


@manager_required
def manage_period_toggle_visible(request, pk):
    """スタッフへの表示/非表示を切り替える。"""
    period = get_object_or_404(ShiftPeriod, pk=pk)
    if request.method == "POST":
        period.is_visible = not period.is_visible
        period.save(update_fields=["is_visible"])
        state = "表示" if period.is_visible else "非表示"
        messages.success(request, f"「{period}」をスタッフに{state}にしました。")
    return redirect("manage_periods")


@manager_required
def manage_period_edit(request, pk):
    """対象期間の編集。"""
    period = get_object_or_404(ShiftPeriod, pk=pk)
    if request.method == "POST":
        form = PeriodForm(request.POST, instance=period)
        if form.is_valid():
            form.save()
            messages.success(request, "対象期間を更新しました。")
            return redirect("manage_periods")
    else:
        form = PeriodForm(instance=period)
    return render(
        request, "shifts/manage_period_edit.html", {"form": form, "period": period}
    )


@manager_required
def manage_period_close(request, pk):
    """募集中⇔締切 を手動で切り替える。"""
    period = get_object_or_404(ShiftPeriod, pk=pk)
    if request.method == "POST":
        if period.status == ShiftPeriod.Status.CLOSED:
            period.status = ShiftPeriod.Status.OPEN
            msg = "募集中に戻しました。"
        else:
            period.status = ShiftPeriod.Status.CLOSED
            msg = "締め切りました。"
        period.save(update_fields=["status"])
        messages.success(request, msg)
    return redirect("manage_periods")


@manager_required
def manage_period_delete(request, pk):
    """対象期間の削除。提出・確定シフトも一緒に削除される（警告のうえ実行）。"""
    period = get_object_or_404(ShiftPeriod, pk=pk)
    if request.method == "POST":
        count = period.requests.count()
        # 物理ファイル（確定シフトPDF）を先に削除してから期間を削除
        for cs in period.confirmed_shifts.all():
            cs.file.delete(save=False)
        title = str(period)
        period.delete()
        if count:
            messages.success(
                request, f"「{title}」と提出 {count} 件を削除しました。"
            )
        else:
            messages.success(request, f"「{title}」を削除しました。")
    return redirect("manage_periods")


def _is_closed(period, now) -> bool:
    """締切扱いか。明示的にclosed、または締切日時を過ぎていれば締切とみなす。"""
    return period.status == ShiftPeriod.Status.CLOSED or period.deadline < now


def _manually_closed(period, now) -> bool:
    """締切日時より前なのに、管理者が手動で締め切った状態か。"""
    return period.status == ShiftPeriod.Status.CLOSED and period.deadline >= now


def _submission_permission(period, now, submitted):
    """締切後ポリシーを踏まえ、(新規提出できるか, 既存を編集できるか) を返す。"""
    Policy = ShiftPeriod.PostDeadlinePolicy

    # 手動締切（status=closed）は常に全面クローズ
    if period.status == ShiftPeriod.Status.CLOSED:
        return (False, False)
    # 締切前は誰でも提出・編集可能
    if now < period.deadline:
        return (True, True)

    # ここから締切後（締切日時を過ぎ、手動締切はされていない）
    policy = period.post_deadline_policy
    if policy == Policy.LOCK_ALL:
        return (False, False)
    if policy == Policy.LATE_SUBMIT:
        return (not submitted, False)  # 未提出者のみ提出可・編集は不可
    if policy == Policy.EDITABLE:
        if period.edit_deadline:  # 自動：編集最終期限まで
            return (now < period.edit_deadline, now < period.edit_deadline)
        return (True, True)  # 手動：締め切るまで編集・提出可
    return (False, False)


def _date_range(start, end):
    """start〜end（両端含む）の日付リスト。"""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
