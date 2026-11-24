from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .invitations import expire_due_locked, finish_invitation, unreserved_waitlist
from .models import Invitation, Participant, Registration
from .seats import available_seats, lock_activity, occupy_seat, release_seat


class SignupError(ValueError):
    """The requested registration action is unavailable."""


@transaction.atomic
def submit_registration(activity_id, participant_id, *, request_id):
    """Register a verified participant, or return the existing result for this request."""
    activity = lock_activity(activity_id)
    now = timezone.now()
    participant = Participant.objects.select_related("current_registration").get(
        activity=activity, pk=participant_id
    )
    existing = participant.registrations.filter(request_id=request_id).first()
    if existing is not None:
        return existing
    if now >= activity.registration_closes_at:
        raise SignupError("Registration has closed.")
    if (
        participant.current_registration is not None
        and participant.current_registration.status != Registration.Status.WITHDRAWN
    ):
        raise SignupError("This participant already has a current registration.")

    expire_due_locked(activity.pk, now)
    sequence = Registration.objects.filter(activity=activity).aggregate(
        last=Max("queue_sequence", default=0)
    )["last"] + 1
    seat = None
    if not unreserved_waitlist(activity.pk, now).exists():
        seat = available_seats(activity.pk, at=now).first()

    registration = Registration.objects.create(
        activity=activity,
        participant=participant,
        queue_sequence=sequence,
        initial_category=(
            Registration.InitialCategory.FORMAL if seat else Registration.InitialCategory.WAITLIST
        ),
        status=Registration.Status.CONFIRMED if seat else Registration.Status.WAITLISTED,
        request_id=request_id,
        submitted_at=now,
        confirmed_at=now if seat else None,
    )
    if seat is not None:
        occupy_seat(activity, seat.pk, participant.pk, now)
    participant.current_registration = registration
    participant.save(update_fields=("current_registration",))
    return registration


@transaction.atomic
def withdraw_registration(activity_id, participant_id, registration_id):
    """Withdraw one specific registration round. Replays cannot withdraw a later round."""
    activity = lock_activity(activity_id)
    now = timezone.now()
    registration = Registration.objects.select_related("participant").get(
        activity=activity, participant__activity=activity,
        participant_id=participant_id, pk=registration_id,
    )
    if registration.status == Registration.Status.WITHDRAWN:
        return registration
    if now >= activity.starts_at or registration.participant.current_registration_id != registration.pk:
        raise SignupError("This registration cannot be withdrawn.")

    expire_due_locked(activity.pk, now)
    for invitation in Invitation.objects.filter(
        registration=registration, status=Invitation.Status.PENDING
    ):
        finish_invitation(invitation, Invitation.Status.VOID, now)
    release_seat(activity, participant_id)
    registration.status = Registration.Status.WITHDRAWN
    registration.withdrawn_at = now
    registration.save(update_fields=("status", "withdrawn_at"))
    return registration
