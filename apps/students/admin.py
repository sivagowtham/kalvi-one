from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.academics.admin import DepartmentScopedAdmin, is_hod_only
from apps.academics.models import Programme
from apps.accounts.permissions import has_perm, hod_department_ids
from apps.tenancy.admin import TenantModelAdmin

from . import config
from .models import Batch, Consent, Guardian, Section, Student
from .validators import normalise_aadhaar


@admin.register(Batch)
class BatchAdmin(DepartmentScopedAdmin):
    list_display = ["programme", "label", "admission_year", "regulation", "is_active"]
    list_filter = ["is_active", "admission_year", "programme"]
    search_fields = ["label", "programme__code", "programme__name"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "programme" and is_hod_only(request, "students.add_batch"):
            departments = hod_department_ids(request.user, request.college)
            kwargs["queryset"] = Programme.objects.filter(department_id__in=departments)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Section)
class SectionAdmin(DepartmentScopedAdmin):
    list_display = ["batch", "name", "capacity"]
    list_filter = ["batch__programme", "batch"]
    search_fields = ["name", "batch__label", "batch__programme__code"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "batch" and is_hod_only(request, "students.add_section"):
            departments = hod_department_ids(request.user, request.college)
            kwargs["queryset"] = Batch.objects.filter(programme__department_id__in=departments)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


def sees_sensitive(request) -> bool:
    return has_perm(request.user, "students.view_sensitive")


class GuardianForm(forms.ModelForm):
    annual_income = forms.CharField(
        required=False, help_text="Annual family income in rupees. Stored encrypted."
    )

    class Meta:
        model = Guardian
        fields = ["relation", "name", "occupation", "mobile", "email", "is_primary"]

    def save(self, commit=True):
        if self.cleaned_data.get("annual_income"):
            self.instance.set_secret("annual_income", self.cleaned_data["annual_income"])
        return super().save(commit)


class GuardianInline(admin.StackedInline):
    model = Guardian
    form = GuardianForm
    extra = 0
    fields = [
        ("relation", "name", "is_primary"),
        ("occupation", "mobile", "email"),
        ("annual_income", "income_on_file"),
    ]
    readonly_fields = ["income_on_file"]

    @admin.display(description="Income on file")
    def income_on_file(self, obj):
        return "recorded" if obj and obj.has_secret("annual_income") else "not recorded"


class ConsentInline(admin.TabularInline):
    model = Consent
    extra = 0
    fields = ["notice_version", "given_by", "guardian", "method", "given_at", "withdrawn_at"]


class StudentForm(forms.ModelForm):
    aadhaar_number = forms.CharField(
        required=False,
        label="Aadhaar number",
        help_text="Type a new number to set or replace it. Stored encrypted; blank keeps it.",
    )
    community_cert_no = forms.CharField(
        required=False,
        label="Community certificate number",
        help_text="Type to set or replace it. Stored encrypted; blank keeps it.",
    )

    class Meta:
        model = Student
        fields = []  # ModelAdmin passes the fields from its fieldsets

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None:
            for name, key in [("community", "communities"), ("quota", "quotas")]:
                if name in self.fields:
                    self.fields[name] = forms.ChoiceField(
                        choices=[("", "---------"), *config.choices(college, key)],
                        required=False,
                        label=self.fields[name].label,
                    )

    def clean_aadhaar_number(self):
        value = self.cleaned_data.get("aadhaar_number", "")
        return normalise_aadhaar(value) if value else ""

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("aadhaar_number")
        if number:
            from . import crypto

            clash = Student.objects.filter(aadhaar_hash=crypto.keyed_hash(number))
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise ValidationError({"aadhaar_number": "Another student has this Aadhaar."})
        return cleaned

    def save(self, commit=True):
        secrets = {"aadhaar": "aadhaar_number", "community_cert_no": "community_cert_no"}
        for name, field in secrets.items():
            if self.cleaned_data.get(field):
                self.instance.set_secret(name, self.cleaned_data[field])
        return super().save(commit)


IDENTITY = (
    "Identity",
    {
        "fields": [
            ("roll_number", "admission_number", "register_number"),
            ("initials", "name"),
            "name_tamil",
            ("date_of_birth", "gender", "blood_group"),
            "user",
        ]
    },
)
COURSE = (
    "Course",
    {"fields": [("batch", "entry_semester"), ("admission_type", "admission_date"), "residence"]},
)
CATEGORY = (
    "Category (sensitive)",
    {
        "fields": [
            ("community", "caste"),
            ("religion", "nationality", "mother_tongue"),
            ("is_first_graduate", "first_graduate_cert_no"),
            "is_govt_school_student",
            ("is_differently_abled", "disability_note"),
            "quota",
            ("community_cert_no", "community_cert_on_file"),
        ]
    },
)
PRIOR = (
    "Prior study",
    {
        "fields": [
            ("qualifying_exam", "qualifying_board", "year_of_passing"),
            "school_name",
            ("qualifying_percent", "cutoff_marks"),
            ("tnea_application_no", "tnea_rank"),
        ]
    },
)
CONTACT = (
    "Contact",
    {"fields": [("mobile", "email"), "communication_address", "permanent_address", "pincode"]},
)
IDS = ("Government IDs", {"fields": [("emis_id", "umis_id", "apaar_id")]})
AADHAAR = ("Aadhaar (sensitive)", {"fields": [("aadhaar_on_file", "aadhaar_number")]})
STATUS = ("Status", {"fields": [("status", "status_date"), "status_note"]})


@admin.register(Student)
class StudentAdmin(DepartmentScopedAdmin):
    form = StudentForm
    list_display = ["roll_number", "display_name", "batch", "status", "residence"]
    list_filter = ["status", "batch", "residence", "admission_type"]
    search_fields = ["roll_number", "admission_number", "register_number", "name", "mobile"]
    list_select_related = ["batch__programme"]
    readonly_fields = ["aadhaar_on_file", "community_cert_on_file"]
    inlines = [GuardianInline, ConsentInline]

    def get_fieldsets(self, request, obj=None):
        if sees_sensitive(request):
            return [IDENTITY, COURSE, CATEGORY, PRIOR, CONTACT, IDS, AADHAAR, STATUS]
        return [IDENTITY, COURSE, PRIOR, CONTACT, IDS, STATUS]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        college = request.college

        class BoundForm(form):
            def __init__(self, *args, **kw):
                super().__init__(*args, college=college, **kw)

        return BoundForm

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not has_perm(request.user, "students.edit_student_details"):
            editable = {"register_number"}
            fields = [
                f
                for _, opts in self.get_fieldsets(request, obj)
                for row in opts["fields"]
                for f in (row if isinstance(row, tuple) else (row,))
            ]
            readonly += [f for f in fields if f not in editable and f not in readonly]
        return readonly

    def get_inlines(self, request, obj):
        return self.inlines if sees_sensitive(request) else []

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            from apps.accounts.models import User

            kwargs["queryset"] = User.objects.filter(college=request.college)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Aadhaar on file")
    def aadhaar_on_file(self, obj):
        if obj is None or not obj.has_secret("aadhaar"):
            return "not recorded"
        url = reverse("admin:students_student_reveal", args=[obj.pk, "aadhaar"])
        return format_html('{} <a href="{}">Reveal (audited)</a>', obj.masked("aadhaar"), url)

    @admin.display(description="Certificate on file")
    def community_cert_on_file(self, obj):
        if obj is None or not obj.has_secret("community_cert_no"):
            return "not recorded"
        url = reverse("admin:students_student_reveal", args=[obj.pk, "community_cert_no"])
        return format_html('recorded <a href="{}">Reveal (audited)</a>', url)

    def get_urls(self):
        reveal = path(
            "<int:pk>/reveal/<str:field>/",
            self.admin_site.admin_view(self.reveal_view),
            name="students_student_reveal",
        )
        return [reveal, *super().get_urls()]

    def reveal_view(self, request, pk, field):
        student = get_object_or_404(Student.objects.all(), pk=pk)
        if field not in Student.sensitive_fields:
            raise PermissionDenied
        value = student.reveal(field, request.user)  # checks the permission and audits
        labels = {"aadhaar": "Aadhaar number", "community_cert_no": "Community certificate number"}
        return TemplateResponse(
            request,
            "admin/students/reveal.html",
            {
                **self.admin_site.each_context(request),
                "object": student,
                "label": labels[field],
                "value": value,
                "back_url": reverse("admin:students_student_change", args=[pk]),
            },
        )


@admin.register(Consent)
class ConsentAdmin(TenantModelAdmin):
    list_display = ["student", "notice_version", "given_by", "method", "given_at", "withdrawn_at"]
    list_filter = ["notice_version", "given_by", "method"]
    search_fields = ["student__roll_number", "student__name"]
