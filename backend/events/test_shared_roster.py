from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

from .invitations import issue_invitation, respond_invitation
from .models import Activity, ActivityStaff, Invitation, Participant, Registration, Seat
from .seats import active_holds, available_seats, seat_assignments
from .signups import SignupError, submit_registration, withdraw_registration
from .test_invitations import event_time


class SharedRosterFixture:
    def setUp(self):
        super().setUp()
        self.when_open = event_time(21, 0, day=26)
        self.activity = self.make_activity()
        Seat.objects.bulk_create(
            [Seat(activity=self.activity, number=number) for number in range(1, 17)]
        )
        self.organizer = get_user_model().objects.create_user(username="organizer")
        ActivityStaff.objects.create(
            activity=self.activity, user=self.organizer, role=ActivityStaff.Role.ORGANIZER
        )
        self.occupied = []
        with patch("events.signups.timezone.now", return_value=self.when_open):
            for number in range(1, 16):
                person = self.make_participant(f"{number:04}")
                self.occupied.append(self.signup(person))

    def make_activity(self):
        return Activity.objects.create(
            title="Shared roster demo",
            capacity=16,
            registration_closes_at=event_time(22, 0, day=26),
            invitation_stops_at=event_time(12, 0),
            latest_confirmation_at=event_time(13, 30),
            starts_at=event_time(14, 0),
            release_starts_at=event_time(14, 30),
            absence_at=event_time(15, 0),
            ends_at=event_time(16, 0),
        )

    def make_participant(self, student_number, *, activity=None):
        return Participant.objects.create(
            activity=activity or self.activity,
            student_number=student_number,
            name=f"Demo participant {student_number}",
        )

    def signup(self, person, request_id=None):
        return submit_registration(self.activity.pk, person.pk, request_id=request_id or uuid4())

    def withdraw(self, registration):
        return withdraw_registration(self.activity.pk, registration.participant_id, registration.pk)

    def fill_then_invite(self, candidate):
        last = self.signup(self.make_participant("0016"))
        waitlisted = self.signup(candidate)
        self.assertEqual(waitlisted.status, Registration.Status.WAITLISTED)
        self.withdraw(last)
        seat = Seat.objects.get(activity=self.activity, number=16)
        invitation = issue_invitation(
            self.activity.pk, seat.pk, organizer_id=self.organizer.pk, request_id=uuid4()
        )
        return waitlisted, invitation

    def accept(self, person, invitation):
        return respond_invitation(self.activity.pk, person.pk, invitation.token, invitation.code)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SharedRosterTests(SharedRosterFixture, TestCase):
    def test_activity_scoped_identity_and_unique_seat_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_participant("0001")
        independent = self.make_participant("0001", activity=self.make_activity())
        self.assertEqual(independent.student_number, "0001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Seat.objects.create(activity=self.activity, number=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Seat.objects.filter(activity=self.activity, number=16).update(
                occupant_id=self.occupied[0].participant_id
            )
        self.assertEqual(seat_assignments(self.activity.pk).count(), 15)

    def test_fifteen_confirmed_and_one_active_hold_waitlist_a_new_signup(self):
        with patch("events.signups.timezone.now", return_value=self.when_open):
            first = self.make_participant("0017")
            original, issued = self.fill_then_invite(first)
            new = self.signup(self.make_participant("0018"))
            self.assertEqual(new.status, Registration.Status.WAITLISTED)
            self.assertGreater(new.queue_sequence, original.queue_sequence)
            self.assertEqual(seat_assignments(self.activity.pk).count(), 15)
            self.assertFalse(available_seats(self.activity.pk).exists())
            self.assertEqual(
                list(active_holds(self.activity.pk, self.when_open).values_list("pk", flat=True)),
                [issued.invitation_id],
            )

    def test_reapply_keeps_participant_id_and_voids_old_hold_and_replays(self):
        with patch("events.signups.timezone.now", return_value=self.when_open):
            person = self.make_participant("0017")
            first, invitation = self.fill_then_invite(person)
            self.withdraw(first)
            self.assertEqual(self.accept(person, invitation), "invalid")
            self.assertTrue(available_seats(self.activity.pk).exists())
            second = self.signup(person)
            self.assertEqual(second.status, Registration.Status.CONFIRMED)
            self.assertEqual(self.signup(person, first.request_id).pk, first.pk)
            self.withdraw(first)
            self.assertEqual(self.accept(person, invitation), "invalid")

        invitation_row = Invitation.objects.get(pk=invitation.invitation_id)
        self.assertEqual((invitation_row.status, invitation_row.registration_id), ("void", first.pk))
        first.refresh_from_db()
        person.refresh_from_db()
        self.assertEqual(first.status, Registration.Status.WITHDRAWN)
        self.assertEqual(second.participant_id, first.participant_id)
        self.assertGreater(second.queue_sequence, first.queue_sequence)
        self.assertEqual(person.current_registration_id, second.pk)
        self.assertEqual(person.registrations.count(), 2)
        self.assertEqual(seat_assignments(self.activity.pk).count(), 16)

    def test_confirmation_history_remains_after_formal_withdrawal_and_reapplication(self):
        with patch("events.signups.timezone.now", return_value=self.when_open):
            person = self.make_participant("0017")
            first, invitation = self.fill_then_invite(person)
            self.assertEqual(self.accept(person, invitation), "accepted")
            occupied_seat = Seat.objects.get(occupant=person)
            self.withdraw(first)
            second = self.signup(person)
            self.assertEqual(self.accept(person, invitation), "invalid")
        first.refresh_from_db()
        occupied_seat.refresh_from_db()
        self.assertEqual(first.status, Registration.Status.WITHDRAWN)
        self.assertEqual(first.confirmed_at, self.when_open)
        self.assertEqual(second.status, Registration.Status.CONFIRMED)
        self.assertEqual(occupied_seat.vacancy_round, 3)
        self.assertEqual(Invitation.objects.get(pk=invitation.invitation_id).status, "accepted")

    def test_new_signup_does_not_bypass_an_existing_waitlist(self):
        with patch("events.signups.timezone.now", return_value=self.when_open):
            last = self.signup(self.make_participant("0016"))
            waiting = self.signup(self.make_participant("0017"))
            self.withdraw(last)
            newcomer = self.signup(self.make_participant("0018"))
            self.assertEqual(newcomer.status, Registration.Status.WAITLISTED)
            self.assertGreater(newcomer.queue_sequence, waiting.queue_sequence)
            self.assertEqual(available_seats(self.activity.pk).count(), 1)

    def test_registration_and_withdrawal_boundaries(self):
        person = self.make_participant("0016")
        with patch("events.signups.timezone.now", return_value=event_time(21, 59, 59, day=26)):
            registration = self.signup(person)
            self.assertEqual(registration.status, Registration.Status.CONFIRMED)
        with patch("events.signups.timezone.now", return_value=self.activity.registration_closes_at):
            self.withdraw(registration)
            with self.assertRaises(SignupError):
                self.signup(person)
            self.assertEqual(self.signup(person, registration.request_id).status, "withdrawn")
        with patch("events.signups.timezone.now", return_value=self.activity.starts_at):
            with self.assertRaises(SignupError):
                self.withdraw(self.occupied[0])


class SignupConcurrencyTests(SharedRosterFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_connections_compete_for_the_last_seat_then_replay(self):
        people = [self.make_participant("0016"), self.make_participant("0017")]
        request_ids = [uuid4(), uuid4()]
        ready = Barrier(2)

        def submit_in_connection(person, request_id):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return self.signup(person, request_id)
            finally:
                connections.close_all()

        with patch("events.signups.timezone.now", return_value=self.when_open):
            with ThreadPoolExecutor(max_workers=2) as workers:
                pending = [
                    workers.submit(submit_in_connection, person, request_id)
                    for person, request_id in zip(people, request_ids)
                ]
                results = [item.result(timeout=30) for item in pending]
            self.assertEqual(self.signup(people[0], request_ids[0]).pk, results[0].pk)

        confirmed, waiting = sorted(results, key=lambda registration: registration.queue_sequence)
        self.assertEqual((confirmed.queue_sequence, waiting.queue_sequence), (16, 17))
        self.assertEqual(confirmed.status, Registration.Status.CONFIRMED)
        self.assertEqual(waiting.status, Registration.Status.WAITLISTED)
        self.assertEqual(seat_assignments(self.activity.pk).count(), 16)
        self.assertEqual(Registration.objects.filter(activity=self.activity).count(), 17)
