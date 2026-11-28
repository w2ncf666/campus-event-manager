from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from .checkin import (
    OnsiteError,
    record_stage_absences_locked,
    require_activity_role,
    require_onsite_open,
)
from .invitations import expire_due_locked
from .models import (
    Activity,
    ActivityStaff,
    Attendance,
    Participant,
    PresenceRequest,
    Registration,
    RosterEvent,
)
from .seats import available_seats, lock_activity, occupy_seat, seat_assignments


PRESENCE_EVENTS = (RosterEvent.Kind.ARRIVED, RosterEvent.Kind.LEFT)


def _arrival_queue(activity):
    latest_presence = RosterEvent.objects.filter(
        participant_id=OuterRef("participant_id"), kind__in=PRESENCE_EVENTS
    ).order_by("-pk")
    arrivals = (
        RosterEvent.objects.filter(
            pk=Subquery(latest_presence.values("pk")[:1]),
            kind=RosterEvent.Kind.ARRIVED,
            participant__activity=activity,
            participant__attendance__isnull=True,
            participant__seat__isnull=True,
        )
        .select_related("participant__current_registration")
        .order_by("pk")
    )
    waitlist = []
    walk_ins = []
    for arrival in arrivals:
        participant = arrival.participant
        registration = participant.current_registration
        if registration and registration.status in (
            Registration.Status.WAITLISTED,
            Registration.Status.ONSITE_ONLY,
        ):
            waitlist.append((registration.queue_sequence, participant))
        else:
            walk_ins.append((participant, Attendance.AdmissionMode.ONSITE_WALK_IN))
    waitlist.sort(key=lambda entry: entry[0])
    return [
        (participant, Attendance.AdmissionMode.ONSITE_WAITLIST)
        for _, participant in waitlist
    ] + walk_ins


def get_arrival_queue(activity_id, *, staff_id):
    """Return the current on-site queue in admission order."""
    activity = Activity.objects.get(pk=activity_id)
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    return _arrival_queue(activity)


def _set_presence(participant, kind, *, staff_id, at):
    latest_kind = (
        participant.roster_events.filter(kind__in=PRESENCE_EVENTS)
        .order_by("-pk")
        .values_list("kind", flat=True)
        .first()
    )
    if latest_kind == kind or (latest_kind is None and kind == RosterEvent.Kind.LEFT):
        return
    RosterEvent.objects.create(
        participant=participant,
        registration=participant.current_registration,
        kind=kind,
        occurred_at=at,
        recorded_by_id=staff_id,
    )


def _previous_presence_request(activity, request_id, kind):
    previous = PresenceRequest.objects.filter(
        activity=activity, request_id=request_id,
    ).select_related("participant").first()
    if previous is not None and previous.kind != kind:
        raise OnsiteError("提交编号已用于其他操作。请刷新名单后重试。")
    return previous


@transaction.atomic
def record_arrival(activity_id, *, staff_id, student_number, name, request_id):
    """Record presence after the check-in operator verifies the name and student number."""
    activity = lock_activity(activity_id)
    now = timezone.now()
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    require_onsite_open(activity, now)
    student_number = student_number.strip()
    name = name.strip()
    if not student_number or len(student_number) > 32 or not name or len(name) > 100:
        raise OnsiteError("请输入有效的姓名和学号。")
    kind = PresenceRequest.Kind.ARRIVE
    previous = _previous_presence_request(activity, request_id, kind)
    if previous is not None:
        participant = previous.participant
        if (participant.student_number, participant.name) != (student_number, name):
            raise OnsiteError("提交编号已用于其他人员。请刷新名单后重试。")
        return participant

    participant, _ = Participant.objects.get_or_create(
        activity=activity, student_number=student_number, defaults={"name": name}
    )
    if participant.student_number != student_number or participant.name != name:
        raise OnsiteError("姓名或学号与本场记录不一致，请重新核验。")
    if not Attendance.objects.filter(participant=participant).exists():
        if seat_assignments(activity_id).filter(occupant=participant).exists():
            raise OnsiteError("此人已有正式席位，请直接办理签到。")
        _set_presence(participant, RosterEvent.Kind.ARRIVED, staff_id=staff_id, at=now)
    PresenceRequest.objects.create(
        activity=activity, request_id=request_id, participant=participant, kind=kind,
    )
    return participant


@transaction.atomic
def remove_arrival(activity_id, participant_id, *, staff_id, request_id):
    """Withdraw an on-site queue entry without changing past attendance."""
    activity = lock_activity(activity_id)
    now = timezone.now()
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    require_onsite_open(activity, now)
    kind = PresenceRequest.Kind.LEAVE
    previous = _previous_presence_request(activity, request_id, kind)
    if previous is not None:
        if previous.participant_id != participant_id:
            raise OnsiteError("提交编号已用于其他人员。请刷新名单后重试。")
        return previous.participant
    participant = Participant.objects.filter(pk=participant_id, activity=activity).first()
    if participant is None:
        raise OnsiteError("本场活动没有该到场记录。")
    if not Attendance.objects.filter(participant=participant).exists():
        _set_presence(participant, RosterEvent.Kind.LEFT, staff_id=staff_id, at=now)
    PresenceRequest.objects.create(
        activity=activity, request_id=request_id, participant=participant, kind=kind,
    )
    return participant


@transaction.atomic
def admit_next(activity_id, participant_id, *, staff_id):
    """Admit the expected queue head and check them in in the same transaction."""
    activity = lock_activity(activity_id)
    now = timezone.now()
    require_activity_role(activity, staff_id, ActivityStaff.Role.CHECK_IN)
    require_onsite_open(activity, now)
    existing = Attendance.objects.filter(
        participant__activity=activity, participant_id=participant_id
    ).first()
    if existing is not None:
        if existing.admission_mode == Attendance.AdmissionMode.ONLINE:
            raise OnsiteError("此人已有线上正式席位和签到记录。")
        return existing

    queue = _arrival_queue(activity)
    if not queue or queue[0][0].pk != participant_id:
        raise OnsiteError("到场顺序已变，请刷新名单后办理队首人员。")
    seat = available_seats(activity_id, at=now).first()
    if seat is None:
        raise OnsiteError("当前没有空位。")

    record_stage_absences_locked(activity, now)
    expire_due_locked(activity_id, now)
    participant, mode = queue[0]
    seat = occupy_seat(activity, seat.pk, participant.pk, now)
    return Attendance.objects.create(
        participant=participant,
        seat=seat,
        admission_mode=mode,
        checked_in_at=now,
        recorded_by_id=staff_id,
    )
