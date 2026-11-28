"""Bell schedules, allocations, lab groups and clash checks (D4, D12, D35, D36)."""

import datetime as dt

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academics.models import Course
from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.students.models import Section
from apps.tenancy.context import CrossCollegeError, NoCollegeSelected, college_context
from apps.timetable.models import (
    Allocation,
    AllocationStudent,
    AllocationTeacher,
    BellSchedule,
    CalendarDay,
    LabGroup,
    LabGroupMember,
    PeriodSlot,
    ScheduleProgramme,
    TimetableEntry,
    schedule_for,
)

pytestmark = pytest.mark.django_db

MODELS = [
    BellSchedule,
    PeriodSlot,
    LabGroup,
    Allocation,
    AllocationTeacher,
    TimetableEntry,
]


@pytest.mark.parametrize("model", MODELS)
def test_each_model_is_isolated_per_college(model, college_a, college_b, core_a, core_b):
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids
    assert a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def _extra_rows(core, make_student, roll):
    student = make_student(core, roll)
    with college_context(core["odd"].college):
        CalendarDay.objects.create(date=dt.date(2026, 12, 7), is_working=True, day=1)
        shift = BellSchedule.objects.create(name="Shift II")
        ScheduleProgramme.objects.create(schedule=shift, programme=core["be_ece"])
        LabGroupMember.objects.create(group=core["lab_b1"], student=student)
        AllocationStudent.objects.create(allocation=core["allocation"], student=student)


@pytest.mark.parametrize(
    "model", [CalendarDay, ScheduleProgramme, LabGroupMember, AllocationStudent]
)
def test_other_models_are_isolated_per_college(
    model, college_a, college_b, core_a, core_b, make_student
):
    _extra_rows(core_a, make_student, "26CSE001")
    _extra_rows(core_b, make_student, "26CSE001")
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_an_allocation_cannot_use_another_colleges_course(college_a, core_a, core_b):
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Allocation.objects.create(
            semester=core_a["odd"], course=core_b["course"], section=core_a["be_cse_a"]
        )


def test_periods_must_not_overlap_and_must_end_after_they_start(college_a, core_a):
    with college_context(college_a):
        overlapping = PeriodSlot(
            schedule=core_a["schedule"],
            number=8,
            start_time=dt.time(15, 30),
            end_time=dt.time(16, 20),
        )
        with pytest.raises(ValidationError, match="overlaps period 7"):
            overlapping.full_clean()
        with transaction.atomic(), pytest.raises(IntegrityError):
            PeriodSlot.objects.create(
                schedule=core_a["schedule"],
                number=9,
                start_time=dt.time(17, 0),
                end_time=dt.time(16, 0),
            )


def test_one_default_schedule_and_programmes_can_follow_another(college_a, core_a):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            BellSchedule.objects.create(name="Second", is_default=True)
        shift = BellSchedule.objects.create(name="Shift II")
        assert schedule_for(core_a["be_cse"]) == core_a["schedule"]
        ScheduleProgramme.objects.create(schedule=shift, programme=core_a["be_ece"])
        assert schedule_for(core_a["be_ece"]) == shift
        assert schedule_for(core_a["be_cse"]) == core_a["schedule"]


def test_allocation_course_must_match_the_section(college_a, core_a):
    with college_context(college_a):
        wrong = Allocation(
            semester=core_a["odd"], course=core_a["course"], section=core_a["be_ece_a"]
        )
        with pytest.raises(ValidationError) as error:
            wrong.full_clean()
        assert "course" in error.value.message_dict
        other_lab = LabGroup.objects.create(
            section=core_a["be_cse_b"], semester=core_a["odd"], name="B1"
        )
        mismatched = Allocation(
            semester=core_a["odd"],
            course=core_a["course"],
            section=core_a["be_cse_a"],
            lab_group=other_lab,
        )
        with pytest.raises(ValidationError) as error:
            mismatched.full_clean()
        assert "lab_group" in error.value.message_dict


def test_one_allocation_per_course_section_and_group(college_a, core_a):
    with college_context(college_a), transaction.atomic(), pytest.raises(IntegrityError):
        Allocation.objects.create(
            semester=core_a["odd"], course=core_a["course"], section=core_a["be_cse_a"]
        )


def test_a_student_is_in_one_lab_group_of_a_section(college_a, core_a, make_student):
    student = make_student(core_a, "26CSE001")
    with college_context(college_a):
        LabGroupMember.objects.create(group=core_a["lab_b1"], student=student)
        b2 = LabGroup.objects.create(section=core_a["be_cse_a"], semester=core_a["odd"], name="B2")
        with pytest.raises(ValidationError, match="already in B1"):
            LabGroupMember(group=b2, student=student).full_clean()
        ece = make_student(core_a, "26ECE001", batch_key="be_ece_batch")
        with pytest.raises(ValidationError, match="not in this section's batch"):
            LabGroupMember(group=b2, student=ece).full_clean()


def _allocation(core, section_key="be_cse_a", lab_group=None, course=None):
    return Allocation.objects.create(
        semester=core["odd"],
        course=course or core["course"],
        section=core[section_key],
        lab_group=lab_group,
    )


def _second_course(core):
    return Course.objects.create(
        programme=core["be_cse"],
        semester_number=3,
        code="CS3361",
        title="Data Structures Lab",
        credits=2,
        course_type="lab",
    )


class TestClashes:
    def test_a_section_cannot_have_two_classes_at_once(self, college_a, core_a):
        with college_context(college_a):
            other = _allocation(core_a, course=_second_course(core_a))
            with pytest.raises(ValidationError, match="The section already has CS3301"):
                TimetableEntry.objects.create(allocation=other, day=1, period=core_a["periods"][1])
            TimetableEntry.objects.create(allocation=other, day=1, period=core_a["periods"][2])

    def test_two_lab_groups_can_meet_at_once_but_not_with_the_whole_section(
        self, college_a, core_a
    ):
        with college_context(college_a):
            lab = _second_course(core_a)
            b2 = LabGroup.objects.create(
                section=core_a["be_cse_a"], semester=core_a["odd"], name="B2"
            )
            b1_lab = _allocation(core_a, lab_group=core_a["lab_b1"], course=lab)
            b2_lab = _allocation(core_a, lab_group=b2, course=lab)
            period = core_a["periods"][5]
            TimetableEntry.objects.create(allocation=b1_lab, day=2, period=period)
            TimetableEntry.objects.create(allocation=b2_lab, day=2, period=period)
            with pytest.raises(ValidationError, match="The section already has"):
                TimetableEntry.objects.create(allocation=core_a["allocation"], day=2, period=period)

    def test_a_teacher_cannot_be_in_two_sections_at_once(self, college_a, core_a):
        with college_context(college_a):
            other = _allocation(core_a, section_key="be_cse_b")
            AllocationTeacher.objects.create(allocation=other, teacher=core_a["teacher"])
            with pytest.raises(ValidationError, match="A teacher of this class already has"):
                TimetableEntry.objects.create(allocation=other, day=1, period=core_a["periods"][1])

    def test_adding_a_busy_teacher_to_a_class_is_refused(self, college_a, core_a):
        with college_context(college_a):
            other = _allocation(core_a, section_key="be_cse_b")
            TimetableEntry.objects.create(allocation=other, day=1, period=core_a["periods"][1])
            with pytest.raises(ValidationError, match="already has CS3301"):
                AllocationTeacher.objects.create(allocation=other, teacher=core_a["teacher"])
            assert not other.teachers.exists()

    def test_a_room_cannot_be_booked_twice(self, college_a, core_a):
        with college_context(college_a):
            other = _allocation(core_a, section_key="be_cse_b")
            with pytest.raises(ValidationError, match="Room cs-101 is already taken"):
                TimetableEntry.objects.create(
                    allocation=other, day=1, period=core_a["periods"][1], room="cs-101"
                )

    def test_times_are_compared_across_bell_schedules(self, college_a, core_a):
        with college_context(college_a):
            shift = BellSchedule.objects.create(name="Shift II")
            ScheduleProgramme.objects.create(schedule=shift, programme=core_a["be_ece"])
            overlapping = PeriodSlot.objects.create(
                schedule=shift, number=1, start_time=dt.time(9, 30), end_time=dt.time(10, 20)
            )
            ece_course = Course.objects.create(
                programme=core_a["be_ece"],
                semester_number=3,
                code="EC3301",
                title="Signals",
                credits=3,
                course_type="theory",
            )
            ece = _allocation(core_a, section_key="be_ece_a", course=ece_course)
            AllocationTeacher.objects.create(allocation=ece, teacher=core_a["teacher"])
            with pytest.raises(ValidationError, match="A teacher of this class"):
                TimetableEntry.objects.create(allocation=ece, day=1, period=overlapping)
            with pytest.raises(ValidationError, match="follows the Shift II bell schedule"):
                TimetableEntry.objects.create(allocation=ece, day=3, period=core_a["periods"][1])

    def test_day_must_be_one_of_the_colleges_days(self, college_a, core_a):
        with college_context(college_a), pytest.raises(ValidationError) as error:
            TimetableEntry.objects.create(
                allocation=core_a["allocation"], day=7, period=core_a["periods"][3]
            )
        assert "day" in error.value.message_dict

    def test_day_orders_use_the_cycle_length(self, college_a, core_a):
        college_a.config = {"timetable": {"cycle": "day_order", "day_order_count": 5}}
        college_a.save()
        with college_context(college_a):
            entry = TimetableEntry.objects.create(
                allocation=core_a["allocation"], day=5, period=core_a["periods"][3]
            )
            assert entry.day_label == "Day 5"
            with pytest.raises(ValidationError):
                TimetableEntry.objects.create(
                    allocation=core_a["allocation"], day=6, period=core_a["periods"][3]
                )


def test_a_teacher_from_another_college_is_refused(college_a, core_a, core_b):
    outsider = User.objects.get(pk=core_b["teacher"].pk)
    with college_context(college_a):
        other = _allocation(core_a, section_key="be_cse_b")
        with pytest.raises(ValidationError, match="active staff member of this college"):
            AllocationTeacher.objects.create(allocation=other, teacher=outsider)


def test_changes_are_audited(college_a, core_a):
    with college_context(college_a):
        entry = core_a["entry"]
        entry.room = "CS-102"
        entry.save()
        kind = ContentType.objects.get_for_model(TimetableEntry)
        assert AuditEvent.objects.filter(content_type=kind, object_id=str(entry.pk)).count() >= 2


def test_sections_with_classes_are_protected(college_a, core_a):
    from django.db.models import ProtectedError

    with college_context(college_a), pytest.raises(ProtectedError):
        Section.objects.get(pk=core_a["be_cse_a"].pk).delete()
