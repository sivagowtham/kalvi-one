import datetime as dt

import pytest

from apps.accounts.roles import Role
from apps.tenancy.context import college_context
from apps.timetable.models import (
    Allocation,
    AllocationTeacher,
    BellSchedule,
    LabGroup,
    PeriodSlot,
    TimetableEntry,
)
from tests.students.conftest import build_batches, make_student  # noqa: F401

# A seven-period day with a break after period 2 and lunch after period 4 (D10: fake).
TIMES = [
    ("09:00", "09:50"),
    ("09:50", "10:40"),
    ("11:00", "11:50"),
    ("11:50", "12:40"),
    ("13:30", "14:20"),
    ("14:20", "15:10"),
    ("15:10", "16:00"),
]


def _time(text):
    return dt.time.fromisoformat(text)


def build_timetable(college, prefix=""):
    """Batches and sections, a default bell schedule, a teacher and one allocation."""
    from apps.accounts.models import RoleAssignment, User

    core = build_batches(college, prefix)
    with college_context(college):
        schedule = BellSchedule.objects.create(name="Regular", is_default=True)
        core["schedule"] = schedule
        core["periods"] = {
            n: PeriodSlot.objects.create(
                schedule=schedule, number=n, start_time=_time(a), end_time=_time(b)
            )
            for n, (a, b) in enumerate(TIMES, start=1)
        }
        teacher = User.objects.create_user(
            f"{college.slug}-teacher", "correct-horse-1", college=college, full_name="Fake Teacher"
        )
        RoleAssignment.objects.create(user=teacher, role=Role.FACULTY)
        core["teacher"] = teacher
        allocation = Allocation.objects.create(
            semester=core["odd"], course=core["course"], section=core["be_cse_a"], hours_per_week=4
        )
        AllocationTeacher.objects.create(allocation=allocation, teacher=teacher)
        core["allocation"] = allocation
        core["entry"] = TimetableEntry.objects.create(
            allocation=allocation, day=1, period=core["periods"][1], room="CS-101"
        )
        core["lab_b1"] = LabGroup.objects.create(
            section=core["be_cse_a"], semester=core["odd"], name="B1"
        )
    return core


@pytest.fixture
def core_a(college_a):
    return build_timetable(college_a, "Alpha ")


@pytest.fixture
def core_b(college_b):
    return build_timetable(college_b, "Beta ")
