"""Who is in a class: the one place other modules ask for an allocation's students (D36)."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.students.models import Student

from .models import Allocation


def roster(allocation: Allocation) -> QuerySet[Student]:
    """The students of a class, by roll number.

    An elective's own roster when it has one; otherwise the lab group's members; otherwise
    the students placed in the section for the allocation's term. Only studying students count.
    """
    if allocation.roster.exists():
        students = Student.objects.filter(electives__allocation=allocation)
    elif allocation.lab_group_id:
        students = Student.objects.filter(lab_groups__group_id=allocation.lab_group_id)
    else:
        students = Student.objects.filter(
            semesters__section_id=allocation.section_id,
            semesters__semester_id=allocation.semester_id,
        )
    return students.filter(status=Student.Status.STUDYING).distinct().order_by("roll_number")
