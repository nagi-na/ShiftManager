import mimetypes
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import manager_required
from accounts.models import User

from .forms import (
    AnnouncementForm,
    AnnouncementSettingsForm,
    ConfirmedShiftForm,
    FixedShiftFormSet,
    NoteForm,
    PeriodForm,
    ShiftDayFormSet,
)
from .models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementRead,
    AnnouncementSettings,
    ConfirmedShift,
    FixedShiftChangeRequest,
    ShiftPeriod,
    ShiftRequest,
    ShiftRequestDay,
    ShiftRequestHistory,
    WeeklyFixedShift,
)

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


@login_required
def home(request):
    """S2 ホーム（対象期間選択）。"""
    now = timezone.now()
    _prune_old_announcements()
    unread = _unread_announcement_count(request.user)
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
        return render(
            request,
            "shifts/home.html",
            {"items": items, "is_manager": True, "unread_announcements": unread},
        )

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
    return render(
        request,
        "shifts/home.html",
        {"items": items, "is_manager": False, "unread_announcements": unread},
    )


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
        {
            "form": form,
            "date": dt,
            "weekday": WEEKDAYS_JP[dt.weekday()],
            "weekday_idx": dt.weekday(),
        }
        for form, dt in zip(formset.forms, dates)
    ]

    # 「固定シフトを反映」ボタン用：このユーザーの曜日別固定シフトを曜日→内容で渡す
    fixed_map = {ws.weekday: ws for ws in request.user.fixed_shifts.all()}
    fixed_shift_json = {
        str(wd): (
            {"off": True}
            if not ws.is_available
            else {"off": False, "start": ws.start_time, "end": ws.end_time}
        )
        for wd, ws in fixed_map.items()
    }

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
        "fixed_shift_json": fixed_shift_json,
        "has_fixed_shift": bool(fixed_map),
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


# ----- 固定シフト（曜日別デフォルト） -----

def _fixed_shift_initial(user):
    """ユーザーの固定シフトを、月〜日(0〜6)の順でフォーム初期値にする。"""
    existing = {ws.weekday: ws for ws in user.fixed_shifts.all()}
    initial = []
    for wd in range(7):
        ws = existing.get(wd)
        initial.append(
            {
                "weekday": wd,
                "is_day_off": (not ws.is_available) if ws else False,
                "start_time": ws.start_time if ws else None,
                "end_time": ws.end_time if ws else None,
            }
        )
    return initial


def _save_fixed_shift(user, formset):
    """固定シフトを保存（全削除→作り直し）。"""
    with transaction.atomic():
        user.fixed_shifts.all().delete()
        objs = []
        for form in formset:
            cd = form.cleaned_data
            avail = not cd.get("is_day_off", False)
            objs.append(
                WeeklyFixedShift(
                    user=user,
                    weekday=cd["weekday"],
                    is_available=avail,
                    start_time=cd.get("start_time") if avail else None,
                    end_time=cd.get("end_time") if avail else None,
                )
            )
        WeeklyFixedShift.objects.bulk_create(objs)


def _fixed_shift_rows(formset):
    """テンプレート表示用に (曜日名, form) を並べる。"""
    return [
        {"form": form, "weekday": WEEKDAYS_JP[i]}
        for i, form in enumerate(formset.forms)
    ]


def _formset_to_payload(formset):
    """固定シフトのフォームセットを、保存/申請用の payload（曜日順の辞書リスト）にする。"""
    payload = []
    for form in formset:
        cd = form.cleaned_data
        avail = not cd.get("is_day_off", False)
        payload.append(
            {
                "weekday": cd["weekday"],
                "is_available": avail,
                "start_time": cd.get("start_time") if avail else None,
                "end_time": cd.get("end_time") if avail else None,
            }
        )
    return payload


def _payload_to_initial(payload):
    """payload（辞書リスト）をフォームセットの初期値（月〜日順）に変換する。"""
    by_wd = {d["weekday"]: d for d in payload}
    initial = []
    for wd in range(7):
        d = by_wd.get(wd)
        initial.append(
            {
                "weekday": wd,
                "is_day_off": (not d["is_available"]) if d else False,
                "start_time": d["start_time"] if d else None,
                "end_time": d["end_time"] if d else None,
            }
        )
    return initial


def _payload_rows(payload):
    """payload を表示用に (曜日名, 内容) で並べる（承認画面の比較表示など）。"""
    by_wd = {d["weekday"]: d for d in payload}
    rows = []
    for wd in range(7):
        d = by_wd.get(wd)
        rows.append({"weekday": WEEKDAYS_JP[wd], "data": d})
    return rows


def _prune_processed_requests(user, keep=10):
    """ユーザーの処理済み（承認/却下）申請を新しい順に keep 件だけ残し、古いものを削除する。"""
    processed = (
        user.fixed_shift_requests.exclude(
            status=FixedShiftChangeRequest.Status.PENDING
        )
        .order_by("-created_at")
        .values_list("id", flat=True)
    )
    old_ids = list(processed[keep:])  # 11件目以降（古い側）
    if old_ids:
        FixedShiftChangeRequest.objects.filter(id__in=old_ids).delete()


def _apply_payload(user, payload):
    """payload の内容で、ユーザーの固定シフトを全置換する。"""
    with transaction.atomic():
        user.fixed_shifts.all().delete()
        WeeklyFixedShift.objects.bulk_create(
            [
                WeeklyFixedShift(
                    user=user,
                    weekday=d["weekday"],
                    is_available=d["is_available"],
                    start_time=d["start_time"],
                    end_time=d["end_time"],
                )
                for d in payload
            ]
        )


@login_required
def my_fixed_shift(request):
    """クルー本人の固定シフトページ。

    - 直接編集を許可されている → その場で保存（mode="edit"）。
    - 許可されていないクルー → 変更を申請（mode="request"）。リーダー承認で反映。
    """
    user = request.user
    editable = user.can_edit_fixed_shift_of(user)
    mode = "edit" if editable else "request"
    pending = user.fixed_shift_requests.filter(
        status=FixedShiftChangeRequest.Status.PENDING
    ).first()
    # 直近の処理済み申請（リーダーのコメント表示用）
    last_reviewed = (
        user.fixed_shift_requests.exclude(
            status=FixedShiftChangeRequest.Status.PENDING
        ).first()
    )

    # 申請モードで保留中は読み取り専用（取り消してから新規申請する）
    locked = mode == "request" and pending is not None
    crew_comment = pending.crew_comment if (pending and locked) else ""

    if request.method == "POST" and not locked:
        formset = FixedShiftFormSet(request.POST, prefix="fx")
        crew_comment = request.POST.get("crew_comment", "").strip()
        if formset.is_valid():
            payload = _formset_to_payload(formset)
            if mode == "edit":
                _apply_payload(user, payload)
                messages.success(request, "固定シフトを保存しました。")
            else:
                FixedShiftChangeRequest.objects.create(
                    user=user, payload=payload, crew_comment=crew_comment
                )
                messages.success(request, "固定シフトの変更を申請しました。承認をお待ちください。")
            return redirect("my_fixed_shift")
    else:
        if locked:
            initial = _payload_to_initial(pending.payload)  # 申請内容を読み取り専用表示
        else:
            initial = _fixed_shift_initial(user)
        formset = FixedShiftFormSet(initial=initial, prefix="fx")

    if locked:
        for form in formset.forms:
            for field in form.fields.values():
                field.widget.attrs["disabled"] = True

    return render(
        request,
        "shifts/fixed_shift_edit.html",
        {
            "formset": formset,
            "rows": _fixed_shift_rows(formset),
            "mode": mode,
            "editable": editable,
            "locked": locked,
            "target": user,
            "self_view": True,
            "has_fixed_shift": user.fixed_shifts.exists(),
            "crew_comment": crew_comment,
            "pending": pending,
            "last_reviewed": last_reviewed,
        },
    )


@login_required
def my_fixed_shift_cancel(request):
    """クルー本人が、自分の保留中の固定シフト変更申請を取り消す。"""
    if request.method == "POST":
        deleted, _ = request.user.fixed_shift_requests.filter(
            status=FixedShiftChangeRequest.Status.PENDING
        ).delete()
        if deleted:
            messages.success(request, "固定シフトの変更申請を取り消しました。新しく申請できます。")
    return redirect("my_fixed_shift")


@manager_required
def manage_fixed_shifts(request):
    """全クルーの固定シフト一覧（リーダー・管理者）。"""
    crew = User.objects.filter(role=User.Role.CREW, is_active=True).order_by(
        "name", "username"
    )
    by_user = {}
    for ws in WeeklyFixedShift.objects.filter(user__in=crew):
        by_user.setdefault(ws.user_id, {})[ws.weekday] = ws

    table = []
    for u in crew:
        wsmap = by_user.get(u.id, {})
        table.append(
            {
                "user": u,
                "cells": [wsmap.get(wd) for wd in range(7)],
                "has_any": bool(wsmap),
            }
        )
    return render(
        request,
        "shifts/manage_fixed_shifts.html",
        {"table": table, "weekdays": WEEKDAYS_JP},
    )


@manager_required
def manage_fixed_shift_edit(request, user_pk):
    """リーダー・管理者が、対象クルーの固定シフトを代理編集する。"""
    target = get_object_or_404(User, pk=user_pk, role=User.Role.CREW)

    has_pending = target.fixed_shift_requests.filter(
        status=FixedShiftChangeRequest.Status.PENDING
    ).exists()

    if request.method == "POST":
        formset = FixedShiftFormSet(request.POST, prefix="fx")
        if formset.is_valid():
            _save_fixed_shift(target, formset)
            messages.success(request, f"「{target.name}」の固定シフトを保存しました。")
            if has_pending:
                messages.warning(
                    request,
                    f"「{target.name}」には未処理の変更申請があります。"
                    "今の保存内容が、その申請を承認すると上書きされる可能性があります。"
                    "申請一覧から処理してください。",
                )
            return redirect("manage_fixed_shifts")
    else:
        formset = FixedShiftFormSet(initial=_fixed_shift_initial(target), prefix="fx")
        if has_pending:
            messages.warning(
                request,
                f"「{target.name}」には未処理の変更申請があります。"
                "代理編集の前に、申請一覧での処理を検討してください。",
            )

    return render(
        request,
        "shifts/fixed_shift_edit.html",
        {
            "formset": formset,
            "rows": _fixed_shift_rows(formset),
            "mode": "edit",
            "editable": True,
            "locked": False,
            "target": target,
            "self_view": False,
            "has_fixed_shift": target.fixed_shifts.exists(),
            "crew_comment": "",
            "pending": None,
            "last_reviewed": None,
        },
    )


def _norm_cell(obj):
    """固定シフト(モデル) or payload(辞書) を、比較表示用の共通形に正規化する。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {
            "is_available": obj["is_available"],
            "start": obj["start_time"],
            "end": obj["end_time"],
        }
    return {"is_available": obj.is_available, "start": obj.start_time, "end": obj.end_time}


@manager_required
def manage_fixed_shift_requests(request):
    """固定シフト変更申請の一覧（保留＋直近の処理済み）。"""
    Status = FixedShiftChangeRequest.Status
    pending = (
        FixedShiftChangeRequest.objects.filter(status=Status.PENDING)
        .select_related("user")
        .order_by("created_at")
    )
    recent = (
        FixedShiftChangeRequest.objects.exclude(status=Status.PENDING)
        .select_related("user", "reviewer")[:20]
    )
    return render(
        request,
        "shifts/manage_fixed_shift_requests.html",
        {"pending": pending, "recent": recent},
    )


@manager_required
def manage_fixed_shift_request_review(request, pk):
    """申請の詳細（現在値と提案の比較）と、承認/却下（コメント任意）。"""
    Status = FixedShiftChangeRequest.Status
    req = get_object_or_404(
        FixedShiftChangeRequest.objects.select_related("user"), pk=pk
    )

    if request.method == "POST" and req.status == Status.PENDING:
        action = request.POST.get("action")
        comment = request.POST.get("review_comment", "").strip()
        if action in ("approve", "reject"):
            req.reviewer = request.user
            req.review_comment = comment
            req.reviewed_at = timezone.now()
            if action == "approve":
                _apply_payload(req.user, req.payload)
                req.status = Status.APPROVED
                msg = f"「{req.user.name}」の固定シフト変更を承認し、反映しました。"
            else:
                req.status = Status.REJECTED
                msg = f"「{req.user.name}」の固定シフト変更を却下しました。"
            req.save()
            # 処理済みはクルーごとに直近10件だけ残す
            _prune_processed_requests(req.user)
            messages.success(request, msg)
            return redirect("manage_fixed_shift_requests")

    current = {ws.weekday: ws for ws in req.user.fixed_shifts.all()}
    proposed = {d["weekday"]: d for d in req.payload}
    compare = []
    for wd in range(7):
        cur = _norm_cell(current.get(wd))
        pro = _norm_cell(proposed.get(wd))
        compare.append(
            {
                "weekday": WEEKDAYS_JP[wd],
                "current": cur,
                "proposed": pro,
                "changed": cur != pro,
            }
        )
    return render(
        request,
        "shifts/manage_fixed_shift_request_review.html",
        {"req": req, "compare": compare, "is_pending": req.status == Status.PENDING},
    )


# ----- アナウンス -----

ANNOUNCEMENT_RETENTION_DAYS = 7  # 投稿からこの日数を過ぎたアナウンスは自動削除


def _prune_old_announcements():
    """投稿から一定日数を過ぎたアナウンスを、添付の実ファイルごと削除する。

    cron 等を使わず、アナウンスを表示するタイミングで掃除する方式。
    """
    cutoff = timezone.now() - timedelta(days=ANNOUNCEMENT_RETENTION_DAYS)
    old = Announcement.objects.filter(created_at__lt=cutoff)
    for ann in old.prefetch_related("attachments"):
        for att in ann.attachments.all():
            att.file.delete(save=False)
    old.delete()


def _unread_announcement_count(user):
    """このユーザーの未読アナウンス件数。"""
    return Announcement.objects.exclude(reads__user=user).count()


def _auto_announce(
    category, title, body="", period=None, by=None, level=Announcement.Level.INFO
):
    """設定がオンのときだけ、自動アナウンスを投稿する。"""
    cfg = AnnouncementSettings.load()
    enabled = {
        Announcement.Category.PERIOD: cfg.auto_on_period,
    }.get(category, False)
    if not enabled:
        return None
    return Announcement.objects.create(
        title=title,
        body=body,
        category=category,
        level=level,
        related_period=period,
        created_by=by,
    )


@login_required
def announcements(request):
    """アナウンス一覧（タイトル＋抜粋）。既読は詳細を開いたときに付ける。"""
    _prune_old_announcements()
    items = list(
        Announcement.objects.select_related("created_by")
        .prefetch_related("attachments")
        .all()
    )
    read_ids = set(
        AnnouncementRead.objects.filter(
            user=request.user, announcement__in=items
        ).values_list("announcement_id", flat=True)
    )
    for a in items:
        a.is_unread = a.id not in read_ids
    return render(request, "shifts/announcements.html", {"items": items})


@login_required
def announcement_detail(request, pk):
    """アナウンス詳細。開いた時点でこのユーザーの既読にする。"""
    _prune_old_announcements()
    ann = get_object_or_404(
        Announcement.objects.select_related("created_by").prefetch_related(
            "attachments"
        ),
        pk=pk,
    )
    AnnouncementRead.objects.get_or_create(announcement=ann, user=request.user)
    return render(request, "shifts/announcement_detail.html", {"a": ann})


@login_required
def announcement_attachment(request, pk):
    """アナウンス添付の配信。ログイン必須＋本番は X-Accel-Redirect（確定シフトと同方式）。"""
    att = get_object_or_404(AnnouncementAttachment, pk=pk)
    name = att.file.name
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    display_name = att.original_name or name.rsplit("/", 1)[-1]
    disposition = "inline; filename*=UTF-8''" + quote(display_name)

    if settings.DEBUG:
        response = FileResponse(att.file.open("rb"), content_type=content_type)
    else:
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = "/protected/" + quote(name)
    response["Content-Disposition"] = disposition
    response["Cache-Control"] = "private, no-store"
    return response


ANNOUNCE_ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf")
ANNOUNCE_MAX_SIZE = 10 * 1024 * 1024  # 10MB


@manager_required
def manage_announcements(request):
    """アナウンスの手動投稿（画像・PDFを複数添付可）と一覧・削除。"""
    _prune_old_announcements()
    if request.method == "POST":
        form = AnnouncementForm(request.POST)
        files = request.FILES.getlist("files")
        file_errors = []
        for f in files:
            if not f.name.lower().endswith(ANNOUNCE_ALLOWED_EXT):
                file_errors.append(f"{f.name}: 画像かPDFを選んでください。")
            elif f.size > ANNOUNCE_MAX_SIZE:
                file_errors.append(f"{f.name}: 10MBまでにしてください。")
        if form.is_valid() and not file_errors:
            ann = form.save(commit=False)
            ann.created_by = request.user
            ann.category = Announcement.Category.MANUAL
            ann.save()
            for f in files:
                AnnouncementAttachment.objects.create(
                    announcement=ann, file=f, original_name=f.name
                )
            messages.success(request, "アナウンスを投稿しました。")
            return redirect("manage_announcements")
        for e in file_errors:
            messages.error(request, e)
    else:
        form = AnnouncementForm()

    items = Announcement.objects.prefetch_related("attachments").all()
    return render(
        request, "shifts/manage_announcements.html", {"form": form, "items": items}
    )


@manager_required
def manage_announcement_delete(request, pk):
    """アナウンスの削除（添付の実ファイルも削除）。"""
    ann = get_object_or_404(Announcement, pk=pk)
    if request.method == "POST":
        for att in ann.attachments.all():
            att.file.delete(save=False)
        ann.delete()
        messages.success(request, "アナウンスを削除しました。")
    return redirect("manage_announcements")


@manager_required
def manage_announcement_settings(request):
    """自動投稿（確定シフト/期間追加）のオンオフ設定。"""
    obj = AnnouncementSettings.load()
    if request.method == "POST":
        form = AnnouncementSettingsForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "自動投稿の設定を保存しました。")
            return redirect("manage_announcement_settings")
    else:
        form = AnnouncementSettingsForm(instance=obj)
    return render(
        request, "shifts/manage_announcement_settings.html", {"form": form}
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

        # クルーへアナウンスを投稿（ボタンで明示的に。自動投稿ではない）
        if request.POST.get("announce"):
            Announcement.objects.create(
                title=f"確定シフトが公開されました（{period}）",
                body="「確定シフト」のページからご確認ください。",
                category=Announcement.Category.CONFIRMED,
                level=Announcement.Level.SUCCESS,
                related_period=period,
                created_by=request.user,
            )
            messages.success(request, "確定シフトのアナウンスをクルーに投稿しました。")
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


@login_required
def confirmed_shift_file(request, pk):
    """確定シフトPDFの配信。ログイン必須にして無認証ダウンロードを防ぐ。

    本番では実ファイルの送信を nginx(X-Accel-Redirect) に委譲する。
    nginx 側に `internal` の /protected/ ロケーション（media ルートを alias）を用意し、
    /media/ への直接アクセスは塞いでおくこと。
    開発(runserver, DEBUG=True)では nginx が無いので Django が直接返す。
    """
    cs = get_object_or_404(ConfirmedShift, pk=pk)
    name = cs.file.name  # 例: confirmed_shifts/period_3/problem.pdf
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    display_name = cs.original_name or name.rsplit("/", 1)[-1]
    disposition = "inline; filename*=UTF-8''" + quote(display_name)

    if settings.DEBUG:
        # 開発用: Django が直接ファイルを返す
        response = FileResponse(cs.file.open("rb"), content_type=content_type)
    else:
        # 本番: 認証だけ Django が行い、送信は nginx に任せる
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = "/protected/" + quote(name)
    response["Content-Disposition"] = disposition
    # 認証済みファイルなので CDN/プロキシにキャッシュさせない
    # （Cloudflare 等のエッジに残ると無認証で配られてしまうため）
    response["Cache-Control"] = "private, no-store"
    return response


@manager_required
def manage_top(request):
    """S8 リーダー用トップ（管理メニュー）。"""
    now = timezone.now()
    staff_count = User.objects.filter(
        role=User.Role.CREW, is_active=True
    ).count()
    open_count = sum(1 for p in ShiftPeriod.objects.all() if not _is_closed(p, now))
    fixed_request_count = FixedShiftChangeRequest.objects.filter(
        status=FixedShiftChangeRequest.Status.PENDING
    ).count()
    return render(
        request,
        "shifts/manage_top.html",
        {
            "staff_count": staff_count,
            "open_count": open_count,
            "fixed_request_count": fixed_request_count,
        },
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
            if period.is_visible:
                deadline = timezone.localtime(period.deadline).strftime("%Y/%m/%d %H:%M")
                _auto_announce(
                    Announcement.Category.PERIOD,
                    title=f"新しいシフト期間が追加されました（{period}）",
                    body=f"締切は {deadline} です。提出をお願いします。",
                    period=period,
                    by=request.user,
                )
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
