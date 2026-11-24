import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .models import Activity, ActivityStaff, Invitation, Registration, Seat, VacancySkip
from .seats import active_holds, available_seats, current_registrations, lock_activity, occupy_seat


class InvitationError(ValueError):
    """The requested organizer operation cannot be applied to the current roster."""


@dataclass(frozen=True)
class IssuedInvitation:
    invitation_id: int
    token: str = field(repr=False)
    code: str = field(repr=False)


def unreserved_waitlist(activity_id, now):
    expired = Invitation.objects.filter(
        registration_id=OuterRef("pk"),
        status=Invitation.Status.PENDING,
        expires_at__lte=now,
    )
    return (
        current_registrations(activity_id)
        .filter(~Exists(expired), status=Registration.Status.WAITLISTED)
        .exclude(pk__in=active_holds(activity_id, now).values("registration_id"))
        .order_by("queue_sequence")
    )


def finish_invitation(invitation, status, now):
    """Resolve a pending invitation inside the activity transaction."""
    invitation.status = status
    invitation.resolved_at = now
    invitation.save(update_fields=("status", "resolved_at"))
    if status in (Invitation.Status.EXPIRED, Invitation.Status.DECLINED):
        registration = invitation.registration
        if (
            registration.participant.current_registration_id == registration.pk
            and registration.status == Registration.Status.WAITLISTED
        ):
            registration.status = Registration.Status.ONSITE_ONLY
            registration.save(update_fields=("status",))


def expire_due_locked(activity_id, now):
    due = Invitation.objects.select_related("registration__participant").filter(
        seat__activity_id=activity_id, status=Invitation.Status.PENDING, expires_at__lte=now
    )
    count = 0
    for invitation in due.iterator():
        finish_invitation(invitation, Invitation.Status.EXPIRED, invitation.expires_at)
        count += 1
    return count


@transaction.atomic
def expire_invitations(activity_id):
    lock_activity(activity_id)
    return expire_due_locked(activity_id, timezone.now())


def _require_organizer(activity, organizer_id):
    if not ActivityStaff.objects.filter(
        activity=activity, user_id=organizer_id, user__is_active=True, role=ActivityStaff.Role.ORGANIZER
    ).exists():
        raise InvitationError("Only this activity's organizer can manage its invitations.")


def _vacant_seat(activity, seat_id):
    seat = Seat.objects.filter(
        pk=seat_id, activity=activity, number__lte=activity.capacity, occupant__isnull=True
    ).first()
    if seat is None:
        raise InvitationError("The seat is not available in this activity.")
    return seat


def _token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _candidate_for_seat(seat, now):
    skipped = VacancySkip.objects.filter(seat=seat, vacancy_round=seat.vacancy_round)
    return unreserved_waitlist(seat.activity_id, now).exclude(
        participant_id__in=skipped.values("participant_id")
    ).first()


def next_candidate(activity_id, seat_id, *, organizer_id):
    activity = Activity.objects.get(pk=activity_id)
    _require_organizer(activity, organizer_id)
    now = timezone.now()
    if now >= activity.invitation_stops_at:
        return None
    seat = available_seats(activity_id, at=now).filter(pk=seat_id).first()
    return _candidate_for_seat(seat, now) if seat is not None else None


def _store_invitation(
    seat, registration, organizer_id, request_id, now, expires_at, *, replaces=None, reason=""
):
    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    while replaces is not None and check_password(code, replaces.code_hash):
        code = f"{secrets.randbelow(1_000_000):06d}"
    invitation = Invitation.objects.create(
        seat=seat,
        vacancy_round=seat.vacancy_round,
        registration=registration,
        replaces=replaces,
        issued_by_id=organizer_id,
        request_id=request_id,
        reason=reason,
        token_digest=_token_digest(token),
        code_hash=make_password(code),
        issued_at=now,
        expires_at=expires_at,
        failed_attempts=replaces.failed_attempts if replaces else 0,
        blocked_until=replaces.blocked_until if replaces else None,
    )
    return IssuedInvitation(invitation.pk, token, code)


@transaction.atomic
def issue_invitation(
    activity_id, seat_id, *, organizer_id, request_id: UUID,
    expected_registration_id=None, expected_vacancy_round=None,
):
    activity = lock_activity(activity_id)
    _require_organizer(activity, organizer_id)
    now = timezone.now()
    if now >= activity.invitation_stops_at:
        raise InvitationError("This activity has stopped issuing invitations.")

    seat = _vacant_seat(activity, seat_id)
    if Invitation.objects.filter(seat=seat, request_id=request_id).exists():
        raise InvitationError("This operation already issued an invitation.")
    if expected_vacancy_round is not None and seat.vacancy_round != expected_vacancy_round:
        raise InvitationError("The seat has moved to a different vacancy round.")
    expire_due_locked(activity.pk, now)
    if active_holds(activity.pk, now).filter(seat=seat).exists():
        raise InvitationError("The seat already has an active reservation.")

    candidate = _candidate_for_seat(seat, now)
    if candidate is None:
        raise InvitationError("There is no eligible candidate for this vacancy.")
    if expected_registration_id is not None and candidate.pk != expected_registration_id:
        raise InvitationError("The next candidate has changed. Refresh the roster.")

    expires_at = min(now + timedelta(minutes=activity.invitation_minutes), activity.latest_confirmation_at)
    return _store_invitation(seat, candidate, organizer_id, request_id, now, expires_at)


@transaction.atomic
def reissue_invitation(activity_id, invitation_id, *, organizer_id, request_id: UUID, reason):
    activity = lock_activity(activity_id)
    _require_organizer(activity, organizer_id)
    now = timezone.now()
    if now >= activity.invitation_stops_at:
        raise InvitationError("This activity has stopped issuing invitations.")
    reason = _validated_reason(reason)
    invitation = (
        active_holds(activity.pk, now).select_related("seat", "registration")
        .filter(pk=invitation_id).first()
    )
    if invitation is None:
        raise InvitationError("This reservation is no longer active.")
    if Invitation.objects.filter(seat=invitation.seat, request_id=request_id).exists():
        raise InvitationError("This operation already issued an invitation.")
    finish_invitation(invitation, Invitation.Status.REISSUED, now)
    return _store_invitation(
        invitation.seat, invitation.registration, organizer_id, request_id,
        now, invitation.expires_at, replaces=invitation, reason=reason,
    )


@transaction.atomic
def respond_invitation(activity_id, participant_id, token, code, *, accept=True):
    """Resolve an invitation for a participant ID supplied by the verified session."""
    if (
        not isinstance(token, str) or len(token) != 43 or not token.isascii()
        or not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit()
    ):
        return "invalid"
    activity = lock_activity(activity_id)
    now = timezone.now()
    invitation = (
        Invitation.objects.select_related("seat", "registration__participant")
        .filter(
            seat__activity_id=activity_id,
            registration__activity_id=activity_id,
            registration__participant__activity_id=activity_id,
            registration__participant_id=participant_id,
            token_digest=_token_digest(token),
        )
        .first()
    )
    if invitation is None:
        return "invalid"
    registration = invitation.registration
    if (
        registration.participant.current_registration_id != registration.pk
        or registration.status == Registration.Status.WITHDRAWN
        or invitation.status in (Invitation.Status.VOID, Invitation.Status.REISSUED)
    ):
        return "invalid"

    if invitation.status != Invitation.Status.PENDING:
        if invitation.status in (Invitation.Status.ACCEPTED, Invitation.Status.DECLINED):
            return invitation.status if check_password(code, invitation.code_hash) else "invalid"
        return invitation.status

    if now >= invitation.expires_at:
        finish_invitation(invitation, Invitation.Status.EXPIRED, invitation.expires_at)
        return Invitation.Status.EXPIRED
    if invitation.blocked_until is not None:
        if now < invitation.blocked_until:
            return "throttled"
        invitation.failed_attempts = 0
        invitation.blocked_until = None
    if not check_password(code, invitation.code_hash):
        invitation.failed_attempts += 1
        if invitation.failed_attempts >= 5:
            invitation.blocked_until = now + timedelta(minutes=5)
        invitation.save(update_fields=("failed_attempts", "blocked_until"))
        return "throttled" if invitation.blocked_until is not None else "invalid"

    seat = invitation.seat
    if (
        seat.vacancy_round != invitation.vacancy_round
        or seat.occupant_id is not None
        or seat.number > activity.capacity
        or registration.status != Registration.Status.WAITLISTED
    ):
        finish_invitation(invitation, Invitation.Status.VOID, now)
        return "invalid"

    status = Invitation.Status.ACCEPTED if accept else Invitation.Status.DECLINED
    finish_invitation(invitation, status, now)
    if accept:
        occupy_seat(activity, seat.pk, participant_id, now)
        registration.status = Registration.Status.CONFIRMED
        registration.confirmed_at = now
        registration.save(update_fields=("status", "confirmed_at"))
    return status


def _validated_reason(reason):
    reason = reason.strip()
    if not reason or len(reason) > 240:
        raise InvitationError("A reason of up to 240 characters is required.")
    return reason


@transaction.atomic
def skip_candidate(activity_id, seat_id, participant_id, *, organizer_id, reason, vacancy_round):
    activity = lock_activity(activity_id)
    _require_organizer(activity, organizer_id)
    now = timezone.now()
    if now >= activity.starts_at:
        raise InvitationError("This activity has entered on-site admission.")
    reason = _validated_reason(reason)
    seat = _vacant_seat(activity, seat_id)
    if seat.vacancy_round != vacancy_round:
        raise InvitationError("The seat has moved to a different vacancy round.")

    expire_due_locked(activity.pk, now)
    candidate = current_registrations(activity.pk).filter(
        participant_id=participant_id, status=Registration.Status.WAITLISTED
    ).first()
    if candidate is None:
        raise InvitationError("The participant is not waiting for an online seat.")

    VacancySkip.objects.get_or_create(
        seat=seat,
        participant_id=participant_id,
        vacancy_round=vacancy_round,
        defaults={"recorded_by_id": organizer_id, "recorded_at": now, "reason": reason},
    )
    reservation = active_holds(activity.pk, now).filter(seat=seat, registration=candidate).first()
    if reservation is not None:
        finish_invitation(reservation, Invitation.Status.VOID, now)
