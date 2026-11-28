from django import forms
from django.contrib import admin, messages
from django.db import IntegrityError
from django.utils.html import format_html_join

from apps.tenancy.admin import TenantModelAdmin

from .models import ZERO, AssessmentScheme, GradeBand, GradeScale, SchemeComponent


class LockedReadOnly:
    """Locked rows (in use by marks or results) open read-only; use "Make a copy" instead."""

    def has_change_permission(self, request, obj=None):
        if obj is not None and getattr(obj, "is_locked", False):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and getattr(obj, "is_locked", False):
            return False
        return super().has_delete_permission(request, obj)


def show_problems(obj) -> str:
    if obj is None or obj.pk is None:
        return "-"
    found = obj.problems()
    if not found:
        return "Ready to use."
    return format_html_join("", "<p>{}</p>", ((p,) for p in found))


class GradeBandInline(LockedReadOnly, admin.TabularInline):
    model = GradeBand
    extra = 0
    fields = ["letter", "description", "grade_point", "min_percent", "is_pass"]


@admin.register(GradeScale)
class GradeScaleAdmin(LockedReadOnly, TenantModelAdmin):
    list_display = ["code", "name", "fail_letter", "is_locked"]
    search_fields = ["code", "name"]
    readonly_fields = ["is_locked", "check_result"]
    fields = [
        "code",
        "name",
        "fail_letter",
        "absent_letter",
        "shortage_letter",
        "withdrawal_letter",
        "is_locked",
        "check_result",
    ]
    inlines = [GradeBandInline]
    actions = ["make_copy"]

    @admin.display(description="Check")
    def check_result(self, obj):
        return show_problems(obj)

    @admin.action(description="Make an editable copy", permissions=["add"])
    def make_copy(self, request, queryset):
        for scale in queryset:
            try:
                new = scale.copy(f"{scale.code}-COPY"[:30])
            except IntegrityError:
                self.message_user(
                    request,
                    f"{scale.code}-COPY already exists. Rename it first.",
                    messages.ERROR,
                )
                continue
            self.message_user(request, f"Copied {scale.code} to {new.code}.")


class ComponentFormSet(forms.BaseInlineFormSet):
    """The components must add up to the scheme's internal maximum."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        total = ZERO
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            total += form.cleaned_data.get("weight") or ZERO
        internal_max = self.instance.internal_max
        if internal_max is not None and total != internal_max:
            raise forms.ValidationError(
                f"The components are worth {total} in all, but the internal maximum is "
                f"{internal_max}. Make them add up."
            )


class SchemeComponentInline(LockedReadOnly, admin.TabularInline):
    model = SchemeComponent
    formset = ComponentFormSet
    extra = 0
    fields = [
        "sort_order",
        "code",
        "name",
        "kind",
        "count",
        "max_marks",
        "rule",
        "best_of",
        "weight",
    ]


@admin.register(AssessmentScheme)
class AssessmentSchemeAdmin(LockedReadOnly, TenantModelAdmin):
    list_display = [
        "code",
        "regulation",
        "course_type",
        "internal_max",
        "external_max",
        "min_external_percent",
        "min_total_percent",
        "grade_scale",
        "is_active",
        "is_locked",
    ]
    list_filter = ["regulation", "course_type", "is_active", "is_locked"]
    search_fields = ["code", "name", "regulation"]
    readonly_fields = ["is_locked", "check_result"]
    fieldsets = [
        (None, {"fields": ["code", "name", "regulation", "course_type", "is_active"]}),
        ("Marks", {"fields": ["internal_max", "external_max"]}),
        (
            "Pass rule",
            {
                "fields": [
                    "grade_scale",
                    "min_external_percent",
                    "min_total_percent",
                    "min_internal_percent",
                ]
            },
        ),
        ("Status", {"fields": ["is_locked", "check_result"]}),
    ]
    inlines = [SchemeComponentInline]
    actions = ["make_copy"]

    @admin.display(description="Check")
    def check_result(self, obj):
        return show_problems(obj)

    @admin.action(description="Make an editable copy (starts inactive)", permissions=["add"])
    def make_copy(self, request, queryset):
        for scheme in queryset:
            try:
                new = scheme.copy(f"{scheme.code}-COPY"[:30])
            except IntegrityError:
                self.message_user(
                    request,
                    f"{scheme.code}-COPY already exists. Rename it first.",
                    messages.ERROR,
                )
                continue
            self.message_user(
                request,
                f"Copied {scheme.code} to {new.code}. Check it, then make it active in place of "
                "the old one.",
            )
