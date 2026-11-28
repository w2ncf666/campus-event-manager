from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from openpyxl import load_workbook

from .attendance_report import build_workbook, get_attendance_report
from .checkin import OnsiteError
from .models import Activity, ActivityStaff, Attendance, Participant, Registration, RosterEvent, Seat
from .test_invitations import event_time


class AttendanceReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.activity = cls.make_activity("羽毛球")
        other_activity = cls.make_activity("另一场活动")
        user_model = get_user_model()
        cls.finance = user_model.objects.create_user(username="finance")
        cls.check_in_staff = user_model.objects.create_user(username="check-in")
        cls.other_finance = user_model.objects.create_user(username="other-finance")
        ActivityStaff.objects.bulk_create(
            [
                ActivityStaff(activity=cls.activity, user=cls.finance, role=ActivityStaff.Role.FINANCE),
                ActivityStaff(
                    activity=cls.activity, user=cls.check_in_staff, role=ActivityStaff.Role.CHECK_IN
                ),
                ActivityStaff(
                    activity=other_activity, user=cls.other_finance, role=ActivityStaff.Role.FINANCE
                ),
            ]
        )
        Participant.objects.create(activity=other_activity, name="别场人员", student_number="0001")

    @staticmethod
    def make_activity(title):
        return Activity.objects.create(
            title=title,
            capacity=16,
            registration_closes_at=event_time(22, 0, day=26),
            invitation_stops_at=event_time(12, 0),
            latest_confirmation_at=event_time(13, 30),
            starts_at=event_time(14, 0),
            release_starts_at=event_time(14, 30),
            absence_at=event_time(15, 0),
            ends_at=event_time(16, 0),
        )

    def make_person(self, number, name, status=None, *, confirmed=False):
        person = Participant.objects.create(
            activity=self.activity, name=name, student_number=f"{number:04d}"
        )
        if status is not None:
            self.add_registration(person, number, status, confirmed=confirmed)
        return person

    def add_registration(self, person, queue_sequence, status, *, confirmed=False):
        signup_time = event_time(21, 0, day=26)
        registration = Registration.objects.create(
            activity=self.activity,
            participant=person,
            queue_sequence=queue_sequence,
            initial_category=(
                Registration.InitialCategory.FORMAL
                if confirmed else Registration.InitialCategory.WAITLIST
            ),
            status=status,
            request_id=uuid4(),
            submitted_at=signup_time,
            confirmed_at=signup_time if confirmed else None,
            withdrawn_at=(
                signup_time + timedelta(minutes=5)
                if status == Registration.Status.WITHDRAWN else None
            ),
        )
        person.current_registration = registration
        person.save(update_fields=("current_registration",))
        return registration

    def add_attendance(self, person, number, admission_mode, checked_in_at):
        seat = Seat.objects.create(activity=self.activity, number=number, occupant=person)
        Attendance.objects.create(
            participant=person,
            seat=seat,
            admission_mode=admission_mode,
            checked_in_at=checked_in_at,
            recorded_by=self.check_in_staff,
        )

    def report(self):
        with patch("events.attendance_report.timezone.now", return_value=self.activity.ends_at):
            return get_attendance_report(self.activity.pk, staff_id=self.finance.pk)

    def test_report_requires_this_activity_finance_and_includes_end_boundary(self):
        with patch(
            "events.attendance_report.timezone.now",
            return_value=self.activity.ends_at - timedelta(seconds=1),
        ):
            with self.assertRaises(OnsiteError):
                get_attendance_report(self.activity.pk, staff_id=self.finance.pk)

        with patch("events.attendance_report.timezone.now", return_value=self.activity.ends_at):
            for user in (self.check_in_staff, self.other_finance):
                with self.subTest(role=user.username), self.assertRaises(PermissionDenied):
                    get_attendance_report(self.activity.pk, staff_id=user.pk)
        self.assertFalse(RosterEvent.objects.exists())
        self.assertEqual(self.report().rows, ())

    def test_summary_counts_latest_registrations_and_distinguishes_final_absence(self):
        confirmed = Registration.Status.CONFIRMED
        walk_in_mode = Attendance.AdmissionMode.ONSITE_WALK_IN
        a = self.make_person(1, "A", confirmed, confirmed=True)
        self.make_person(2, "B", Registration.Status.WAITLISTED)
        self.make_person(3, "C", Registration.Status.WITHDRAWN, confirmed=True)
        d = self.make_person(4, "D", Registration.Status.RELEASED, confirmed=True)
        self.make_person(5, "E")
        f = self.make_person(6, "F", confirmed, confirmed=True)
        self.add_attendance(a, 1, Attendance.AdmissionMode.ONLINE, event_time(14, 0))
        self.add_attendance(d, 2, walk_in_mode, event_time(15, 20))
        Registration.objects.filter(pk=f.current_registration_id).update(
            late_reported_at=event_time(14, 28), late_report_reason="晚点到"
        )

        report = self.report()
        self.assertEqual((report.registered_count, report.attended_count, report.absent_count), (4, 2, 1))
        self.assertEqual(len(report.rows), 6)
        rows = {row.name: row for row in report.rows}
        self.assertEqual(rows["F"].final_status, "缺席")
        self.assertFalse(rows["F"].stage_absent)
        self.assertTrue(rows["D"].stage_absent)
        self.assertEqual(rows["D"].final_status, "出席")
        self.assertEqual([rows[label].final_status for label in "BCE"], ["未入场"] * 3)

    def test_old_withdrawn_formal_round_does_not_make_new_waitlist_round_absent(self):
        person = self.make_person(1, "重报者", Registration.Status.WITHDRAWN, confirmed=True)
        self.add_registration(person, 2, Registration.Status.WAITLISTED)

        report = self.report()
        self.assertEqual((report.registered_count, report.attended_count, report.absent_count), (1, 0, 0))
        self.assertEqual(report.rows[0].initial_category, "候补")
        self.assertEqual(report.rows[0].final_status, "未入场")
        self.assertFalse(report.rows[0].stage_absent)

    def test_workbook_preserves_history_leading_zero_and_literal_text(self):
        formula_like_name = '=HYPERLINK("https://example.invalid","x")'
        person = self.make_person(1, formula_like_name, Registration.Status.RELEASED, confirmed=True)
        self.add_attendance(person, 1, Attendance.AdmissionMode.ONSITE_WALK_IN, event_time(15, 20))
        RosterEvent.objects.create(
            participant=person,
            registration=person.current_registration,
            kind=RosterEvent.Kind.RELEASED,
            occurred_at=event_time(14, 30),
            recorded_by=self.check_in_staff,
            reason="+核验后释位\uffff",
        )

        report = self.report()
        workbook = load_workbook(BytesIO(build_workbook(report)))
        self.addCleanup(workbook.close)
        sheet = workbook["出席明细"]
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual((sheet["A2"].value, sheet["A2"].data_type), (formula_like_name, "s"))
        self.assertEqual((sheet["B2"].value, sheet["B2"].data_type), ("0001", "s"))
        self.assertEqual(sheet["C2"].value, "正式")
        self.assertEqual(sheet["D2"].value, "现场临时")
        self.assertEqual(sheet["E2"].value, datetime(2026, 11, 28, 15, 20))
        self.assertEqual(sheet["F2"].value, datetime(2026, 11, 28, 14, 30))
        self.assertEqual((sheet["G2"].value, sheet["G2"].data_type), ("+核验后释位", "s"))
        self.assertEqual(sheet["H2"].value, "是")
        self.assertEqual(sheet["I2"].value, datetime(2026, 11, 28, 15, 0))
        self.assertEqual(sheet["J2"].value, "出席")
        self.assertEqual([workbook["活动汇总"][f"B{row}"].value for row in (2, 3, 4)], [1, 1, 0])
        self.assertEqual(self.report().rows[0], report.rows[0])
        self.assertEqual(
            RosterEvent.objects.filter(participant=person, kind=RosterEvent.Kind.STAGE_ABSENT).count(),
            1,
        )
