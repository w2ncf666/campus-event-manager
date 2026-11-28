"""Create a separate 100-registration fixture in a test deployment using manage.py shell."""

import os
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from events.models import Activity, ActivityStaff, Participant, Registration, RosterEvent, Seat


def create_fixture(check_in_staff):
    now = timezone.now()
    with transaction.atomic():
        activity = Activity.objects.create(
            title=f"NFR-02 模拟名单 {uuid4().hex[:8]}",
            capacity=80,
            registration_closes_at=now - timedelta(days=2),
            invitation_stops_at=now - timedelta(hours=2),
            latest_confirmation_at=now - timedelta(minutes=20),
            starts_at=now - timedelta(minutes=10),
            release_starts_at=now - timedelta(minutes=2),
            absence_at=now + timedelta(minutes=30),
            ends_at=now + timedelta(hours=2),
        )
        ActivityStaff.objects.create(
            activity=activity, user=check_in_staff, role=ActivityStaff.Role.CHECK_IN,
        )
        Participant.objects.bulk_create([
            Participant(activity=activity, name=f"模拟人员 {i:03}", student_number=f"TEST{i:05}")
            for i in range(1, 101)
        ])
        people = list(Participant.objects.filter(activity=activity).order_by("student_number"))
        submitted_at = activity.registration_closes_at - timedelta(hours=1)
        formal = Registration.InitialCategory.FORMAL
        statuses = (
            [(formal, Registration.Status.CONFIRMED)] * 70
            + [(formal, Registration.Status.RELEASED)] * 10
            + [(Registration.InitialCategory.WAITLIST, Registration.Status.ONSITE_ONLY)] * 20
        )
        Registration.objects.bulk_create([
            Registration(
                activity=activity, participant=person, queue_sequence=i,
                initial_category=category, status=status, request_id=uuid4(),
                submitted_at=submitted_at,
                confirmed_at=submitted_at if category == formal else None,
            )
            for i, (person, (category, status)) in enumerate(zip(people, statuses), start=1)
        ])
        registrations = list(Registration.objects.filter(activity=activity).order_by("queue_sequence"))
        for person, registration in zip(people, registrations):
            person.current_registration = registration
        Participant.objects.bulk_update(people, ["current_registration"])

        Seat.objects.bulk_create([
            Seat(activity=activity, number=i, occupant=people[i-1], vacancy_round=1)
            for i in range(1, 71)
        ] + [
            Seat(activity=activity, number=i, vacancy_round=2) for i in range(71, 81)
        ])
        released_seats = Seat.objects.filter(activity=activity, number__gt=70).order_by("number")
        RosterEvent.objects.bulk_create([
            RosterEvent(
                participant=person, registration=registration, seat=seat,
                kind=RosterEvent.Kind.RELEASED, occurred_at=now - timedelta(minutes=1),
                recorded_by=check_in_staff, reason="NFR-02 模拟释位",
            )
            for person, registration, seat in zip(people[70:80], registrations[70:80], released_seats)
        ] + [
            RosterEvent(
                participant=person, registration=registration,
                kind=RosterEvent.Kind.ARRIVED, occurred_at=now, recorded_by=check_in_staff,
            )
            for person, registration in zip(people[80:], registrations[80:])
        ])
    return activity


username = os.environ.get("NFR02_STAFF_USERNAME", "").strip()
if not username:
    raise SystemExit("Set NFR02_STAFF_USERNAME to an existing account on the test deployment.")
staff = get_user_model().objects.filter(username=username, is_active=True).first()
if staff is None:
    raise SystemExit("The named account does not exist or is inactive.")

activity = create_fixture(staff)
print(f"Created {activity.title}: 70 formal, 20 on-site waiting, 10 historical releases.")
print(f"Open {reverse('onsite:home')} and select the new fixture. Roster: {reverse('onsite:roster', args=[activity.pk])}")
