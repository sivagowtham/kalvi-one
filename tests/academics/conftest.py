import datetime as dt
from decimal import Decimal

import pytest

from apps.academics.models import AcademicYear, Course, Department, Programme, Semester
from apps.tenancy.context import college_context


def build_core(college, prefix=""):
    """One small academic structure inside ``college``."""
    with college_context(college):
        cse = Department.objects.create(code="CSE", name=f"{prefix}Computer Science")
        ece = Department.objects.create(code="ECE", name=f"{prefix}Electronics")
        be_cse = Programme.objects.create(
            department=cse,
            code="BE-CSE",
            name=f"{prefix}B.E. CSE",
            level="ug",
            duration_years=4,
            total_semesters=8,
            regulation="R2021",
        )
        be_ece = Programme.objects.create(
            department=ece,
            code="BE-ECE",
            name=f"{prefix}B.E. ECE",
            level="ug",
            duration_years=4,
            total_semesters=8,
            regulation="R2021",
        )
        course = Course.objects.create(
            programme=be_cse,
            semester_number=3,
            code="CS3301",
            title=f"{prefix}Data Structures",
            credits=Decimal("3.0"),
            course_type="theory",
        )
        year = AcademicYear.objects.create(
            label="2026-27",
            start_date=dt.date(2026, 6, 1),
            end_date=dt.date(2027, 5, 31),
            is_current=True,
        )
        odd = Semester.objects.create(
            academic_year=year,
            term="odd",
            start_date=dt.date(2026, 7, 1),
            end_date=dt.date(2026, 11, 30),
            is_current=True,
        )
    return {
        "cse": cse,
        "ece": ece,
        "be_cse": be_cse,
        "be_ece": be_ece,
        "course": course,
        "year": year,
        "odd": odd,
    }


@pytest.fixture
def core_a(college_a):
    return build_core(college_a, "Alpha ")


@pytest.fixture
def core_b(college_b):
    return build_core(college_b, "Beta ")
