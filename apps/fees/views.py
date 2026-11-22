"""Phone-first pages for the accounts counter: find a student, take a payment, print (D29)."""

from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import has_perm, require_perm
from apps.students.models import Student

from . import receipts
from .models import ZERO, PaymentAccount, PaymentMode, Receipt, StudentDue
from .words import rupees_in_words


class PaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    mode = forms.ChoiceField(choices=PaymentMode.choices, initial=PaymentMode.CASH)
    reference = forms.CharField(
        required=False, max_length=60, help_text="UPI transaction ID, cheque or DD number."
    )
    notes = forms.CharField(required=False, max_length=200)

    field_order = ["amount", "mode", "account", "reference", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built here, not on the class: a tenant queryset needs the current college (D12).
        accounts = PaymentAccount.objects.filter(is_active=True)
        self.fields["account"] = forms.ModelChoiceField(
            queryset=accounts,
            label="Received in",
            initial=accounts.filter(kind=PaymentAccount.Kind.CASH).first(),
        )
        self.order_fields(self.field_order)


class CancelForm(forms.Form):
    reason = forms.CharField(max_length=200, widget=forms.TextInput)


def _college(request):
    return {"college": request.college}


@require_perm("fees.collect")
def collect_search(request):
    query = request.GET.get("q", "").strip()
    students = []
    if query:
        students = (
            Student.objects.filter(Q(roll_number__iexact=query) | Q(name__icontains=query))
            .select_related("batch__programme")
            .order_by("roll_number")[:20]
        )
        if len(students) == 1:
            return redirect("fees:collect_student", pk=students[0].pk)
    return render(
        request,
        "fees/collect_search.html",
        _college(request) | {"query": query, "students": students},
    )


def _dues_by_instalment(student):
    groups = OrderedDict()
    dues = StudentDue.objects.filter(student=student).select_related("head", "academic_year")
    for due in dues.order_by("due_date", "instalment_number", "head__sort_order"):
        key = (due.academic_year.label, due.instalment_label, due.due_date)
        groups.setdefault(key, []).append(due)
    return [
        {
            "year": year,
            "label": label,
            "due_date": due_date,
            "dues": items,
            "balance": sum((d.balance for d in items), ZERO),
        }
        for (year, label, due_date), items in groups.items()
    ]


@require_perm("fees.collect")
def collect_student(request, pk):
    student = get_object_or_404(Student.objects.select_related("batch__programme"), pk=pk)
    groups = _dues_by_instalment(student)
    owed = sum((g["balance"] for g in groups), ZERO)
    form = PaymentForm(request.POST or None, initial={"amount": owed or None})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            receipt = receipts.collect(
                student,
                data["amount"],
                mode=data["mode"],
                account=data["account"],
                reference=data["reference"],
                notes=data["notes"],
                user=request.user,
            )
        except ValidationError as error:
            for field, errors in error.message_dict.items():
                form.add_error(field if field in form.fields else None, errors)
        else:
            messages.success(request, f"Receipt {receipt.number} saved.")
            return redirect("fees:receipt", pk=receipt.pk)
    recent = student.receipts.order_by("-created_at")[:5]
    return render(
        request,
        "fees/collect_student.html",
        _college(request)
        | {"student": student, "groups": groups, "owed": owed, "form": form, "recent": recent},
    )


@require_perm("fees.view_receipt")
def receipt_view(request, pk):
    receipt = get_object_or_404(
        Receipt.objects.select_related("student__batch__programme", "account", "received_by"),
        pk=pk,
    )
    lines = receipt.lines.select_related("head").order_by("pk")
    taxable = any(line.gst_rate for line in lines)
    return render(
        request,
        "fees/receipt.html",
        _college(request)
        | {
            "receipt": receipt,
            "lines": lines,
            "taxable": taxable,
            "in_words": rupees_in_words(receipt.amount),
            "can_cancel": not receipt.is_cancelled
            and has_perm(request.user, "fees.cancel_receipt"),
            "can_collect": has_perm(request.user, "fees.collect"),
        },
    )


@require_perm("fees.cancel_receipt")
def cancel_receipt(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    form = CancelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            receipts.cancel(receipt, request.user, form.cleaned_data["reason"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, f"Receipt {receipt.number} is cancelled.")
            return redirect("fees:receipt", pk=receipt.pk)
    return render(
        request, "fees/cancel.html", _college(request) | {"receipt": receipt, "form": form}
    )
