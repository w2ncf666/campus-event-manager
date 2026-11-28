import re
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from .models import ActivityStaff, Attendance, Invitation, Participant, Registration, RosterEvent, Seat
from .seats import active_holds, available_seats
from .test_invitations import InvitationFixture, event_time


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OnsiteViewTests(InvitationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.checker = self.create_staff("checker", ActivityStaff.Role.CHECK_IN)
        self.finance = self.create_staff("finance", ActivityStaff.Role.FINANCE)

    def create_staff(self, username, role):
        user = get_user_model().objects.create_user(username=username, password="local-test-password")
        ActivityStaff.objects.create(activity=self.activity, user=user, role=role)
        return user

    def url(self, name, *args):
        return reverse(f"onsite:{name}", args=(self.activity.pk, *args))

    def create_formal_roster(self):
        self.activity.capacity = 16
        self.activity.save(update_fields=("capacity",))
        for number in range(3, 17):
            participant = Participant.objects.create(
                activity=self.activity, student_number=f"{number:04}", name=f"模拟正式 {number:02}"
            )
            participant.current_registration = Registration.objects.create(
                activity=self.activity, participant=participant, queue_sequence=number,
                initial_category=Registration.InitialCategory.FORMAL, status=Registration.Status.CONFIRMED,
                request_id=uuid4(), submitted_at=event_time(20, 0, day=26),
                confirmed_at=event_time(20, 0, day=26),
            )
            participant.save(update_fields=("current_registration",))
            Seat.objects.create(activity=self.activity, number=number, occupant=participant)
        return Participant.objects.get(activity=self.activity, student_number="0003")

    def post_arrival(self, person):
        response = self.client.post(self.url("arrival"), {
            "student_number": person.student_number, "name": person.name, "request_id": uuid4(),
        })
        self.assertRedirects(response, self.url("roster"), fetch_redirect_response=False)

    def test_ac07_through_staff_views_and_released_person_export(self):
        person_c = self.create_formal_roster()
        self.client.force_login(self.checker)
        with patch("django.utils.timezone.now", return_value=event_time(11, 50)):
            first = self.issue(self.first_seat)
            second = self.issue(self.second_seat)
            self.assertEqual(active_holds(self.activity.pk, event_time(11, 50)).count(), 2)

        with patch("django.utils.timezone.now", return_value=event_time(13, 29, 59)):
            self.assertEqual(self.respond(first, self.a), "accepted")
            response = self.client.get(self.url("roster"))
            self.assertContains(response, self.a.name)
            self.assertNotContains(response, self.b.name)

        with patch("django.utils.timezone.now", return_value=event_time(13, 30)):
            self.assertEqual(self.respond(second, self.b), "expired")
            self.assertEqual(list(available_seats(self.activity.pk).values_list("pk", flat=True)), [self.second_seat.pk])
            self.client.post(self.url("admit", self.b.pk))
            self.assertFalse(Attendance.objects.filter(participant=self.b).exists())

        with patch("django.utils.timezone.now", return_value=event_time(14, 0)):
            for _ in range(2):
                self.client.post(self.url("sign_in", self.a.pk))
            self.assertEqual(Attendance.objects.get(participant=self.a).seat_id, self.first_seat.pk)
            self.post_arrival(self.b)
            self.assertContains(self.client.get(self.url("roster")), "现场候补")
            for _ in range(2):
                self.client.post(self.url("admit", self.b.pk))
            attendance_b = Attendance.objects.get(participant=self.b)
            self.assertEqual(attendance_b.seat_id, self.second_seat.pk)
            self.assertEqual(attendance_b.admission_mode, Attendance.AdmissionMode.ONSITE_WAITLIST)
            self.assertFalse(available_seats(self.activity.pk).exists())

        with patch("django.utils.timezone.now", return_value=event_time(14, 29, 59)):
            self.client.post(self.url("release", person_c.pk), {"reason": "未到且无留言"})
            self.assertFalse(available_seats(self.activity.pk).exists())
        with patch("django.utils.timezone.now", return_value=event_time(14, 30)):
            for _ in range(2):
                self.client.post(self.url("release", person_c.pk), {"reason": "未到且无留言"})
            self.assertEqual(available_seats(self.activity.pk).count(), 1)
            self.assertEqual(person_c.roster_events.filter(kind=RosterEvent.Kind.RELEASED).count(), 1)
            self.assertContains(self.client.get(self.url("roster")), "释位记录")

        with patch("django.utils.timezone.now", return_value=event_time(15, 1)):
            self.post_arrival(person_c)
            self.client.post(self.url("admit", person_c.pk))
            self.assertEqual(Attendance.objects.get(participant=person_c).admission_mode, Attendance.AdmissionMode.ONSITE_WALK_IN)
            self.assertFalse(available_seats(self.activity.pk).exists())
            self.assertTrue(person_c.roster_events.filter(kind=RosterEvent.Kind.STAGE_ABSENT).exists())

        self.client.force_login(self.finance)
        with patch("django.utils.timezone.now", return_value=event_time(16, 0)):
            self.assertContains(self.client.get(self.url("report")), "未到且无留言")
            excel = self.client.get(self.url("export"))
        self.assertEqual(excel.status_code, 200)
        self.assertIn(".xlsx", excel.headers["Content-Disposition"])
        workbook = load_workbook(BytesIO(excel.content))
        rows = [row for row in workbook["出席明细"].values if row[1] == "0003"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][3], rows[0][6], rows[0][7], rows[0][9]), ("现场临时", "未到且无留言", "是", "出席"))
        self.assertEqual(Invitation.objects.get(pk=second.invitation_id).status, Invitation.Status.EXPIRED)

    def test_checkin_page_masks_student_numbers_in_all_roster_sections(self):
        numbers = ("101234560001", "101234560002", "101234560003")
        people = [
            Participant.objects.create(activity=self.activity, student_number=number, name=name)
            for number, name in zip(numbers, ("正式成员甲", "候补成员乙", "已释位成员丙"))
        ]
        seated, waiting, released = people
        self.first_seat.occupant = seated
        self.first_seat.save(update_fields=("occupant",))
        for person, kind in ((waiting, RosterEvent.Kind.ARRIVED), (released, RosterEvent.Kind.RELEASED)):
            RosterEvent.objects.create(
                participant=person, kind=kind, occurred_at=event_time(14, 30),
                recorded_by=self.checker,
            )
        self.client.force_login(self.checker)
        with patch("django.utils.timezone.now", return_value=event_time(14, 31)):
            response = self.client.get(self.url("roster"))
        for person in people:
            self.assertContains(response, person.name)
            self.assertContains(response, f"••••{person.student_number[-4:]}")
            self.assertNotContains(response, person.student_number)

    def test_replayed_browser_arrival_remains_effective_only_once(self):
        self.client.force_login(self.checker)
        with patch("django.utils.timezone.now", return_value=event_time(14, 10)):
            def form_ids():
                page = self.client.get(self.url("roster"))
                return re.findall(r'name="request_id" value="([a-f0-9-]+)"', page.content.decode())

            arrival_id, = form_ids()
            data = {"name": "现场人员甲", "student_number": "101234560004", "request_id": arrival_id}
            self.client.post(self.url("arrival"), data)
            new_arrival_id, leave_id = form_ids()
            person = Participant.objects.get(student_number=data["student_number"], activity=self.activity)
            self.client.post(self.url("leave", person.pk), {"request_id": leave_id})
            self.client.post(self.url("arrival"), data)
            self.assertNotContains(self.client.get(self.url("roster")), person.name)

            self.client.post(self.url("arrival"), {**data, "request_id": new_arrival_id})
            self.client.post(self.url("leave", person.pk), {"request_id": leave_id})
            self.assertContains(self.client.get(self.url("roster")), person.name)

    def test_login_csrf_and_roles_are_enforced_at_web_entry_points(self):
        client = Client(enforce_csrf_checks=True)
        roster_url = self.url("roster")
        login_url = reverse("onsite:login")
        self.assertRedirects(client.get(roster_url), f"{login_url}?next={roster_url}")
        self.assertContains(client.get(login_url), "工作人员登录")
        login = client.post(login_url, {
            "username": self.checker.username, "password": "local-test-password", "next": roster_url,
        }, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertRedirects(login, roster_url)
        self.assertEqual(client.post(self.url("sign_in", self.a.pk)).status_code, 403)
        self.assertEqual(client.get(self.url("sign_in", self.a.pk)).status_code, 405)
        self.assertEqual(client.get(self.url("export")).status_code, 403)

        client.force_login(self.finance)
        self.assertEqual(client.get(roster_url).status_code, 403)
        with patch("django.utils.timezone.now", return_value=event_time(15, 59, 59)):
            self.assertContains(client.get(self.url("report")), "活动结束后", status_code=409)
