from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings

from .checkin import (
    OnsiteError,
    check_in,
    get_checkin_roster,
    record_late_note,
    release_formal_seat,
)
from .models import ActivityStaff, Attendance, Registration, RosterEvent
from .seats import available_seats
from .signups import withdraw_registration
from .test_invitations import InvitationFixture, event_time


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CheckinTests(InvitationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.staff = get_user_model().objects.create_user(username="check-in")
        ActivityStaff.objects.create(
            activity=self.activity, user=self.staff, role=ActivityStaff.Role.CHECK_IN
        )
        self.finance = get_user_model().objects.create_user(username="finance")
        ActivityStaff.objects.create(
            activity=self.activity, user=self.finance, role=ActivityStaff.Role.FINANCE
        )

    def confirm(self, person, seat):
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = self.issue(seat)
        with patch("events.invitations.timezone.now", return_value=event_time(13, 29, 59)):
            self.assertEqual(self.respond(issued, person), "accepted")

    def sign_in(self, person, *, staff=None):
        return check_in(self.activity.pk, person.pk, staff_id=(staff or self.staff).pk)

    def release(self, person):
        return release_formal_seat(
            self.activity.pk, person.pk, staff_id=self.staff.pk, reason="核对未到场"
        )

    def roster(self, *, staff=None):
        return get_checkin_roster(self.activity.pk, staff_id=(staff or self.staff).pk)

    def test_accepted_invitation_is_in_shared_roster_and_checkin_is_idempotent(self):
        self.confirm(self.a, self.first_seat)
        with patch("events.checkin.timezone.now", return_value=event_time(13, 59, 59)):
            self.assertEqual([seat.occupant_id for seat in self.roster()], [self.a.pk])
            with self.assertRaises(OnsiteError):
                self.sign_in(self.a)

        with patch("events.checkin.timezone.now", return_value=event_time(14, 0)):
            first = self.sign_in(self.a)
            self.assertEqual(self.sign_in(self.a).pk, first.pk)
            with self.assertRaises(OnsiteError):
                self.sign_in(self.b)
        self.assertEqual(first.admission_mode, Attendance.AdmissionMode.ONLINE)
        self.assertEqual(first.seat_id, self.first_seat.pk)
        self.assertEqual(first.checked_in_at, event_time(14, 0))
        self.assertEqual(first.recorded_by_id, self.staff.pk)
        self.assertEqual(Attendance.objects.count(), 1)
        self.first_seat.refresh_from_db()
        self.assertEqual(self.first_seat.occupant_id, self.a.pk)

    def test_role_protects_both_roster_and_actions_and_checkin_closes(self):
        self.confirm(self.a, self.first_seat)
        with patch("events.checkin.timezone.now", return_value=event_time(14, 0)):
            for user in (self.finance, self.organizer):
                with self.subTest(user=user.username):
                    with self.assertRaises(PermissionDenied):
                        self.roster(staff=user)
                    with self.assertRaises(PermissionDenied):
                        self.sign_in(self.a, staff=user)
        with patch("events.checkin.timezone.now", return_value=event_time(16, 0)):
            with self.assertRaises(OnsiteError):
                self.sign_in(self.a)
            with self.assertRaises(OnsiteError):
                self.release(self.a)
        self.assertFalse(Attendance.objects.exists())

    def test_release_at_exact_cutoff_creates_one_vacancy_and_preserves_registration(self):
        self.confirm(self.a, self.first_seat)
        self.confirm(self.b, self.second_seat)
        with patch("events.checkin.timezone.now", return_value=event_time(14, 29, 59)):
            self.sign_in(self.b)
            with self.assertRaises(OnsiteError):
                self.release(self.a)
            self.assertFalse(available_seats(self.activity.pk).exists())

        with patch("events.checkin.timezone.now", return_value=event_time(14, 30)):
            first = self.release(self.a)
            self.assertEqual(self.release(self.a).pk, first.pk)
            with self.assertRaises(OnsiteError):
                self.release(self.b)
            self.assertEqual(
                list(available_seats(self.activity.pk).values_list("pk", flat=True)),
                [self.first_seat.pk],
            )
        self.first_seat.refresh_from_db()
        self.a.refresh_from_db()
        self.assertEqual(self.first_seat.vacancy_round, 2)
        self.assertEqual(self.a.current_registration.status, Registration.Status.RELEASED)
        self.assertEqual(first.registration_id, self.a.current_registration_id)
        self.assertEqual(first.occurred_at, event_time(14, 30))
        self.assertEqual(first.recorded_by_id, self.staff.pk)
        self.assertEqual(first.reason, "核对未到场")

    def test_late_protection_only_prevents_release_until_cutoff_and_is_not_absence(self):
        self.confirm(self.a, self.first_seat)
        self.confirm(self.b, self.second_seat)
        with patch("events.checkin.timezone.now", return_value=event_time(14, 29, 59)):
            for _ in range(2):
                record_late_note(
                    self.activity.pk, self.a.pk, staff_id=self.staff.pk, reason="QQ 留言确认"
                )
        with patch("events.checkin.timezone.now", return_value=event_time(14, 30)):
            self.release(self.b)
        with patch("events.checkin.timezone.now", return_value=event_time(14, 59, 59)):
            with self.assertRaises(OnsiteError):
                self.release(self.a)
            with self.assertRaises(OnsiteError):
                record_late_note(self.activity.pk, self.b.pk, staff_id=self.staff.pk, reason="重试")

        with patch("events.checkin.timezone.now", return_value=event_time(15, 0)):
            with self.assertRaises(OnsiteError):
                record_late_note(self.activity.pk, self.a.pk, staff_id=self.staff.pk, reason="重试")
            self.release(self.a)
            self.roster()
            self.roster()
        note = RosterEvent.objects.get(kind=RosterEvent.Kind.LATE_NOTE)
        self.assertEqual((note.participant_id, note.reason), (self.a.pk, "QQ 留言确认"))
        absent = RosterEvent.objects.get(kind=RosterEvent.Kind.STAGE_ABSENT)
        self.assertEqual((absent.participant_id, absent.occurred_at), (self.b.pk, event_time(15, 0)))
        self.assertIsNone(absent.recorded_by_id)

    def test_checkin_at_absence_cutoff_retains_both_absence_and_attendance(self):
        self.confirm(self.a, self.first_seat)
        self.confirm(self.b, self.second_seat)
        with patch("events.checkin.timezone.now", return_value=event_time(13, 59, 59)):
            withdraw_registration(self.activity.pk, self.b.pk, self.b.current_registration_id)
        with patch("events.checkin.timezone.now", return_value=event_time(15, 0)):
            attendance = self.sign_in(self.a)
            self.roster()
        absence = RosterEvent.objects.get(kind=RosterEvent.Kind.STAGE_ABSENT)
        self.assertEqual(absence.participant_id, attendance.participant_id)
        self.assertEqual(absence.occurred_at, attendance.checked_in_at)

    def test_on_time_checkin_is_excluded_from_stage_absence(self):
        self.confirm(self.a, self.first_seat)
        with patch("events.checkin.timezone.now", return_value=event_time(14, 59, 59)):
            self.sign_in(self.a)
        with patch("events.checkin.timezone.now", return_value=event_time(15, 0)):
            self.roster()
        self.assertFalse(RosterEvent.objects.filter(kind=RosterEvent.Kind.STAGE_ABSENT).exists())
