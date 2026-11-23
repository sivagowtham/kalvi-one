"""Taking a payment against a student's dues, and cancelling a receipt (D29)."""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.students.numbering import next_number_for_pattern

from . import config
from .models import ZERO, PaymentAccount, PaymentMode, Receipt, ReceiptLine, StudentDue

PAISE = Decimal("0.01")


def financial_year(college, day: dt.date) -> str:
    """The Indian financial year of ``day``, e.g. 2026-27 for any day from April 2026."""
    start_month = config.setting(college, "financial_year_start_month")
    start = day.year if day.month >= start_month else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def gst_split(amount: Decimal, rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """(taxable value, CGST, SGST) for a GST-inclusive amount. Fees inside a state."""
    if not rate:
        return amount, ZERO, ZERO
    taxable = (amount * 100 / (100 + rate)).quantize(PAISE, rounding=ROUND_HALF_UP)
    tax = amount - taxable
    cgst = (tax / 2).quantize(PAISE, rounding=ROUND_HALF_UP)
    return taxable, cgst, tax - cgst


def open_dues(student):
    """The student's dues with something left to pay, oldest first."""
    dues = StudentDue.objects.filter(student=student).select_related("head")
    dues = dues.order_by("due_date", "instalment_number", "head__sort_order", "pk")
    return [due for due in dues if due.balance > 0]


def check_payment(mode: str, account: PaymentAccount, reference: str) -> None:
    if mode not in PaymentMode.values:
        raise ValidationError({"mode": "Choose how the money was paid."})
    if not account.is_active:
        raise ValidationError({"account": f"{account} is no longer in use."})
    wanted = PaymentAccount.Kind.CASH if mode == PaymentMode.CASH else PaymentAccount.Kind.BANK
    if account.kind != wanted:
        raise ValidationError(
            {"account": f"{PaymentMode(mode).label} goes to a {wanted.label.lower()} account."}
        )
    if mode != PaymentMode.CASH and not reference.strip():
        raise ValidationError(
            {"reference": f"Enter the {PaymentMode(mode).label} reference number."}
        )


def collect(
    student, amount: Decimal, *, mode: str, account, reference: str = "", notes: str = "", user
) -> Receipt:
    """Take ``amount`` from ``student``, settling the oldest dues first.

    Refuses more than the student owes: advance payments and refunds are not in this phase.
    """
    amount = Decimal(amount).quantize(PAISE)
    if amount <= 0:
        raise ValidationError({"amount": "Enter an amount above zero."})
    check_payment(mode, account, reference)
    with transaction.atomic():
        # Lock the student's dues so two counters cannot take the same balance twice.
        list(StudentDue.objects.select_for_update().filter(student=student))
        dues = open_dues(student)
        owed = sum((due.balance for due in dues), ZERO)
        if amount > owed:
            raise ValidationError(
                {"amount": f"{student.roll_number} owes ₹{owed:,.2f}; this is more than that."}
            )
        college = student.college
        today = timezone.localdate()
        year = financial_year(college, today)
        number = next_number_for_pattern(
            config.setting(college, "receipt_number_pattern"),
            "receipt_number_pattern",
            lambda n: Receipt.objects.filter(number=n).exists(),
            code=college.code,
            fy=year,
        )
        receipt = Receipt.objects.create(
            number=number,
            financial_year=year,
            date=today,
            student=student,
            account=account,
            mode=mode,
            reference=reference.strip(),
            amount=amount,
            notes=notes,
            received_by=user,
        )
        left = amount
        for due in dues:
            if not left:
                break
            part = min(left, due.balance)
            left -= part
            taxable, cgst, sgst = gst_split(part, due.head.gst_rate)
            ReceiptLine.objects.create(
                receipt=receipt,
                due=due,
                head=due.head,
                instalment_label=due.instalment_label,
                amount=part,
                gst_rate=due.head.gst_rate,
                taxable_value=taxable,
                cgst=cgst,
                sgst=sgst,
            )
            due.paid += part
            due.save(update_fields=["paid"])
    return receipt


def cancel(receipt: Receipt, user, reason: str) -> Receipt:
    """Cancel a receipt and put its amounts back on the student's dues."""
    if not reason.strip():
        raise ValidationError({"reason": "Say why the receipt is cancelled."})
    with transaction.atomic():
        receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
        if receipt.is_cancelled:
            raise ValidationError(f"Receipt {receipt.number} is already cancelled.")
        for line in receipt.lines.select_related("due"):
            due = StudentDue.objects.select_for_update().get(pk=line.due_id)
            due.paid -= line.amount
            due.save(update_fields=["paid"])
        receipt.status = Receipt.Status.CANCELLED
        receipt.cancel_reason = reason.strip()
        receipt.cancelled_by = user
        receipt.cancelled_at = timezone.now()
        receipt.save()
    return receipt
