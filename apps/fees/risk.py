"""Dues-risk flags: which students may fall behind, with plain reasons (D32).

Worked out on our own server from dues and receipts. No AI service sees student data.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Max

from .models import ZERO, Receipt, StudentDue
from .reports import DuesFilter

HIGH = "high"
WATCH = "watch"


@dataclass
class Flag:
    student_id: int
    roll_number: str
    name: str
    mobile: str
    overdue: Decimal = ZERO
    payable: Decimal = ZERO
    oldest_due: dt.date | None = None
    instalments: set = field(default_factory=set)
    arrears: bool = False
    last_paid: dt.date | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        return HIGH if self.score >= 4 else WATCH


def _score(flag: Flag, today: dt.date) -> None:
    days = (today - flag.oldest_due).days
    flag.score = 1
    flag.reasons.append(f"₹{flag.overdue:,.2f} overdue for {days} day(s)")
    if days > 90:
        flag.score += 2
    elif days > 30:
        flag.score += 1
    if len(flag.instalments) >= 2:
        flag.score += 1
        flag.reasons.append(f"{len(flag.instalments)} instalments missed")
    if flag.arrears:
        flag.score += 2
        flag.reasons.append("still owes from an earlier year")
    if flag.last_paid is None:
        flag.score += 1
        flag.reasons.append("has not paid anything yet")
    elif (today - flag.last_paid).days > 60:
        flag.score += 1
        flag.reasons.append(f"last paid on {flag.last_paid:%d %b %Y}")
    if flag.payable and flag.overdue * 2 > flag.payable:
        flag.score += 1
        flag.reasons.append("more than half of the fees is overdue")


def flags(filters: DuesFilter, today: dt.date) -> list[Flag]:
    """Students with overdue fees, the most at risk first."""
    dues = filters.apply(StudentDue.objects.all()).select_related("student", "academic_year")
    by_student: dict[int, Flag] = {}
    payable: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for due in dues:
        payable[due.student_id] += due.payable
        if due.due_date >= today or due.balance <= 0:
            continue
        student = due.student
        flag = by_student.get(student.pk)
        if flag is None:
            flag = by_student[student.pk] = Flag(
                student.pk, student.roll_number, student.name, student.mobile
            )
        flag.overdue += due.balance
        flag.instalments.add((due.academic_year_id, due.instalment_number))
        flag.oldest_due = min(filter(None, [flag.oldest_due, due.due_date]))
        if not due.academic_year.is_current:
            flag.arrears = True
    last_paid = dict(
        Receipt.objects.filter(student__in=by_student, status=Receipt.Status.VALID)
        .values("student")
        .annotate(last=Max("date"))
        .values_list("student", "last")
    )
    for pk, flag in by_student.items():
        flag.payable = payable[pk]
        flag.last_paid = last_paid.get(pk)
        _score(flag, today)
    return sorted(by_student.values(), key=lambda f: (-f.score, -f.overdue, f.roll_number))
