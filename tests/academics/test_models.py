import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academics.models import AcademicYear, Course, Department, Programme, Semester
from apps.audit.models import AuditEvent
from apps.tenancy.context import CrossCollegeError, NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db

MODELS = [Department, Programme, Course, AcademicYear, Semester]


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


def test_same_codes_allowed_in_different_colleges(core_a, core_b):
    assert Department.all_colleges.filter(code="CSE").count() == 2
    assert AcademicYear.all_colleges.filter(label="2026-27").count() == 2


def test_programme_cannot_use_another_colleges_department(college_a, core_b):
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Programme.objects.create(
            department=core_b["cse"],
            code="X",
            name="X",
            level="ug",
            duration_years=4,
            total_semesters=8,
        )


def test_duplicate_department_code_in_one_college(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        Department.objects.create(code="CSE", name="Again")


def test_only_one_current_academic_year_and_semester(college_a, core_a):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            AcademicYear.objects.create(
                label="2027-28",
                start_date=dt.date(2027, 6, 1),
                end_date=dt.date(2028, 5, 31),
                is_current=True,
            )
        with transaction.atomic(), pytest.raises(IntegrityError):
            Semester.objects.create(
                academic_year=core_a["year"],
                term="even",
                start_date=dt.date(2026, 12, 1),
                end_date=dt.date(2027, 4, 30),
                is_current=True,
            )
        Semester.objects.create(
            academic_year=core_a["year"],
            term="even",
            start_date=dt.date(2026, 12, 1),
            end_date=dt.date(2027, 4, 30),
        )
        with transaction.atomic(), pytest.raises(IntegrityError):
            Semester.objects.create(
                academic_year=core_a["year"],
                term="even",
                start_date=dt.date(2026, 12, 1),
                end_date=dt.date(2027, 4, 30),
            )


def test_dates_must_run_forwards(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        AcademicYear.objects.create(
            label="2030-31", start_date=dt.date(2031, 5, 31), end_date=dt.date(2030, 6, 1)
        )


def test_term_must_fall_inside_its_year(college_a, core_a):
    with college_context(college_a):
        term = Semester(
            academic_year=core_a["year"],
            term="even",
            start_date=dt.date(2027, 1, 1),
            end_date=dt.date(2027, 7, 1),
        )
        with pytest.raises(ValidationError):
            term.clean()


def test_course_semester_must_exist_in_programme(college_a, core_a):
    with college_context(college_a):
        course = Course(
            programme=core_a["be_cse"],
            semester_number=9,
            code="CS9",
            title="Too late",
            credits=Decimal("3"),
            course_type="theory",
        )
        with pytest.raises(ValidationError):
            course.clean()
        with pytest.raises(ValidationError):
            course.save()


def test_negative_credits_are_refused(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        Course.objects.create(
            programme=core_a["be_cse"],
            semester_number=1,
            code="BAD",
            title="Bad",
            credits=Decimal("-1"),
            course_type="theory",
        )


def test_programme_ranges_are_enforced(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        Programme.objects.create(
            department=core_a["cse"],
            code="BAD",
            name="Bad",
            level="ug",
            duration_years=4,
            total_semesters=20,
        )


def test_odd_and_even_terms_map_to_semester_numbers(core_a):
    odd = core_a["odd"]
    assert odd.semester_numbers(8) == [1, 3, 5, 7]
    odd.term = Semester.Term.EVEN
    assert odd.semester_numbers(8) == [2, 4, 6, 8]


def test_academic_changes_are_audited(college_a, core_a):
    with college_context(college_a):
        dept = core_a["cse"]
        dept.name = "Computer Science and Engineering"
        dept.save()
        event = AuditEvent.objects.filter(action="update", object_id=str(dept.pk)).get()
    assert event.changes["name"] == ["Alpha Computer Science", "Computer Science and Engineering"]


def test_string_forms(core_a):
    assert str(core_a["cse"]) == "CSE - Alpha Computer Science"
    assert str(core_a["be_cse"]) == "Alpha B.E. CSE"
    assert str(core_a["course"]) == "CS3301 Alpha Data Structures"
    assert str(core_a["year"]) == "2026-27"
    assert str(core_a["odd"]) == "2026-27 Odd term"
    assert core_a["course"].scope_department_id == core_a["cse"].pk
