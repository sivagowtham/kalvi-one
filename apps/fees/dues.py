"""Raising student dues from fee structures and applying concessions to them (D28)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.students.models import Student

from .models import ZERO, Concession, FeeStructure, StudentDue

PAISE = Decimal("0.01")


def structure_for(student, academic_year) -> FeeStructure | None:
    """The most specific active structure that fits the student's quota and residence.

    A structure for the student's quota beats one only for their residence, which beats a
    structure for everyone.
    """
    candidates = FeeStructure.objects.filter(
        batch_id=student.batch_id,
        academic_year=academic_year,
        is_active=True,
        quota__in=["", student.quota],
        residence__in=["", student.residence],
    )
    return max(candidates, key=lambda s: (bool(s.quota), bool(s.residence)), default=None)


@dataclass
class RaiseResult:
    created: int = 0
    students: int = 0
    skipped: list[str] = field(default_factory=list)


def raise_dues(batch, academic_year) -> RaiseResult:
    """Create the dues of every studying student of ``batch`` for ``academic_year``.

    Safe to run again: dues that already exist are left as they are, so a student who joins
    late can be picked up by running it once more.
    """
    result = RaiseResult()
    students = Student.objects.filter(batch=batch, status=Student.Status.STUDYING)
    with transaction.atomic():
        for student in students.order_by("roll_number"):
            structure = structure_for(student, academic_year)
            if structure is None:
                result.skipped.append(f"{student.roll_number}: no fee structure fits")
                continue
            instalments = {i.number: i for i in structure.instalments.all()}
            created = 0
            for line in structure.lines.select_related("head"):
                instalment = instalments[line.instalment_number]
                _, made = StudentDue.objects.get_or_create(
                    student=student,
                    academic_year=academic_year,
                    instalment_number=line.instalment_number,
                    head=line.head,
                    defaults={
                        "structure": structure,
                        "instalment_label": instalment.label,
                        "due_date": instalment.due_date,
                        "amount": line.amount,
                    },
                )
                created += made
            if created:
                result.created += created
                result.students += 1
                apply_concessions(student, academic_year)
    return result


def _percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    return (amount * percent / 100).quantize(PAISE, rounding=ROUND_HALF_UP)


def apply_concessions(student, academic_year) -> list[str]:
    """Work out ``waived`` and ``govt_share`` on the student's dues from approved concessions.

    Percentages are applied first, then fixed amounts, earliest instalment first. A due is
    never reduced below what has already been paid on it; any concession that no longer fits
    is returned as a warning, because it needs a refund or an adjustment by hand.
    """
    with transaction.atomic():
        dues = list(
            StudentDue.objects.select_for_update()
            .filter(student=student, academic_year=academic_year)
            .order_by("due_date", "instalment_number", "head__sort_order", "pk")
        )
        concessions = Concession.objects.filter(
            student=student, academic_year=academic_year, status=Concession.Status.APPROVED
        )
        room = {due.pk: due.amount - due.paid for due in dues}
        share = defaultdict(lambda: {"college": ZERO, "government": ZERO})
        warnings = []

        def give(due, value, funder) -> Decimal:
            taken = min(value, room[due.pk])
            room[due.pk] -= taken
            share[due.pk][funder] += taken
            return value - taken

        percentages = [c for c in concessions if c.percent is not None]
        amounts = [c for c in concessions if c.amount is not None]
        for concession in sorted(percentages, key=lambda c: c.pk):
            for due in dues:
                if concession.head_id in (None, due.head_id):
                    left = give(
                        due, _percent_of(due.amount, concession.percent), concession.funded_by
                    )
                    if left:
                        warnings.append(f"{concession}: ₹{left} could not be applied")
        for concession in sorted(amounts, key=lambda c: c.pk):
            left = concession.amount
            for due in dues:
                if due.head_id == concession.head_id and left:
                    left = give(due, left, concession.funded_by)
            if left:
                warnings.append(f"{concession}: ₹{left} could not be applied")

        for due in dues:
            waived, govt = share[due.pk]["college"], share[due.pk]["government"]
            if (due.waived, due.govt_share) != (waived, govt):
                due.waived, due.govt_share = waived, govt
                due.save(update_fields=["waived", "govt_share"])
    return warnings


def _decide(concession: Concession, user, status: str, allowed_from: str) -> list[str]:
    if concession.status != allowed_from:
        raise ValidationError(
            f"This concession is {concession.get_status_display().lower()}, so it cannot be "
            f"changed to {Concession.Status(status).label.lower()}."
        )
    with transaction.atomic():
        concession.status = status
        concession.decided_by = user
        concession.decided_at = timezone.now()
        concession.save()
        return apply_concessions(concession.student, concession.academic_year)


def approve(concession, user) -> list[str]:
    return _decide(concession, user, Concession.Status.APPROVED, Concession.Status.PENDING)


def reject(concession, user) -> list[str]:
    return _decide(concession, user, Concession.Status.REJECTED, Concession.Status.PENDING)


def withdraw(concession, user) -> list[str]:
    return _decide(concession, user, Concession.Status.WITHDRAWN, Concession.Status.APPROVED)
