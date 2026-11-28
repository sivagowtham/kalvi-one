"""Who is in a class (D36)."""

import pytest

from apps.students.models import StudentSemester
from apps.tenancy.context import college_context
from apps.timetable.models import Allocation, AllocationStudent, LabGroupMember
from apps.timetable.rosters import roster

pytestmark = pytest.mark.django_db


@pytest.fixture
def students(college_a, core_a, make_student):
    made = [make_student(core_a, f"26CSE00{n}") for n in range(1, 5)]
    with college_context(college_a):
        for student in made[:3]:
            StudentSemester.objects.create(
                student=student,
                semester=core_a["odd"],
                semester_number=3,
                section=core_a["be_cse_a"],
            )
        StudentSemester.objects.create(
            student=made[3], semester=core_a["odd"], semester_number=3, section=core_a["be_cse_b"]
        )
    return made


def rolls(queryset):
    return [s.roll_number for s in queryset]


def test_a_class_is_its_section_for_the_term(college_a, core_a, students):
    with college_context(college_a):
        assert rolls(roster(core_a["allocation"])) == ["26CSE001", "26CSE002", "26CSE003"]


def test_a_lab_group_class_is_its_members(college_a, core_a, students):
    with college_context(college_a):
        LabGroupMember.objects.create(group=core_a["lab_b1"], student=students[1])
        lab = Allocation.objects.create(
            semester=core_a["odd"],
            course=core_a["course"],
            section=core_a["be_cse_a"],
            lab_group=core_a["lab_b1"],
        )
        assert rolls(roster(lab)) == ["26CSE002"]


def test_an_elective_roster_wins_and_only_studying_students_count(college_a, core_a, students):
    with college_context(college_a):
        allocation = core_a["allocation"]
        AllocationStudent.objects.create(allocation=allocation, student=students[0])
        AllocationStudent.objects.create(allocation=allocation, student=students[3])
        assert rolls(roster(allocation)) == ["26CSE001", "26CSE004"]
        students[3].status = "discontinued"
        students[3].save()
        assert rolls(roster(allocation)) == ["26CSE001"]
