import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from openpyxl import Workbook

from .checkin import OnsiteError, record_stage_absences_locked, require_activity_role
from .models import Activity, ActivityStaff, Participant, Registration, RosterEvent
from .seats import lock_activity


_INVALID_XML_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


@dataclass(frozen=True)
class AttendanceRow:
    name: str
    student_number: str
    initial_category: str
    admission_mode: str
    checked_in_at: datetime | None
    released_at: datetime | None
    release_reason: str
    stage_absent_at: datetime | None
    final_status: str
    registered: bool

    @property
    def stage_absent(self):
        return self.stage_absent_at is not None


@dataclass(frozen=True)
class AttendanceReport:
    activity: Activity
    rows: tuple[AttendanceRow, ...]
    registered_count: int
    attended_count: int
    absent_count: int


def _report_row(participant):
    registration = participant.current_registration
    attendance = getattr(participant, "attendance", None)
    release = next(
        (event for event in participant.report_history if event.kind == RosterEvent.Kind.RELEASED),
        None,
    )
    stage_absence = next(
        (
            event for event in participant.report_history
            if event.kind == RosterEvent.Kind.STAGE_ABSENT
        ),
        None,
    )
    registered = bool(registration and registration.status != Registration.Status.WITHDRAWN)
    final_status = "未入场"
    if attendance is not None:
        final_status = "出席"
    elif registered and registration.confirmed_at is not None:
        final_status = "缺席"

    return AttendanceRow(
        name=participant.name,
        student_number=participant.student_number,
        initial_category=registration.get_initial_category_display() if registration else "未报名",
        admission_mode=attendance.get_admission_mode_display() if attendance else "未入场",
        checked_in_at=attendance.checked_in_at if attendance else None,
        released_at=release.occurred_at if release else None,
        release_reason=release.reason if release else "",
        stage_absent_at=stage_absence.occurred_at if stage_absence else None,
        final_status=final_status,
        registered=registered,
    )


@transaction.atomic
def get_attendance_report(activity_id, *, staff_id):
    """Return the same final snapshot for the finance page and Excel export."""
    activity = lock_activity(activity_id)
    require_activity_role(activity, staff_id, ActivityStaff.Role.FINANCE)
    now = timezone.now()
    if now < activity.ends_at:
        raise OnsiteError("活动结束后才能查看和导出出席汇总。")

    record_stage_absences_locked(activity, now)
    history = RosterEvent.objects.filter(
        kind__in=(RosterEvent.Kind.RELEASED, RosterEvent.Kind.STAGE_ABSENT)
    ).order_by("-occurred_at", "-pk")
    people = (
        Participant.objects.filter(activity=activity)
        .select_related("current_registration", "attendance")
        .prefetch_related(Prefetch("roster_events", queryset=history, to_attr="report_history"))
        .order_by("student_number", "pk")
    )
    rows = tuple(_report_row(person) for person in people)
    return AttendanceReport(
        activity=activity,
        rows=rows,
        registered_count=sum(row.registered for row in rows),
        attended_count=sum(row.final_status == "出席" for row in rows),
        absent_count=sum(row.final_status == "缺席" for row in rows),
    )


def _write_row(sheet, row, values):
    for column, value in enumerate(values, start=1):
        if isinstance(value, str):
            cell = sheet.cell(row, column, _INVALID_XML_CHARACTERS.sub("", value))
            # Treat user-entered names, IDs and reasons as text, even if they start with '='.
            cell.data_type = "s"
        elif isinstance(value, datetime):
            local_time = timezone.localtime(value, timezone.get_default_timezone())
            cell = sheet.cell(row, column, local_time.replace(tzinfo=None))
            cell.number_format = "yyyy-mm-dd hh:mm:ss"
        else:
            sheet.cell(row, column).value = value


def build_workbook(report):
    """Serialize an authorized finance snapshot as an XLSX file."""
    workbook = Workbook()
    detail = workbook.active
    detail.title = "出席明细"
    _write_row(
        detail,
        1,
        (
            "姓名", "学号", "原报名类别", "最终入场方式", "签到时间", "释放时间",
            "释放理由", "阶段缺席", "阶段缺席时间", "最终出席", "计入有效报名",
        ),
    )
    for index, row in enumerate(report.rows, start=2):
        _write_row(
            detail,
            index,
            (
                row.name, row.student_number, row.initial_category, row.admission_mode,
                row.checked_in_at, row.released_at, row.release_reason,
                "是" if row.stage_absent else "否", row.stage_absent_at, row.final_status,
                "是" if row.registered else "否",
            ),
        )
    detail.freeze_panes = "C2"
    detail.auto_filter.ref = detail.dimensions
    detail.column_dimensions["A"].width = 22
    detail.column_dimensions["B"].width = 20
    for column in ("E", "F", "I"):
        detail.column_dimensions[column].width = 23
    detail.column_dimensions["G"].width = 32

    summary = workbook.create_sheet("活动汇总")
    summary_rows = (
        ("活动", report.activity.title),
        ("有效报名", report.registered_count),
        ("实际出席", report.attended_count),
        ("最终缺席", report.absent_count),
        ("时间显示", str(timezone.get_default_timezone())),
    )
    for index, values in enumerate(summary_rows, start=1):
        _write_row(summary, index, values)
    summary.column_dimensions["A"].width = 18
    summary.column_dimensions["B"].width = 32

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
