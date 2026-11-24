from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Activity(models.Model):
    title = models.CharField(max_length=160)
    location = models.CharField(max_length=160, blank=True)
    capacity = models.PositiveIntegerField()
    registration_closes_at = models.DateTimeField()
    invitation_stops_at = models.DateTimeField()
    latest_confirmation_at = models.DateTimeField()
    starts_at = models.DateTimeField()
    release_starts_at = models.DateTimeField()
    absence_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    invitation_minutes = models.PositiveSmallIntegerField(default=120)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(capacity__gt=0, invitation_minutes__gt=0),
                name="activity_capacity_and_duration_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(registration_closes_at__lte=F("invitation_stops_at"))
                    & Q(invitation_stops_at__lte=F("latest_confirmation_at"))
                    & Q(latest_confirmation_at__lte=F("starts_at"))
                    & Q(starts_at__lte=F("release_starts_at"))
                    & Q(release_starts_at__lte=F("absence_at"))
                    & Q(absence_at__lt=F("ends_at"))
                ),
                name="activity_deadlines_in_order",
            ),
        ]


class ActivityStaff(models.Model):
    class Role(models.TextChoices):
        ORGANIZER = "organizer", "活动负责人"
        CHECK_IN = "check_in", "签到岗"
        FINANCE = "finance", "财务"

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("activity", "user", "role"), name="unique_activity_staff_role"
            )
        ]


class Participant(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    student_number = models.CharField(max_length=32)
    name = models.CharField(max_length=100)
    current_registration = models.OneToOneField(
        "Registration", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("activity", "student_number"), name="unique_activity_student_number"
            ),
        ]


class Registration(models.Model):
    class InitialCategory(models.TextChoices):
        FORMAL = "formal", "正式"
        WAITLIST = "waitlist", "候补"

    class Status(models.TextChoices):
        WAITLISTED = "waitlisted", "候补"
        CONFIRMED = "confirmed", "线上正式"
        ONSITE_ONLY = "onsite_only", "仅现场候补"
        WITHDRAWN = "withdrawn", "已退出"
        RELEASED = "released", "座位已释放"

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="registrations"
    )
    queue_sequence = models.PositiveIntegerField()
    initial_category = models.CharField(max_length=16, choices=InitialCategory.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    request_id = models.UUIDField()
    submitted_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    late_reported_at = models.DateTimeField(null=True, blank=True)
    late_report_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("participant", "request_id"), name="unique_participant_signup_request"
            ),
            models.UniqueConstraint(
                fields=("activity", "queue_sequence"), name="unique_activity_queue_sequence"
            ),
            models.CheckConstraint(condition=Q(queue_sequence__gt=0), name="signup_sequence_positive"),
        ]
        indexes = [
            models.Index(fields=("activity", "status", "queue_sequence"), name="signup_waitlist_idx"),
        ]


class Seat(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    number = models.PositiveIntegerField()
    vacancy_round = models.PositiveIntegerField(default=1)
    occupant = models.OneToOneField(
        Participant, on_delete=models.PROTECT, null=True, blank=True, related_name="seat"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("activity", "number"), name="unique_activity_seat"),
            models.CheckConstraint(
                condition=Q(number__gt=0, vacancy_round__gt=0),
                name="seat_number_and_round_positive",
            ),
        ]


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待确认"
        ACCEPTED = "accepted", "已接受"
        DECLINED = "declined", "已拒绝"
        EXPIRED = "expired", "已到期"
        VOID = "void", "已作废"
        REISSUED = "reissued", "已重发"

    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)
    vacancy_round = models.PositiveIntegerField()
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE)
    replaces = models.OneToOneField(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replacement"
    )
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    reason = models.CharField(max_length=240, blank=True)
    token_digest = models.CharField(max_length=64, unique=True)
    code_hash = models.CharField(max_length=128)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("seat", "request_id"), name="unique_seat_invite_request"),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("issued_at")), name="invite_expiry_after_issue"
            ),
        ]
        indexes = [
            models.Index(fields=("seat", "status", "expires_at"), name="invite_seat_active_idx"),
        ]


class VacancySkip(models.Model):
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)
    vacancy_round = models.PositiveIntegerField()
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField()
    reason = models.CharField(max_length=240)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("seat", "vacancy_round", "participant"), name="unique_skip_per_vacancy"
            )
        ]


class Attendance(models.Model):
    class AdmissionMode(models.TextChoices):
        ONLINE = "online", "线上正式"
        ONSITE_WAITLIST = "onsite_waitlist", "现场候补"
        ONSITE_WALK_IN = "onsite_walk_in", "现场临时"

    participant = models.OneToOneField(
        Participant, on_delete=models.PROTECT, related_name="attendance"
    )
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT)
    admission_mode = models.CharField(max_length=16, choices=AdmissionMode.choices)
    checked_in_at = models.DateTimeField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class RosterEvent(models.Model):
    class Kind(models.TextChoices):
        RELEASED = "released", "释放正式席位"
        STAGE_ABSENT = "stage_absent", "阶段缺席"
        ARRIVED = "arrived", "登记在场"
        LATE_NOTE = "late_note", "确认晚到留言"

    participant = models.ForeignKey(
        Participant, on_delete=models.PROTECT, related_name="roster_events"
    )
    registration = models.ForeignKey(Registration, on_delete=models.PROTECT, null=True, blank=True)
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    occurred_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    reason = models.CharField(max_length=240, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("participant", "kind", "occurred_at"), name="roster_event_history_idx"
            ),
        ]
