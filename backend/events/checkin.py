from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .models import ActivityStaff, Attendance, Registration, RosterEvent
from .seats import current_registrations, lock_activity, release_seat, seat_assignments


class OnsiteError(ValueError):
    """An on-site action does not match the activity's current state."""


def require_activity_role(activity, staff_id, role):
    if not ActivityStaff.objects.filter(
        activity=activity, user_id=staff_id, user__is_active=True, role=role
    ).exists():
        raise PermissionDenied("当前账号没有本场活动的操作权限。")


def require_onsite_open(activity, at):
    if not activity.starts_at <= at < activity.ends_at:
        raise OnsiteError("现场操作仅在活动开场后、结束前开放。")


def record_stage_absences_locked(activity, at):
    """Use the state at the absence cutoff. The caller holds the activity lock."""
    cutoff = activity.absence_at
    if at < cutoff:
        return

    recorded = RosterEvent.objects.filter(
        participant_id=OuterRef("participant_id"), kind=RosterEvent.Kind.STAGE_ABSENT
    )
    missed = (
        current_registrations(activity.pk)
        .filter(
            status__in=(Registration.Status.CONFIRMED, Registration.Status.RELEASED),
            confirmed_at__lt=cutoff,
        )
        .exclude(late_reported_at__lt=cutoff)
        .exclude(participant__attendance__checked_in_at__lt=cutoff)
        .filter(~Exists(recorded))
    )
    RosterEvent.objects.bulk_create([
        RosterEvent(
            participant_id=registration.participant_id,
            registration=registration,
            kind=RosterEvent.Kind.STAGE_ABSENT,
            occurred_at=cutoff,
        )
        for registration in missed
    ])


def _validated_reason(reason):
    reason = reason.strip()
    if not 1 <= len(reason) <= 240:
        raise OnsiteError("请填写 1 至 240 字的理由。")
    return reason


def _assigned_seats(activity):
    return seat_assignments(activity.pk).filter(
        occupant__activity=activity
    ).select_related("occupant__attendance")


def _assigned_seat(activity, participant_id):
    return _assigned_seats(activity).filter(occupant_id=participant_id).first()


def _online_registration(activity, seat):
    if seat is None:
        raise OnsiteError("该人员目前没有本场正式席位。")
    registration = seat.occupant.current_registration
    if (
        registration is None
        or registration.activity_id != activity.pk
        or registration.participant_id != seat.occupant_id
        or registration.status != Registration.Status.CONFIRMED
    ):
        raise OnsiteError("该人员目前没有本场正式席位。")
    return registration


@transaction.atomic
def get_checkin_roster(activity_id, *, staff_id):
    activity = lock_activity(activity_id)
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    record_stage_absences_locked(activity, timezone.now())
    return list(_assigned_seats(activity))


@transaction.atomic
def check_in(activity_id, participant_id, *, staff_id):
    activity = lock_activity(activity_id)
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    at = timezone.now()
    require_onsite_open(activity, at)
    seat = _assigned_seat(activity, participant_id)
    attendance = getattr(seat.occupant, "attendance", None) if seat else None
    if attendance is not None:
        return attendance
    _online_registration(activity, seat)

    record_stage_absences_locked(activity, at)
    return Attendance.objects.create(
        participant_id=participant_id,
        seat=seat,
        admission_mode=Attendance.AdmissionMode.ONLINE,
        checked_in_at=at,
        recorded_by_id=staff_id,
    )


@transaction.atomic
def record_late_note(activity_id, participant_id, *, staff_id, reason):
    activity = lock_activity(activity_id)
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    at = timezone.now()
    if at >= activity.absence_at:
        raise OnsiteError("已到缺席判定时点，不能登记晚到保护。")
    reason = _validated_reason(reason)
    seat = _assigned_seat(activity, participant_id)
    registration = _online_registration(activity, seat)
    if getattr(seat.occupant, "attendance", None) is not None:
        raise OnsiteError("该人员已签到，无需登记晚到保护。")
    if registration.late_reported_at is not None:
        return registration

    registration.late_reported_at = at
    registration.late_report_reason = reason
    registration.save(update_fields=("late_reported_at", "late_report_reason"))
    RosterEvent.objects.create(
        participant_id=participant_id,
        registration=registration,
        seat=seat,
        kind=RosterEvent.Kind.LATE_NOTE,
        occurred_at=at,
        recorded_by_id=staff_id,
        reason=reason,
    )
    return registration


@transaction.atomic
def release_formal_seat(activity_id, participant_id, *, staff_id, reason):
    activity = lock_activity(activity_id)
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    at = timezone.now()
    require_onsite_open(activity, at)
    if at < activity.release_starts_at:
        raise OnsiteError("尚未到人工释位时间。")
    reason = _validated_reason(reason)
    previous = RosterEvent.objects.filter(
        participant__activity=activity,
        participant_id=participant_id,
        kind=RosterEvent.Kind.RELEASED,
    ).first()
    if previous is not None:
        return previous

    seat = _assigned_seat(activity, participant_id)
    registration = _online_registration(activity, seat)
    if getattr(seat.occupant, "attendance", None) is not None:
        raise OnsiteError("该人员已签到，不能释放其席位。")
    if registration.late_reported_at is not None and at < activity.absence_at:
        raise OnsiteError("该人员的晚到保护仍有效。")

    record_stage_absences_locked(activity, at)
    release_seat(activity, participant_id)
    registration.status = Registration.Status.RELEASED
    registration.save(update_fields=("status",))
    return RosterEvent.objects.create(
        participant_id=participant_id,
        registration=registration,
        seat=seat,
        kind=RosterEvent.Kind.RELEASED,
        occurred_at=at,
        recorded_by_id=staff_id,
        reason=reason,
    )
