from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

from .admission import admit_next, get_arrival_queue, record_arrival, remove_arrival
from .checkin import OnsiteError
from .invitations import issue_invitation
from .models import Activity, ActivityStaff, Attendance, Invitation, Participant, Registration
from .models import RosterEvent, Seat
from .seats import available_seats
from .test_invitations import event_time


class OnsiteAdmissionFixture:
    def setUp(self):
        super().setUp()
        self.activity = Activity.objects.create(
            title="现场补录验收",
            capacity=5,
            registration_closes_at=event_time(22, 0, day=26),
            invitation_stops_at=event_time(12, 0),
            latest_confirmation_at=event_time(13, 30),
            starts_at=event_time(14, 0),
            release_starts_at=event_time(14, 30),
            absence_at=event_time(15, 0),
            ends_at=event_time(16, 0),
        )
        Seat.objects.bulk_create(
            [Seat(activity=self.activity, number=number) for number in range(1, 6)]
        )
        users = get_user_model().objects
        self.staff = users.create_user(username="check-in")
        self.organizer = users.create_user(username="organizer")
        ActivityStaff.objects.create(
            activity=self.activity, user=self.staff, role=ActivityStaff.Role.CHECK_IN
        )
        ActivityStaff.objects.create(
            activity=self.activity, user=self.organizer, role=ActivityStaff.Role.ORGANIZER
        )

    def _registration(self, student_number, sequence, *, status=Registration.Status.WAITLISTED):
        person = Participant.objects.create(
            activity=self.activity, student_number=student_number, name=f"参与者 {student_number}"
        )
        formal = status == Registration.Status.RELEASED
        submitted_at = event_time(21, 0, day=26)
        registration = Registration.objects.create(
            activity=self.activity,
            participant=person,
            queue_sequence=sequence,
            initial_category=(
                Registration.InitialCategory.FORMAL if formal else Registration.InitialCategory.WAITLIST
            ),
            status=status,
            request_id=uuid4(),
            submitted_at=submitted_at,
            confirmed_at=submitted_at if formal else None,
        )
        person.current_registration = registration
        person.save(update_fields=("current_registration",))
        return person

    def _arrive(self, student_number, name=None):
        return record_arrival(
            self.activity.pk,
            staff_id=self.staff.pk,
            student_number=student_number,
            name=name or f"参与者 {student_number}",
        )

    def _admit(self, person):
        return admit_next(self.activity.pk, person.pk, staff_id=self.staff.pk)

    def _queue(self):
        return get_arrival_queue(self.activity.pk, staff_id=self.staff.pk)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OnsiteAdmissionTests(OnsiteAdmissionFixture, TestCase):
    def test_expired_hold_is_available_for_onsite_admission_at_opening(self):
        waitlisted = self._registration("0003", 3)
        seat = Seat.objects.get(activity=self.activity, number=1)
        with patch("events.invitations.timezone.now", return_value=event_time(11, 50)):
            issued = issue_invitation(
                self.activity.pk, seat.pk, organizer_id=self.organizer.pk, request_id=uuid4()
            )
        self.assertFalse(
            available_seats(self.activity.pk, at=event_time(13, 29, 59)).filter(pk=seat.pk).exists()
        )
        self.assertTrue(
            available_seats(self.activity.pk, at=event_time(13, 30)).filter(pk=seat.pk).exists()
        )
        with patch("events.admission.timezone.now", return_value=event_time(13, 59, 59)):
            with self.assertRaises(OnsiteError):
                self._admit(waitlisted)
        with patch("events.admission.timezone.now", return_value=event_time(14, 0)):
            self._arrive(waitlisted.student_number)
            attendance = self._admit(waitlisted)
        self.assertEqual(attendance.admission_mode, Attendance.AdmissionMode.ONSITE_WAITLIST)
        self.assertEqual(attendance.seat_id, seat.pk)
        self.assertEqual(attendance.participant_id, waitlisted.pk)
        self.assertEqual(attendance.checked_in_at, event_time(14, 0))
        self.assertEqual(
            Invitation.objects.get(pk=issued.invitation_id).status, Invitation.Status.EXPIRED
        )
        self.assertEqual(self._queue(), [])
        with patch("events.admission.timezone.now", return_value=event_time(16, 0)):
            with self.assertRaises(OnsiteError):
                self._admit(waitlisted)

    def test_waitlist_order_presence_and_walk_in_order(self):
        early = self._registration("0003", 3)
        late = self._registration("0012", 12, status=Registration.Status.ONSITE_ONLY)
        with patch("events.admission.timezone.now", return_value=event_time(14, 5)):
            walk_in_first = self._arrive("0031")
            self._arrive(late.student_number)
            walk_in_last = self._arrive("0032")
            self._arrive(early.student_number)
            self._arrive(early.student_number)
            self.assertEqual(
                [person.pk for person, _ in self._queue()],
                [early.pk, late.pk, walk_in_first.pk, walk_in_last.pk],
            )
            with self.assertRaises(OnsiteError):
                self._admit(late)
            remove_arrival(self.activity.pk, early.pk, staff_id=self.staff.pk)
            remove_arrival(self.activity.pk, early.pk, staff_id=self.staff.pk)
            self.assertEqual(
                list(early.roster_events.order_by("pk").values_list("kind", flat=True)),
                [RosterEvent.Kind.ARRIVED, RosterEvent.Kind.LEFT],
            )
            with self.assertRaises(OnsiteError):
                self._admit(early)
            admitted = self._admit(late)
            self._arrive(early.student_number)
            self.assertEqual(self._admit(late).pk, admitted.pk)
            self.assertEqual(
                self._admit(early).admission_mode, Attendance.AdmissionMode.ONSITE_WAITLIST
            )
            for walk_in in (walk_in_first, walk_in_last):
                self.assertEqual(
                    self._admit(walk_in).admission_mode, Attendance.AdmissionMode.ONSITE_WALK_IN
                )
        self.assertEqual(self._queue(), [])
        self.assertEqual(Attendance.objects.count(), 4)
        self.assertEqual(
            Seat.objects.filter(activity=self.activity, occupant__isnull=False).count(), 4
        )

    def test_released_formal_participant_reuses_identity_and_preserves_history(self):
        person = self._registration("0004", 4, status=Registration.Status.RELEASED)
        released = RosterEvent.objects.create(
            participant=person,
            registration=person.current_registration,
            kind=RosterEvent.Kind.RELEASED,
            occurred_at=event_time(14, 30),
            recorded_by=self.staff,
            reason="未到场",
        )
        absent = RosterEvent.objects.create(
            participant=person,
            registration=person.current_registration,
            kind=RosterEvent.Kind.STAGE_ABSENT,
            occurred_at=event_time(15, 0),
        )
        with patch("events.admission.timezone.now", return_value=event_time(15, 5)):
            with self.assertRaises(OnsiteError):
                self._arrive(person.student_number, name="核验不一致")
            self.assertEqual(self._queue(), [])
            checked = self._arrive(person.student_number)
            self.assertEqual(checked.pk, person.pk)
            self.assertEqual(
                self._admit(checked).admission_mode, Attendance.AdmissionMode.ONSITE_WALK_IN
            )
        self.assertEqual(Participant.objects.count(), 1)
        person.refresh_from_db()
        self.assertEqual(person.current_registration.status, Registration.Status.RELEASED)
        self.assertTrue(person.roster_events.filter(pk=released.pk, reason="未到场").exists())
        self.assertEqual(person.roster_events.get(kind=RosterEvent.Kind.STAGE_ABSENT).pk, absent.pk)

    def test_failed_attendance_rolls_back_seat_and_retry_is_idempotent(self):
        with patch("events.admission.timezone.now", return_value=event_time(14, 0)):
            person = self._arrive("0031")
            with patch.object(Attendance.objects, "create", side_effect=RuntimeError("write failed")):
                with self.assertRaises(RuntimeError):
                    self._admit(person)
            self.assertEqual(available_seats(self.activity.pk).count(), 5)
            self.assertFalse(Attendance.objects.filter(participant=person).exists())
            self.assertEqual([entry.pk for entry, _ in self._queue()], [person.pk])
            first = self._admit(person)
            replay = self._admit(person)
            self.assertEqual(first.pk, replay.pk)
            self.assertEqual(available_seats(self.activity.pk).count(), 4)
        self.assertEqual(Attendance.objects.count(), 1)

    def test_capacity_and_activity_scoped_staff_role(self):
        with patch("events.admission.timezone.now", return_value=event_time(14, 0)):
            with self.assertRaises(PermissionDenied):
                get_arrival_queue(self.activity.pk, staff_id=self.organizer.pk)
            with self.assertRaises(PermissionDenied):
                record_arrival(
                    self.activity.pk, staff_id=self.organizer.pk, student_number="0040", name="无权限"
                )
            for number in range(10, 15):
                self._admit(self._arrive(f"{number:04}"))
            next_person = self._arrive("0020")
            with self.assertRaises(OnsiteError):
                self._admit(next_person)
        self.assertEqual(Attendance.objects.count(), 5)
        self.assertEqual([entry.pk for entry, _ in self._queue()], [next_person.pk])


class OnsiteAdmissionConcurrencyTests(OnsiteAdmissionFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_independent_connections_contend_for_the_last_vacancy(self):
        barrier = Barrier(2)

        def attempt(person):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self._admit(person).participant_id
            except OnsiteError:
                return None
            finally:
                connections.close_all()

        with patch("events.admission.timezone.now", return_value=event_time(14, 0)):
            for number in range(10, 14):
                self._admit(self._arrive(f"{number:04}"))
            first = self._arrive("0014")
            second = self._arrive("0015")
            self.assertEqual(available_seats(self.activity.pk).count(), 1)
            self.assertEqual(Attendance.objects.count(), 4)

            with ThreadPoolExecutor(max_workers=2) as pool:
                admitted = list(pool.map(attempt, [first, second]))

        self.assertEqual(admitted, [first.pk, None])
        self.assertEqual(Attendance.objects.count(), 5)
        self.assertEqual(
            Seat.objects.filter(activity=self.activity, occupant__isnull=False).count(), 5
        )
        self.assertEqual([person.pk for person, _ in self._queue()], [second.pk])
