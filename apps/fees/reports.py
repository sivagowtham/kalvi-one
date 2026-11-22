"""Dues and collection reports, on screen and as Excel (D30)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse

from .models import ZERO, Receipt, ReceiptLine, StudentDue

MONEY = DecimalField(max_digits=12, decimal_places=2)


def PAYABLE():
    return ExpressionWrapper(F("amount") - F("waived") - F("govt_share"), output_field=MONEY)


def BALANCE():
    return ExpressionWrapper(
        F("amount") - F("waived") - F("govt_share") - F("paid"), output_field=MONEY
    )


@dataclass
class DuesFilter:
    academic_year: object | None = None
    batch: object | None = None
    head: object | None = None
    overdue_on: dt.date | None = None

    def apply(self, dues):
        if self.academic_year is not None:
            dues = dues.filter(academic_year=self.academic_year)
        if self.batch is not None:
            dues = dues.filter(student__batch=self.batch)
        if self.head is not None:
            dues = dues.filter(head=self.head)
        if self.overdue_on is not None:
            dues = dues.filter(due_date__lt=self.overdue_on)
        return dues


KEYS = ("amount", "waived", "govt_share", "payable", "paid", "balance")


def _sums() -> dict:
    """Sum expressions under t_ names: an annotation named like a field would hide that field
    from the expressions after it."""
    return {
        "t_amount": Sum("amount"),
        "t_waived": Sum("waived"),
        "t_govt_share": Sum("govt_share"),
        "t_payable": Sum(PAYABLE()),
        "t_paid": Sum("paid"),
        "t_balance": Sum(BALANCE()),
    }


def _unpack(row: dict) -> dict:
    return {key: row[f"t_{key}"] or ZERO for key in KEYS}


def _totals(queryset) -> dict:
    return _unpack(queryset.aggregate(**_sums()))


def dues_by_batch(filters: DuesFilter) -> tuple[list[dict], dict]:
    """One row per batch, plus the grand total."""
    dues = filters.apply(StudentDue.objects.all())
    rows = (
        dues.values("student__batch", "student__batch__programme__code", "student__batch__label")
        .annotate(
            students=Count("student", distinct=True),
            owing=Count("student", distinct=True, filter=Q(paid__lt=PAYABLE())),
            **_sums(),
        )
        .order_by("student__batch__programme__code", "student__batch__label")
    )
    return [
        {
            "batch_id": row["student__batch"],
            "batch": f"{row['student__batch__programme__code']} {row['student__batch__label']}",
            "students": row["students"],
            "owing": row["owing"],
            **_unpack(row),
        }
        for row in rows
    ], _totals(dues)


def students_owing(filters: DuesFilter) -> list[dict]:
    """Students with something left to pay, largest balance first."""
    dues = filters.apply(StudentDue.objects.all())
    rows = (
        dues.values("student", "student__roll_number", "student__name", "student__mobile")
        .annotate(**_sums())
        .filter(t_balance__gt=0)
        .order_by("-t_balance", "student__roll_number")
    )
    return [
        {
            "student_id": row["student"],
            "roll_number": row["student__roll_number"],
            "name": row["student__name"],
            "mobile": row["student__mobile"],
            **_unpack(row),
        }
        for row in rows
    ]


def collections(start: dt.date, end: dt.date) -> dict:
    """Valid receipts between two dates: per day and mode, and per fee head."""
    receipts = Receipt.objects.filter(date__gte=start, date__lte=end, status=Receipt.Status.VALID)
    by_day = list(
        receipts.values("date", "mode")
        .annotate(count=Count("pk"), amount=Sum("amount"))
        .order_by("date", "mode")
    )
    lines = ReceiptLine.objects.filter(receipt__in=receipts)
    by_head = list(
        lines.values("head__name", "head__tally_ledger")
        .annotate(amount=Sum("amount"), cgst=Sum("cgst"), sgst=Sum("sgst"))
        .order_by("head__sort_order", "head__name")
    )
    cancelled = Receipt.objects.filter(
        date__gte=start, date__lte=end, status=Receipt.Status.CANCELLED
    ).count()
    total = receipts.aggregate(total=Sum("amount"), count=Count("pk"))
    return {
        "by_day": by_day,
        "by_head": by_head,
        "total": total["total"] or ZERO,
        "count": total["count"],
        "cancelled": cancelled,
    }


def xlsx_response(filename: str, sheets: list[tuple[str, list[str], list[list]]]) -> HttpResponse:
    """An Excel download with one sheet per (title, headers, rows)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    book.remove(book.active)
    for title, headers, rows in sheets:
        sheet = book.create_sheet(title[:31])
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([float(v) if isinstance(v, Decimal) else v for v in row])
        for index, header in enumerate(headers, start=1):
            sheet.column_dimensions[sheet.cell(1, index).column_letter].width = max(
                12, len(header) + 2
            )
    buffer = BytesIO()
    book.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
