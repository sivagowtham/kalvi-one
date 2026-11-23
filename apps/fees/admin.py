from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils.html import format_html

from apps.accounts.permissions import has_perm
from apps.students import config as student_config
from apps.tenancy.admin import TenantModelAdmin

from . import config, dues
from .models import (
    Concession,
    FeeHead,
    FeeStructure,
    FeeStructureLine,
    Instalment,
    PaymentAccount,
    Receipt,
    ReceiptLine,
    StudentDue,
    TallyExport,
)


@admin.register(FeeHead)
class FeeHeadAdmin(TenantModelAdmin):
    list_display = ["code", "name", "tally_ledger", "gst_rate", "sort_order", "is_active"]
    list_editable = ["tally_ledger", "sort_order"]
    list_filter = ["is_active"]
    search_fields = ["code", "name", "tally_ledger"]


@admin.register(PaymentAccount)
class PaymentAccountAdmin(TenantModelAdmin):
    list_display = ["name", "kind", "tally_ledger", "is_active"]
    list_editable = ["tally_ledger"]
    list_filter = ["kind", "is_active"]


class InstalmentInline(admin.TabularInline):
    model = Instalment
    extra = 0
    min_num = 1
    fields = ["number", "label", "due_date"]


class LineFormSet(forms.BaseInlineFormSet):
    """Each amount must belong to an instalment set up on the same page."""

    def submitted_instalment_numbers(self) -> set[int]:
        prefix = "instalments"
        total = int(self.data.get(f"{prefix}-TOTAL_FORMS", 0) or 0)
        numbers = set()
        for index in range(total):
            if self.data.get(f"{prefix}-{index}-DELETE"):
                continue
            value = self.data.get(f"{prefix}-{index}-number", "")
            if str(value).isdigit():
                numbers.add(int(value))
        return numbers

    def clean(self):
        super().clean()
        numbers = self.submitted_instalment_numbers()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            number = form.cleaned_data.get("instalment_number")
            if number is not None and number not in numbers:
                raise ValidationError(f"Instalment {number} is not set up above.")


class LineInline(admin.TabularInline):
    model = FeeStructureLine
    formset = LineFormSet
    extra = 0
    min_num = 1
    fields = ["instalment_number", "head", "amount"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "head":
            kwargs["queryset"] = FeeHead.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = []  # ModelAdmin passes the fields; naming FKs here would query at import

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None:
            self.fields["quota"] = forms.ChoiceField(
                choices=[("", "Every quota"), *student_config.choices(college, "quotas")],
                required=False,
            )


@admin.register(FeeStructure)
class FeeStructureAdmin(TenantModelAdmin):
    """A year's fees for one batch: instalments with due dates, then the amount per head."""

    form = FeeStructureForm
    list_display = ["batch", "academic_year", "year", "quota", "residence", "total", "is_active"]
    list_filter = ["academic_year", "batch__programme", "quota", "residence", "is_active"]
    list_select_related = ["batch__programme", "batch__admission_year", "academic_year"]
    fields = ["batch", "academic_year", "quota", "residence", "notes", "is_active"]
    inlines = [InstalmentInline, LineInline]
    actions = ["raise_dues"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        college = request.college

        class BoundForm(form):
            def __init__(self, *args, **kw):
                super().__init__(*args, college=college, **kw)

        return BoundForm

    @admin.display(description="Year of study")
    def year(self, obj):
        return obj.year_of_study

    @admin.display(description="Total (₹)")
    def total(self, obj):
        return f"{obj.total():,.2f}"

    def has_raise_dues_permission(self, request):
        return has_perm(request.user, "fees.raise_dues")

    @admin.action(
        description="Raise dues for the students of these structures", permissions=["raise_dues"]
    )
    def raise_dues(self, request, queryset):
        done = set()
        for structure in queryset.select_related("batch", "academic_year"):
            key = (structure.batch_id, structure.academic_year_id)
            if key in done:
                continue
            done.add(key)
            result = dues.raise_dues(structure.batch, structure.academic_year)
            self.message_user(
                request,
                f"{structure.batch} {structure.academic_year}: {result.created} dues raised for "
                f"{result.students} student(s).",
            )
            if result.skipped:
                self.message_user(
                    request, "Not raised: " + "; ".join(result.skipped), messages.WARNING
                )


class ConcessionForm(forms.ModelForm):
    class Meta:
        model = Concession
        fields = []

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None and "kind" in self.fields:
            self.fields["kind"] = forms.ChoiceField(
                label="Type",
                choices=[
                    (code, f"{label} ({'government' if funder == 'government' else 'college'})")
                    for code, (label, funder) in config.concession_types(college).items()
                ],
            )


@admin.register(Concession)
class ConcessionAdmin(TenantModelAdmin):
    """Concessions are entered by the office and count only once the principal approves."""

    form = ConcessionForm
    list_display = [
        "student",
        "academic_year",
        "kind",
        "funded_by",
        "head",
        "percent",
        "amount",
        "status",
    ]
    list_filter = ["status", "funded_by", "kind", "academic_year"]
    search_fields = ["student__roll_number", "student__name", "reason"]
    list_select_related = ["student", "academic_year", "head"]
    autocomplete_fields = ["student"]
    fields = ["student", "academic_year", "kind", "head", "percent", "amount", "reason"]
    actions = ["approve", "reject", "withdraw"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        college = request.college

        class BoundForm(form):
            def __init__(self, *args, **kw):
                super().__init__(*args, college=college, **kw)

        return BoundForm

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.status != Concession.Status.PENDING:
            return [*self.fields, "status", "decided_by", "decided_at"]
        return []

    def has_approve_permission(self, request):
        return has_perm(request.user, "fees.approve_concession")

    def _decide(self, request, queryset, decide, verb):
        if not self.has_approve_permission(request):
            raise PermissionDenied
        done = 0
        for concession in queryset.select_related("student", "academic_year"):
            try:
                warnings = decide(concession, request.user)
            except ValidationError as error:
                self.message_user(request, f"{concession}: {error.messages[0]}", messages.ERROR)
                continue
            done += 1
            for warning in warnings:
                self.message_user(request, warning, messages.WARNING)
        if done:
            self.message_user(request, f"{verb}: {done} concession(s).")

    @admin.action(description="Approve the selected concessions", permissions=["approve"])
    def approve(self, request, queryset):
        self._decide(request, queryset, dues.approve, "Approved")

    @admin.action(description="Reject the selected concessions", permissions=["approve"])
    def reject(self, request, queryset):
        self._decide(request, queryset, dues.reject, "Rejected")

    @admin.action(description="Withdraw the selected approved concessions", permissions=["approve"])
    def withdraw(self, request, queryset):
        self._decide(request, queryset, dues.withdraw, "Withdrawn")


@admin.register(StudentDue)
class StudentDueAdmin(TenantModelAdmin):
    """Read-only: dues come from fee structures, concessions and receipts."""

    list_display = [
        "student",
        "instalment_label",
        "head",
        "due_date",
        "amount",
        "waived",
        "govt_share",
        "paid",
        "balance",
    ]
    list_filter = ["academic_year", "student__batch", "head", "instalment_number"]
    search_fields = ["student__roll_number", "student__name"]
    list_select_related = ["student", "head"]
    date_hierarchy = "due_date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Balance")
    def balance(self, obj):
        return obj.balance


class ReceiptLineInline(admin.TabularInline):
    model = ReceiptLine
    extra = 0
    fields = ["head", "instalment_label", "amount", "gst_rate", "taxable_value", "cgst", "sgst"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Receipt)
class ReceiptAdmin(TenantModelAdmin):
    """Read-only: receipts are taken and cancelled on the fee counter pages (D29)."""

    list_display = ["number", "date", "student", "amount", "mode", "account", "status", "open"]
    list_filter = ["status", "mode", "account", "financial_year", "date"]
    search_fields = ["number", "student__roll_number", "student__name", "reference"]
    list_select_related = ["student", "account"]
    date_hierarchy = "date"
    readonly_fields = [
        "number",
        "date",
        "student",
        "account",
        "mode",
        "reference",
        "amount",
        "notes",
        "received_by",
        "status",
        "cancel_reason",
        "cancelled_by",
        "cancelled_at",
        "tally_export",
        "tally_cancel_export",
    ]
    fields = readonly_fields
    inlines = [ReceiptLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Print")
    def open(self, obj):
        return format_html('<a href="{}">Open</a>', reverse("fees:receipt", args=[obj.pk]))


@admin.register(TallyExport)
class TallyExportAdmin(TenantModelAdmin):
    """Read-only record of each Tally file; files are made on the Tally page (D31)."""

    list_display = ["created_at", "up_to", "receipts", "cancellations", "total", "created_by"]
    readonly_fields = ["up_to", "receipts", "cancellations", "total", "created_by", "created_at"]
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
