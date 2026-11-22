from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from apps.students import config as student_config
from apps.tenancy.admin import TenantModelAdmin

from .models import FeeHead, FeeStructure, FeeStructureLine, Instalment, PaymentAccount


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
