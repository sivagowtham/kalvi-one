"""Placing students in a term and promoting a batch to the next term (D17)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.academics.models import AcademicYear, Semester
from apps.accounts.permissions import has_perm

from .models import Batch, Section, Student, StudentSemester


def next_term(term: Semester) -> Semester | None:
    """The term after ``term``: odd to even in the same year, even to odd in the next year."""
    if term.term == Semester.Term.ODD:
        return Semester.objects.filter(
            academic_year=term.academic_year, term=Semester.Term.EVEN
        ).first()
    year = (
        AcademicYear.objects.filter(start_date__gt=term.academic_year.start_date)
        .order_by("start_date")
        .first()
    )
    if year is None:
        return None
    return Semester.objects.filter(academic_year=year, term=Semester.Term.ODD).first()


def place(student: Student, term: Semester, section: Section, semester_number: int):
    """Put ``student`` in ``section`` for ``term``. Used by enrolment and import."""
    return StudentSemester.objects.create(
        student=student, semester=term, section=section, semester_number=semester_number
    )


@dataclass
class Row:
    current: StudentSemester
    next_number: int | None  # None when the student finished the last semester

    @property
    def student(self) -> Student:
        return self.current.student


@dataclass
class Preview:
    batch: Batch
    from_term: Semester
    to_term: Semester | None
    rows: list[Row] = field(default_factory=list)
    already_promoted: int = 0

    @property
    def promotable(self) -> list[Row]:
        return [row for row in self.rows if row.next_number is not None]

    @property
    def finishing(self) -> list[Row]:
        return [row for row in self.rows if row.next_number is None]


def preview(batch: Batch, from_term: Semester) -> Preview:
    """Who in ``batch`` studied in ``from_term`` and where they would go next."""
    to_term = next_term(from_term)
    result = Preview(batch=batch, from_term=from_term, to_term=to_term)
    total = batch.programme.total_semesters
    current = (
        StudentSemester.objects.filter(
            student__batch=batch,
            semester=from_term,
            status=StudentSemester.Status.STUDYING,
            student__status=Student.Status.STUDYING,
        )
        .select_related("student", "section")
        .order_by("student__roll_number")
    )
    moved = set()
    if to_term is not None:
        moved = set(
            StudentSemester.objects.filter(student__batch=batch, semester=to_term).values_list(
                "student_id", flat=True
            )
        )
    for placement in current:
        if placement.student_id in moved:
            result.already_promoted += 1
            continue
        number = placement.semester_number + 1
        result.rows.append(Row(placement, number if number <= total else None))
    return result


def section_load(rows: list[Row], sections: dict[int, int]) -> dict[Section, int]:
    """How many students each section would get, to warn about capacity."""
    counts = Counter(sections.get(row.current.pk, row.current.section_id) for row in rows)
    return {s: counts[s.pk] for s in Section.objects.filter(pk__in=counts)}


@transaction.atomic
def promote(
    user,
    batch: Batch,
    from_term: Semester,
    *,
    hold_back: set[int] = frozenset(),
    sections: dict[int, int] | None = None,
) -> dict[str, int]:
    """Promote everyone in ``batch`` from ``from_term`` to the next term, in one transaction.

    hold_back: StudentSemester ids to mark detained instead of promoting.
    sections:  StudentSemester id to the Section id for the next term (default: same section).
    Each new row and each status change is saved one by one, so all of it is audited (D8).
    """
    if not has_perm(user, "students.promote_batch", batch):
        raise PermissionDenied
    plan = preview(batch, from_term)
    if plan.to_term is None:
        raise ValidationError("The next term does not exist yet. Add it under Academics first.")
    sections = sections or {}
    batch_sections = {s.pk: s for s in batch.sections.all()}
    counts = {"promoted": 0, "detained": 0, "completed": 0}
    for row in plan.rows:
        placement = row.current
        if placement.pk in hold_back:
            placement.status = StudentSemester.Status.DETAINED
            placement.save()
            counts["detained"] += 1
            continue
        placement.status = StudentSemester.Status.COMPLETED
        placement.save()
        if row.next_number is None:
            counts["completed"] += 1
            continue
        section_id = sections.get(placement.pk, placement.section_id)
        if section_id not in batch_sections:
            raise ValidationError(f"{row.student.roll_number}: that section is not in this batch.")
        place(row.student, plan.to_term, batch_sections[section_id], row.next_number)
        counts["promoted"] += 1
    return counts
