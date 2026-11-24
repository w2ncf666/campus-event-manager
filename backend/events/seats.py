from django.db.models import Exists, F, OuterRef
from django.utils import timezone

from .models import Activity, Invitation, Participant, Registration, Seat


class SeatError(ValueError):
    """The requested occupancy does not match the current activity roster."""


def lock_activity(activity_id):
    """Call inside a transaction before reading or writing this activity's seat state."""
    return Activity.objects.select_for_update().get(pk=activity_id)


def current_registrations(activity_id):
    return Registration.objects.filter(
        activity_id=activity_id,
        participant__activity_id=activity_id,
        pk=F("participant__current_registration_id"),
    )


def active_holds(activity_id, at):
    return Invitation.objects.filter(
        seat__activity_id=activity_id,
        seat__occupant_id__isnull=True,
        seat__number__lte=F("seat__activity__capacity"),
        vacancy_round=F("seat__vacancy_round"),
        registration_id__in=current_registrations(activity_id).filter(
            status=Registration.Status.WAITLISTED
        ).values("pk"),
        status=Invitation.Status.PENDING,
        expires_at__gt=at,
    )


def available_seats(activity_id, *, at=None):
    """Shared vacancy query. Pass the server time read after locking for writes."""
    holds = active_holds(activity_id, at or timezone.now()).filter(seat_id=OuterRef("pk"))
    return Seat.objects.filter(
        activity_id=activity_id, occupant_id__isnull=True, number__lte=F("activity__capacity")
    ).filter(~Exists(holds)).order_by("number")


def seat_assignments(activity_id):
    """Read the current shared roster, including anyone admitted on site."""
    return Seat.objects.filter(
        activity_id=activity_id, occupant_id__isnull=False
    ).select_related("occupant", "occupant__current_registration").order_by("number")


def occupy_seat(activity, seat_id, participant_id, at):
    """Assign a free seat while holding the activity lock."""
    seat = available_seats(activity.pk, at=at).filter(pk=seat_id).first()
    if seat is None or not Participant.objects.filter(pk=participant_id, activity=activity).exists():
        raise SeatError("The seat or participant is unavailable in this activity.")
    seat.occupant_id = participant_id
    seat.save(update_fields=("occupant",))
    return seat


def release_seat(activity, participant_id):
    """Release the participant's current seat and start its next vacancy round."""
    seat = Seat.objects.filter(activity=activity, occupant_id=participant_id).first()
    if seat is not None:
        seat.occupant = None
        seat.vacancy_round += 1
        seat.save(update_fields=("occupant", "vacancy_round"))
    return seat
