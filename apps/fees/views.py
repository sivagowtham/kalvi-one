"""Phone-first pages for the accounts counter: find a student, take a payment, print (D29)."""

from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.academics.models import AcademicYear
from apps.accounts.permissions import has_perm, require_perm
from apps.students.models import Batch, Student

from . import ask, receipts, reminders, reports, risk, tally
from . import config as fee_config
from .models import (
    ZERO,
    FeeHead,
    PaymentAccount,
    PaymentMode,
    Receipt,
    StudentDue,
    TallyExport,
)
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


class DuesReportForm(forms.Form):
    overdue = forms.BooleanField(required=False, label="Only what is overdue today")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"] = forms.ModelChoiceField(
            queryset=AcademicYear.objects.all(), required=False, empty_label="Every year"
        )
        self.fields["batch"] = forms.ModelChoiceField(
            queryset=Batch.objects.select_related("programme").filter(is_active=True),
            required=False,
            empty_label="Every batch",
        )
        self.fields["head"] = forms.ModelChoiceField(
            queryset=FeeHead.objects.all(), required=False, empty_label="Every fee head"
        )
        self.order_fields(["academic_year", "batch", "head", "overdue"])

    def filters(self) -> reports.DuesFilter:
        data = self.cleaned_data
        return reports.DuesFilter(
            academic_year=data.get("academic_year"),
            batch=data.get("batch"),
            head=data.get("head"),
            overdue_on=timezone.localdate() if data.get("overdue") else None,
        )


@require_perm("fees.view_reports")
def dues_report(request):
    if request.GET:
        form = DuesReportForm(request.GET)
    else:
        current = AcademicYear.objects.filter(is_current=True).first()
        form = DuesReportForm({"academic_year": current.pk if current else ""})
    filters = form.filters() if form.is_valid() else reports.DuesFilter()
    batches, totals = reports.dues_by_batch(filters)
    owing = reports.students_owing(filters) if filters.batch is not None else []
    if request.GET.get("format") == "xlsx":
        sheets = [
            (
                "By batch",
                [
                    "Batch",
                    "Students",
                    "Owing",
                    "Fees",
                    "Concession",
                    "Government",
                    "To pay",
                    "Paid",
                    "Balance",
                ],
                [
                    [
                        r["batch"],
                        r["students"],
                        r["owing"],
                        r["amount"],
                        r["waived"],
                        r["govt_share"],
                        r["payable"],
                        r["paid"],
                        r["balance"],
                    ]
                    for r in batches
                ],
            ),
            (
                "Students owing",
                ["Roll number", "Name", "Mobile", "To pay", "Paid", "Balance", "Government"],
                [
                    [
                        r["roll_number"],
                        r["name"],
                        r["mobile"],
                        r["payable"],
                        r["paid"],
                        r["balance"],
                        r["govt_share"],
                    ]
                    for r in reports.students_owing(filters)
                ],
            ),
        ]
        return reports.xlsx_response(f"dues-{timezone.localdate():%Y-%m-%d}.xlsx", sheets)
    query = request.GET.urlencode()
    return render(
        request,
        "fees/dues_report.html",
        _college(request)
        | {
            "form": form,
            "batches": batches,
            "totals": totals,
            "owing": owing,
            "batch": filters.batch,
            "query": query,
            "can_collect": has_perm(request.user, "fees.collect"),
            "can_ask": ask.enabled(request.college),
        },
    )


class CollectionsForm(forms.Form):
    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="From")
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="To")

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise ValidationError("The start date is after the end date.")
        if data.get("start") and data.get("end") and (data["end"] - data["start"]).days > 366:
            raise ValidationError("Choose at most a year at a time.")
        return data


@require_perm("fees.view_reports")
def collections_report(request):
    today = timezone.localdate()
    form = CollectionsForm(request.GET or {"start": today, "end": today})
    result = None
    if form.is_valid():
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        result = reports.collections(start, end)
        if request.GET.get("format") == "xlsx":
            modes = dict(PaymentMode.choices)
            return reports.xlsx_response(
                f"collections-{start:%Y-%m-%d}-to-{end:%Y-%m-%d}.xlsx",
                [
                    (
                        "By day",
                        ["Date", "Mode", "Receipts", "Amount"],
                        [
                            [r["date"], modes[r["mode"]], r["count"], r["amount"]]
                            for r in result["by_day"]
                        ],
                    ),
                    (
                        "By fee head",
                        ["Fee head", "Tally ledger", "Amount", "CGST", "SGST"],
                        [
                            [
                                r["head__name"],
                                r["head__tally_ledger"],
                                r["amount"],
                                r["cgst"],
                                r["sgst"],
                            ]
                            for r in result["by_head"]
                        ],
                    ),
                ],
            )
        modes = dict(PaymentMode.choices)
        for row in result["by_day"]:
            row["mode_label"] = modes[row["mode"]]
    return render(
        request,
        "fees/collections_report.html",
        _college(request)
        | {
            "form": form,
            "result": result,
            "query": request.GET.urlencode(),
            "can_ask": ask.enabled(request.college),
        },
    )


def _xml_download(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_perm("fees.export_tally")
def tally_home(request):
    today = timezone.localdate()
    receipts_due, cancellations_due = tally.pending(today)
    if request.method == "POST":
        try:
            export = tally.create_export(request.user, today)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(
                request,
                f"Tally file made with {export.receipts} receipt(s) and "
                f"{export.cancellations} cancellation(s). Download it below.",
            )
        return redirect("fees:tally")
    return render(
        request,
        "fees/tally.html",
        _college(request)
        | {
            "today": today,
            "pending_receipts": receipts_due.count(),
            "pending_total": receipts_due.aggregate(total=Sum("amount"))["total"] or ZERO,
            "pending_cancellations": cancellations_due.count(),
            "exports": TallyExport.objects.select_related("created_by")[:30],
            "company": fee_config.setting(request.college, "tally_company"),
        },
    )


@require_perm("fees.export_tally")
def tally_download(request, pk):
    export = get_object_or_404(TallyExport, pk=pk)
    name = f"tally-receipts-{request.college.code}-{export.up_to:%Y-%m-%d}-{export.pk}.xml"
    return _xml_download(tally.build_file(export), name.lower())


@require_perm("fees.export_tally")
def tally_ledgers(request):
    return _xml_download(
        tally.ledger_file(request.college), f"tally-ledgers-{request.college.code}.xml".lower()
    )


ASK_TARGETS = {
    "dues": "fees:dues_report",
    "at_risk": "fees:at_risk",
    "collections": "fees:collections_report",
}


@require_perm("fees.view_reports")
@require_POST
def ask_question(request):
    """Turn a plain-word question into a report and open it (D32)."""
    question = request.POST.get("question", "")
    back = request.POST.get("next") or reverse("fees:dues_report")
    if not back.startswith("/") or back.startswith("//"):
        back = reverse("fees:dues_report")
    if not ask.enabled(request.college):
        return redirect(back)
    try:
        answer = ask.interpret(request.college, question, timezone.localdate())
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect(back)
    if answer.summary:
        messages.info(request, answer.summary)
    url = reverse(ASK_TARGETS[answer.report])
    if answer.report == "dues" and "academic_year" not in answer.params:
        answer.params["academic_year"] = ""  # every year, not the default current one
    return redirect(f"{url}?{urlencode(answer.params)}")


class RiskForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"] = forms.ModelChoiceField(
            queryset=Batch.objects.select_related("programme").filter(is_active=True),
            required=False,
            empty_label="Every batch",
        )
        self.fields["head"] = forms.ModelChoiceField(
            queryset=FeeHead.objects.all(), required=False, empty_label="Every fee head"
        )


@require_perm("fees.view_reports")
def at_risk(request):
    """Students with overdue fees, most at risk first, with the reasons in plain words."""
    form = RiskForm(request.GET)
    filters = reports.DuesFilter()
    if form.is_valid():
        filters.batch = form.cleaned_data.get("batch")
        filters.head = form.cleaned_data.get("head")
    flagged = risk.flags(filters, timezone.localdate())
    return render(
        request,
        "fees/at_risk.html",
        _college(request)
        | {
            "form": form,
            "flags": flagged[:200],
            "high": sum(1 for f in flagged if f.level == risk.HIGH),
            "count": len(flagged),
            "can_remind": has_perm(request.user, "fees.send_reminder"),
            "can_ask": ask.enabled(request.college),
        },
    )


@require_perm("fees.send_reminder")
def reminder(request, pk):
    student = get_object_or_404(Student.objects.select_related("batch__programme"), pk=pk)
    today = timezone.localdate()
    overdue = [
        due
        for due in StudentDue.objects.filter(student=student, due_date__lt=today)
        if due.balance > 0
    ]
    balance = sum((due.balance for due in overdue), ZERO)
    oldest = min((due.due_date for due in overdue), default=None)
    return render(
        request,
        "fees/reminder.html",
        _college(request)
        | {
            "student": student,
            "balance": balance,
            "drafts": reminders.drafts(request.college, student, balance, oldest)
            if balance
            else [],
        },
    )
