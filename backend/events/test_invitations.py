from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

from .invitations import (
    InvitationError,
    expire_invitations,
    issue_invitation,
    next_candidate,
    reissue_invitation,
    respond_invitation,
    skip_candidate,
)
from .models import Activity, ActivityStaff, Invitation, Participant, Registration, Seat
from .seats import available_seats, seat_assignments
from .signups import withdraw_registration


def event_time(hour, minute, second=0, *, day=28):
    return datetime(
        2026, 11, day, hour, minute, second, tzinfo=timezone(timedelta(hours=8))
    )


class InvitationFixture:
    def setUp(self):
        super().setUp()
        self.activity = Activity.objects.create(
            title="Badminton demo",
            capacity=2,
            registration_closes_at=event_time(22, 0, day=26),
            invitation_stops_at=event_time(12, 0),
            latest_confirmation_at=event_time(13, 30),
            starts_at=event_time(14, 0),
            release_starts_at=event_time(14, 30),
            absence_at=event_time(15, 0),
            ends_at=event_time(16, 0),
            invitation_minutes=120,
        )
        self.organizer = get_user_model().objects.create_user(username="organizer")
        ActivityStaff.objects.create(
            activity=self.activity, user=self.organizer, role=ActivityStaff.Role.ORGANIZER
        )
        self.first_seat = Seat.objects.create(activity=self.activity, number=1)
        self.second_seat = Seat.objects.create(activity=self.activity, number=2)
        # Create B first to exercise ordering by queue sequence rather than row ID.
        self.b = self.make_candidate("0002", 2)
        self.a = self.make_candidate("0001", 1)

    def make_candidate(self, number, sequence):
        participant = Participant.objects.create(
            activity=self.activity,
            student_number=number,
            name=f"Demo participant {number}",
        )
        participant.current_registration = Registration.objects.create(
            activity=self.activity,
            participant=participant,
            queue_sequence=sequence,
            initial_category=Registration.InitialCategory.WAITLIST,
            status=Registration.Status.WAITLISTED,
            request_id=uuid4(),
            submitted_at=event_time(20, 0, day=26),
        )
        participant.save(update_fields=("current_registration",))
        return participant

    def issue(self, seat, request_id=None):
        return issue_invitation(
            self.activity.pk,
            seat.pk,
            organizer_id=self.organizer.pk,
            request_id=request_id or uuid4(),
        )

    def respond(self, issued, participant, *, accept=True, code=None):
        return respond_invitation(
            self.activity.pk,
            participant.pk,
            issued.token,
            issued.code if code is None else code,
            accept=accept,
        )


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InvitationTests(InvitationFixture, TestCase):
    def test_preview_and_issue_revalidate_the_candidate_selection(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            preview = next_candidate(
                self.activity.pk, self.first_seat.pk, organizer_id=self.organizer.pk
            )
            self.assertEqual(preview.pk, self.a.current_registration_id)
            self.issue(self.second_seat)
            with self.assertRaises(InvitationError):
                issue_invitation(
                    self.activity.pk, self.first_seat.pk, organizer_id=self.organizer.pk,
                    request_id=uuid4(), expected_registration_id=preview.pk,
                    expected_vacancy_round=self.first_seat.vacancy_round,
                )
            self.assertEqual(next_candidate(
                self.activity.pk, self.first_seat.pk, organizer_id=self.organizer.pk
            ).pk, self.b.current_registration_id)

    def test_holds_choose_queue_order_and_do_not_double_hold_a_candidate(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            first = self.issue(self.first_seat)
            self.assertEqual(
                Invitation.objects.get(pk=first.invitation_id).registration.participant_id, self.a.pk
            )
            self.assertEqual(
                [seat.pk for seat in available_seats(self.activity.pk)], [self.second_seat.pk]
            )
            second = self.issue(self.second_seat)
            self.assertEqual(
                Invitation.objects.get(pk=second.invitation_id).registration.participant_id, self.b.pk
            )
            with self.assertRaises(InvitationError):
                self.issue(self.first_seat)
            self.assertFalse(available_seats(self.activity.pk).exists())
        self.first_seat.refresh_from_db()
        self.assertIsNone(self.first_seat.occupant_id)

    def test_acceptance_updates_shared_seat_once_and_expiry_opens_other_seat(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            first = self.issue(self.first_seat)
            second = self.issue(self.second_seat)

        for issued in (first, second):
            self.assertEqual(
                Invitation.objects.get(pk=issued.invitation_id).expires_at, event_time(13, 30)
            )

        with patch("events.invitations.timezone.now", return_value=event_time(13, 29, 59)):
            self.assertEqual(self.respond(first, self.a), "accepted")
            self.respond(first, self.a)
            self.assertFalse(available_seats(self.activity.pk).exists())
            signed_up = seat_assignments(self.activity.pk).values_list("occupant_id", flat=True)
            self.assertEqual(list(signed_up), [self.a.pk])
        self.a.refresh_from_db()
        self.first_seat.refresh_from_db()
        self.assertEqual(self.a.current_registration.status, Registration.Status.CONFIRMED)
        self.assertEqual(self.first_seat.occupant_id, self.a.pk)
        self.assertEqual(
            Invitation.objects.filter(seat=self.first_seat, status=Invitation.Status.ACCEPTED).count(),
            1,
        )

        with patch("events.invitations.timezone.now", return_value=event_time(13, 30)):
            self.assertEqual(
                [seat.pk for seat in available_seats(self.activity.pk)], [self.second_seat.pk]
            )
            self.assertEqual(self.respond(second, self.b), "expired")
            expire_invitations(self.activity.pk)
            self.assertEqual(expire_invitations(self.activity.pk), 0)
        self.b.refresh_from_db()
        self.second_seat.refresh_from_db()
        self.assertEqual(self.b.current_registration.status, Registration.Status.ONSITE_ONLY)
        self.assertIsNone(self.second_seat.occupant_id)
        self.assertEqual(
            Invitation.objects.get(pk=second.invitation_id).status, Invitation.Status.EXPIRED
        )
        with patch("events.invitations.timezone.now", return_value=event_time(14, 0)):
            self.assertEqual(
                [seat.pk for seat in available_seats(self.activity.pk)], [self.second_seat.pk]
            )

    def test_wrong_participant_and_confirmation_code_do_not_change_the_hold(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = self.issue(self.first_seat)
            wrong_code = "000000" if issued.code != "000000" else "000001"
            self.assertEqual(self.respond(issued, self.b), "invalid")
            self.assertEqual(self.respond(issued, self.a, code=wrong_code), "invalid")
            self.assertNotIn(self.first_seat.pk, [s.pk for s in available_seats(self.activity.pk)])

        self.first_seat.refresh_from_db()
        self.a.refresh_from_db()
        self.assertIsNone(self.first_seat.occupant_id)
        self.assertEqual(self.a.current_registration.status, Registration.Status.WAITLISTED)
        self.assertEqual(
            Invitation.objects.get(pk=issued.invitation_id).status, Invitation.Status.PENDING
        )

    def test_five_wrong_codes_throttle_without_releasing_the_seat(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = self.issue(self.first_seat)
            wrong_code = "000000" if issued.code != "000000" else "000001"
            for attempt in range(1, 6):
                expected = "throttled" if attempt == 5 else "invalid"
                self.assertEqual(self.respond(issued, self.a, code=wrong_code), expected)
        with patch("events.invitations.timezone.now", return_value=event_time(11, 54, 59)):
            self.assertEqual(self.respond(issued, self.a), "throttled")
            self.assertNotIn(self.first_seat.pk, [s.pk for s in available_seats(self.activity.pk)])
        with patch("events.invitations.timezone.now", return_value=event_time(11, 55)):
            self.assertEqual(self.respond(issued, self.a), "accepted")

    def test_decline_releases_hold_without_changing_original_queue_sequence(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = self.issue(self.first_seat)
            self.assertEqual(self.respond(issued, self.a, accept=False), "declined")
            next_issued = self.issue(self.first_seat)
        self.a.refresh_from_db()
        self.assertEqual(self.a.current_registration.status, Registration.Status.ONSITE_ONLY)
        self.assertEqual(self.a.current_registration.queue_sequence, 1)
        self.assertEqual(
            Invitation.objects.get(pk=next_issued.invitation_id).registration.participant_id, self.b.pk
        )

    def test_reissue_rotates_credentials_with_the_same_deadline_and_cooldown(self):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = self.issue(self.first_seat)
            wrong_code = "000000" if issued.code != "000000" else "000001"
            for _ in range(5):
                self.respond(issued, self.a, code=wrong_code)
        request_id = uuid4()
        with patch("events.invitations.timezone.now", return_value=event_time(11, 51)):
            replacement = reissue_invitation(
                self.activity.pk, issued.invitation_id, organizer_id=self.organizer.pk,
                request_id=request_id, reason="Delivery message lost",
            )
            self.assertEqual(self.respond(issued, self.a), "invalid")
            self.assertEqual(self.respond(replacement, self.a), "throttled")
            with self.assertRaises(InvitationError):
                reissue_invitation(
                    self.activity.pk, issued.invitation_id, organizer_id=self.organizer.pk,
                    request_id=request_id, reason="Delivery message lost",
                )
        before = Invitation.objects.get(pk=issued.invitation_id)
        after = Invitation.objects.get(pk=replacement.invitation_id)
        self.assertEqual(before.status, Invitation.Status.REISSUED)
        self.assertEqual(after.replaces_id, before.pk)
        self.assertEqual(after.registration_id, before.registration_id)
        self.assertEqual((after.seat_id, after.vacancy_round), (before.seat_id, before.vacancy_round))
        self.assertEqual(after.expires_at, event_time(13, 30))
        self.assertNotEqual(replacement.code, issued.code)
        with patch("events.invitations.timezone.now", return_value=event_time(12, 0)):
            with self.assertRaises(InvitationError):
                reissue_invitation(
                    self.activity.pk, after.pk, organizer_id=self.organizer.pk,
                    request_id=uuid4(), reason="Delivery message lost",
                )
        with patch("events.invitations.timezone.now", return_value=event_time(13, 29, 59)):
            self.assertEqual(self.respond(replacement, self.a), "accepted")

    def test_new_invitation_is_rejected_at_the_stop_time_with_a_usable_seat(self):
        with patch("events.invitations.timezone.now", return_value=event_time(12, 0)):
            with self.assertRaises(InvitationError):
                self.issue(self.first_seat)
            self.assertIn(self.first_seat.pk, [s.pk for s in available_seats(self.activity.pk)])
        self.assertEqual(Invitation.objects.count(), 0)

    def test_account_without_activity_organizer_role_cannot_issue_an_invitation(self):
        ordinary_user = get_user_model().objects.create_user(username="ordinary")
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            with self.assertRaises(InvitationError):
                issue_invitation(
                    self.activity.pk,
                    self.first_seat.pk,
                    organizer_id=ordinary_user.pk,
                    request_id=uuid4(),
                )
        self.assertEqual(Invitation.objects.count(), 0)

    def test_retried_request_cannot_issue_another_invitation_after_expiry(self):
        self.activity.invitation_minutes = 10
        self.activity.save(update_fields=["invitation_minutes"])
        request_id = uuid4()
        with patch("events.invitations.timezone.now", return_value=event_time(10, 30)):
            first = self.issue(self.first_seat, request_id)

        with patch("events.invitations.timezone.now", return_value=event_time(10, 40)):
            self.assertEqual(expire_invitations(self.activity.pk), 1)
            try:
                replay = self.issue(self.first_seat, request_id)
            except InvitationError:
                pass
            else:
                self.assertEqual(replay.invitation_id, first.invitation_id)
            self.assertEqual(Invitation.objects.filter(seat=self.first_seat).count(), 1)
            new_issue = self.issue(self.first_seat)
        self.assertEqual(
            Invitation.objects.get(pk=new_issue.invitation_id).registration.participant_id, self.b.pk
        )

    def test_skipping_current_vacancy_preserves_priority_on_an_independent_seat(self):
        self.make_candidate("0003", 3)
        self.activity.invitation_minutes = 10
        self.activity.save(update_fields=["invitation_minutes"])
        with patch("events.invitations.timezone.now", return_value=event_time(10, 30)):
            skip_candidate(
                self.activity.pk,
                self.first_seat.pk,
                self.a.pk,
                organizer_id=self.organizer.pk,
                reason="Temporarily unavailable for this vacancy",
                vacancy_round=self.first_seat.vacancy_round,
            )
            first = self.issue(self.first_seat)
            self.assertEqual(
                Invitation.objects.get(pk=first.invitation_id).registration.participant_id, self.b.pk
            )
        with patch("events.invitations.timezone.now", return_value=event_time(10, 40)):
            self.assertEqual(expire_invitations(self.activity.pk), 1)
            following = self.issue(self.first_seat)
            second = self.issue(self.second_seat)
        self.assertEqual(
            Invitation.objects.get(pk=following.invitation_id).registration.queue_sequence, 3
        )
        self.assertEqual(
            Invitation.objects.get(pk=second.invitation_id).registration.participant_id, self.a.pk
        )
        self.a.refresh_from_db()
        self.assertEqual(self.a.current_registration.queue_sequence, 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InvitationConcurrencyTests(InvitationFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_confirm_and_withdraw_resolve_on_the_same_activity_lock(self):
        ready = Barrier(2)

        def run_in_connection(operation):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()

        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = self.issue(self.first_seat)
            with ThreadPoolExecutor(max_workers=2) as workers:
                confirmation = workers.submit(run_in_connection, lambda: self.respond(issued, self.a))
                withdrawal = workers.submit(
                    run_in_connection,
                    lambda: withdraw_registration(
                        self.activity.pk, self.a.pk, self.a.current_registration_id
                    ),
                )
                result = confirmation.result(timeout=30)
                self.assertEqual(withdrawal.result(timeout=30).status, Registration.Status.WITHDRAWN)

        invitation = Invitation.objects.get(pk=issued.invitation_id)
        self.first_seat.refresh_from_db()
        self.assertIsNone(self.first_seat.occupant_id)
        if result == "accepted":
            self.assertEqual(invitation.status, Invitation.Status.ACCEPTED)
            self.assertEqual(self.first_seat.vacancy_round, 2)
        else:
            self.assertEqual(result, "invalid")
            self.assertEqual(invitation.status, Invitation.Status.VOID)
            self.assertEqual(self.first_seat.vacancy_round, 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_independent_connections_can_only_hold_the_same_seat_once(self):
        ready = Barrier(2)

        def issue_from_separate_connection():
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return self.issue(self.first_seat).invitation_id
            except InvitationError:
                return None
            finally:
                connections.close_all()

        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            with ThreadPoolExecutor(max_workers=2) as workers:
                requests = [workers.submit(issue_from_separate_connection) for _ in range(2)]
                results = [request.result(timeout=30) for request in requests]

        successful_ids = [result for result in results if result is not None]
        self.assertEqual(len(successful_ids), 1)
        self.assertEqual(
            list(
                Invitation.objects.filter(seat=self.first_seat, status=Invitation.Status.PENDING)
                .values_list("pk", flat=True)
            ),
            successful_ids,
        )
