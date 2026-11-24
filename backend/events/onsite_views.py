from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .admission import admit_next, get_arrival_queue, record_arrival, remove_arrival
from .attendance_report import build_workbook, get_attendance_report
from .checkin import OnsiteError, check_in, get_checkin_roster, record_late_note, release_formal_seat
from .models import Activity, ActivityStaff, Registration, RosterEvent
from .seats import available_seats


class ArrivalForm(forms.Form):
    student_number = forms.CharField(max_length=32)
    name = forms.CharField(max_length=100)


class ReasonForm(forms.Form):
    reason = forms.CharField(max_length=240)


@never_cache
@login_required(login_url="onsite:login")
@require_GET
def home(request):
    assignments = ActivityStaff.objects.filter(
        user=request.user, role__in=(ActivityStaff.Role.CHECK_IN, ActivityStaff.Role.FINANCE)
    ).select_related("activity").order_by("-activity__starts_at", "activity_id", "role")
    return render(request, "onsite/home.html", {"assignments": assignments})


@never_cache
@login_required(login_url="onsite:login")
@require_GET
def roster(request, activity_id):
    try:
        seats = get_checkin_roster(activity_id, staff_id=request.user.pk)
        queue = get_arrival_queue(activity_id, staff_id=request.user.pk)
        activity = Activity.objects.get(pk=activity_id)
    except Activity.DoesNotExist as exc:
        raise Http404 from exc

    now = timezone.now()
    is_open = activity.starts_at <= now < activity.ends_at
    rows = []
    for seat in seats:
        participant = seat.occupant
        attendance = getattr(participant, "attendance", None)
        registration = participant.current_registration
        online = registration is not None and registration.status == Registration.Status.CONFIRMED
        protected = online and registration.late_reported_at is not None and now < activity.absence_at
        rows.append({
            "participant": participant,
            "seat": seat,
            "attendance": attendance,
            "protected": protected,
            "can_sign_in": is_open and online and attendance is None,
            "can_note": online and attendance is None and now < activity.absence_at and not protected,
            "can_release": is_open and now >= activity.release_starts_at and online
            and attendance is None and not protected,
        })
    return render(request, "onsite/roster.html", {
        "activity": activity,
        "rows": rows,
        "queue": queue,
        "is_open": is_open,
        "vacancies": available_seats(activity_id, at=now).count(),
        "releases": RosterEvent.objects.filter(
            participant__activity=activity, kind=RosterEvent.Kind.RELEASED
        ).select_related("participant").order_by("-occurred_at", "-pk"),
    })


def _update_roster(request, activity_id, operation, success, *args, **kwargs):
    try:
        operation(activity_id, *args, staff_id=request.user.pk, **kwargs)
    except Activity.DoesNotExist as exc:
        raise Http404 from exc
    except OnsiteError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, success)
    return redirect("onsite:roster", activity_id=activity_id)


def _reason_update(request, activity_id, participant_id, operation, success):
    form = ReasonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "请填写 1 至 240 字的说明。")
        return redirect("onsite:roster", activity_id=activity_id)
    return _update_roster(
        request, activity_id, operation, success, participant_id, reason=form.cleaned_data["reason"]
    )


@login_required(login_url="onsite:login")
@require_POST
def sign_in(request, activity_id, participant_id):
    return _update_roster(request, activity_id, check_in, "已签到。", participant_id)


@login_required(login_url="onsite:login")
@require_POST
def late_note(request, activity_id, participant_id):
    return _reason_update(request, activity_id, participant_id, record_late_note, "已记录晚到留言。")


@login_required(login_url="onsite:login")
@require_POST
def release(request, activity_id, participant_id):
    return _reason_update(request, activity_id, participant_id, release_formal_seat, "席位已释放。")


@login_required(login_url="onsite:login")
@require_POST
def arrival(request, activity_id):
    form = ArrivalForm(request.POST)
    if not form.is_valid():
        messages.error(request, "请填写核验过的学号和姓名。")
        return redirect("onsite:roster", activity_id=activity_id)
    return _update_roster(request, activity_id, record_arrival, "已登记在场。", **form.cleaned_data)


@login_required(login_url="onsite:login")
@require_POST
def leave(request, activity_id, participant_id):
    return _update_roster(request, activity_id, remove_arrival, "已登记离场。", participant_id)


@login_required(login_url="onsite:login")
@require_POST
def admit(request, activity_id, participant_id):
    return _update_roster(request, activity_id, admit_next, "已补位并签到。", participant_id)


def _report(request, activity_id, render_report):
    try:
        result = get_attendance_report(activity_id, staff_id=request.user.pk)
    except Activity.DoesNotExist as exc:
        raise Http404 from exc
    except OnsiteError as exc:
        return render(request, "onsite/report.html", {"unavailable": str(exc)}, status=409)
    return render_report(result)


@never_cache
@login_required(login_url="onsite:login")
@require_GET
def report(request, activity_id):
    return _report(request, activity_id, lambda result: render(request, "onsite/report.html", {"report": result}))


@never_cache
@login_required(login_url="onsite:login")
@require_GET
def export(request, activity_id):
    def download(result):
        return HttpResponse(
            build_workbook(result),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="attendance-{activity_id}.xlsx"'},
        )

    return _report(request, activity_id, download)
