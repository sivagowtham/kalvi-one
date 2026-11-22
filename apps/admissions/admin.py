from io import BytesIO

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.academics.admin import DepartmentScopedAdmin
from apps.academics.models import AcademicYear, Programme
from apps.accounts.permissions import has_perm
from apps.students import config
from apps.students.admin_tools import PersonForm, SensitiveAdminMixin, sees_sensitive
from apps.students.models import Batch, Consent, Section

from . import services
from .models import Application, Intake


class IntakeForm(forms.ModelForm):
    class Meta:
        model = Intake
        fields = []  # ModelAdmin passes the fields; naming FKs here would query at import

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None:
            self.fields["quota"] = forms.ChoiceField(choices=config.choices(college, "quotas"))


@admin.register(Intake)
class IntakeAdmin(DepartmentScopedAdmin):
    """The admission register: sanctioned, filled and remaining seats per quota."""

    form = IntakeForm
    list_display = ["programme", "academic_year", "quota", "sanctioned_seats", "filled", "left"]
    list_filter = ["academic_year", "programme", "quota"]
    fields = ["academic_year", "programme", "quota", "sanctioned_seats"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        college = request.college

        class BoundForm(form):
            def __init__(self, *args, **kw):
                super().__init__(*args, college=college, **kw)

        return BoundForm

    @admin.display(description="Filled")
    def filled(self, obj):
        return obj.filled()

    @admin.display(description="Left")
    def left(self, obj):
        return obj.sanctioned_seats - obj.filled()


class ApplicationForm(PersonForm):
    secret_inputs = {**PersonForm.secret_inputs, "annual_income": "annual_income"}
    duplicate_message = "This Aadhaar already has an open application this year."

    annual_income = forms.CharField(
        required=False, help_text="Annual family income in rupees. Stored encrypted."
    )
    document_list = forms.MultipleChoiceField(
        required=False,
        label="Documents received",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Application
        fields = []

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, college=college, **kwargs)
        if college is not None and "document_list" in self.fields:
            self.fields["document_list"].choices = config.choices(college, "required_documents")
            self.initial["document_list"] = [
                code for code, received in (self.instance.documents or {}).items() if received
            ]

    def duplicates(self, number):
        year = self.cleaned_data.get("academic_year") or self.instance.academic_year
        return (
            super()
            .duplicates(number)
            .filter(academic_year=year)
            .exclude(status__in=Application.CLOSED)
        )

    def save(self, commit=True):
        if "document_list" in self.cleaned_data:
            chosen = set(self.cleaned_data["document_list"])
            self.instance.documents = {
                code: code in chosen for code, _ in self.fields["document_list"].choices
            }
        return super().save(commit)


APPLICANT = (
    "Applicant",
    {
        "fields": [
            ("application_number", "status", "status_changed_at"),
            ("academic_year", "programme"),
            ("quota", "admission_type"),
            ("initials", "name"),
            "name_tamil",
            ("date_of_birth", "gender", "blood_group"),
            ("mobile", "email"),
            "communication_address",
            "pincode",
        ]
    },
)
FAMILY = (
    "Family (sensitive)",
    {"fields": [("father_name", "mother_name", "guardian_mobile"), "annual_income"]},
)
CATEGORY = (
    "Category (sensitive)",
    {
        "fields": [
            ("community", "caste", "religion"),
            ("is_first_graduate", "first_graduate_cert_no"),
            ("is_govt_school_student", "is_differently_abled"),
            ("community_cert_no", "community_cert_on_file"),
            ("aadhaar_number", "aadhaar_on_file"),
        ]
    },
)
STUDY = (
    "Prior study",
    {
        "fields": [
            ("qualifying_exam", "qualifying_board", "year_of_passing"),
            "school_name",
            ("qualifying_percent", "cutoff_marks", "merit_score"),
            ("tnea_application_no", "tnea_rank"),
            ("emis_id", "umis_id"),
        ]
    },
)
PROGRESS = (
    "Progress",
    {"fields": [("fee_paid", "fee_receipt_no"), "document_list", "notes", "enrol_link"]},
)


def status_action(target, label):
    def action(modeladmin, request, queryset):
        done = 0
        for application in queryset:
            try:
                services.move(application, target, request.user)
                done += 1
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
        if done:
            messages.success(request, f"{label}: {done} application(s).")

    action.__name__ = f"mark_{target}"
    action.short_description = f"{label} the selected applications"
    action.allowed_permissions = ("change",)
    return action


class EnrolForm(forms.Form):
    section = forms.ModelChoiceField(queryset=Section.all_colleges.none())  # set per batch below
    consent_by = forms.ChoiceField(
        choices=Consent.GivenBy.choices,
        initial=Consent.GivenBy.GUARDIAN,
        help_text="A guardian consents for a student under 18 (DPDP Act).",
    )

    def __init__(self, *args, batch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if batch is not None:
            self.fields["section"].queryset = batch.sections.all()


@admin.register(Application)
class ApplicationAdmin(SensitiveAdminMixin, DepartmentScopedAdmin):
    form = ApplicationForm
    list_display = [
        "application_number",
        "display_name",
        "programme",
        "quota",
        "status",
        "fee_paid",
        "qualifying_percent",
    ]
    list_filter = ["academic_year", "programme", "status", "quota", "fee_paid"]
    search_fields = ["application_number", "name", "mobile", "tnea_application_no"]
    readonly_fields = [
        "application_number",
        "status",
        "status_changed_at",
        "aadhaar_on_file",
        "community_cert_on_file",
        "enrol_link",
    ]
    actions = [
        status_action(Application.Status.SUBMITTED, "Submit"),
        status_action(Application.Status.OFFERED, "Offer a seat to"),
        status_action(Application.Status.CONFIRMED, "Confirm"),
        status_action(Application.Status.REJECTED, "Reject"),
        status_action(Application.Status.WITHDRAWN, "Withdraw"),
    ]

    def get_fieldsets(self, request, obj=None):
        if sees_sensitive(request):
            return [APPLICANT, FAMILY, CATEGORY, STUDY, PROGRESS]
        return [APPLICANT, STUDY, PROGRESS]

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.status in (*Application.CLOSED, Application.Status.ENROLLED):
            return False  # closed and enrolled applications are read-only
        return super().has_change_permission(request, obj)

    @admin.display(description="Enrolment")
    def enrol_link(self, obj):
        if obj is None or obj.pk is None:
            return "-"
        if obj.student_id:
            url = reverse("admin:students_student_change", args=[obj.student_id])
            return format_html('Enrolled as <a href="{}">{}</a>', url, obj.student.roll_number)
        if obj.status != Application.Status.CONFIRMED:
            return "Confirm the application first."
        url = reverse("admin:admissions_application_enrol", args=[obj.pk])
        return format_html('<a href="{}">Enrol this applicant</a>', url)

    def get_urls(self):
        extra = [
            path(
                "<int:pk>/enrol/",
                self.admin_site.admin_view(self.enrol_view),
                name="admissions_application_enrol",
            ),
            path(
                "merit-list/",
                self.admin_site.admin_view(self.merit_list_view),
                name="admissions_application_merit_list",
            ),
        ]
        return [*extra, *super().get_urls()]

    def enrol_view(self, request, pk):
        application = get_object_or_404(Application.objects.all(), pk=pk)
        if not has_perm(request.user, "admissions.enrol_application", application):
            raise PermissionDenied
        back = reverse("admin:admissions_application_change", args=[pk])
        batch = Batch.objects.filter(
            programme=application.programme, admission_year=application.academic_year
        ).first()
        if batch is None or not batch.sections.exists():
            messages.error(
                request,
                f"Create the {application.programme.code} batch for {application.academic_year} "
                "and its sections first.",
            )
            return redirect(back)
        form = EnrolForm(request.POST or None, batch=batch)
        if request.method == "POST" and form.is_valid():
            try:
                student = services.enrol(
                    application,
                    request.user,
                    section=form.cleaned_data["section"],
                    consent_by=form.cleaned_data["consent_by"],
                )
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, f"Enrolled as {student.roll_number}.")
                return redirect(reverse("admin:students_student_change", args=[student.pk]))
        return TemplateResponse(
            request,
            "admin/admissions/enrol.html",
            {
                **self.admin_site.each_context(request),
                "title": f"Enrol {application}",
                "application": application,
                "batch": batch,
                "form": form,
                "back_url": back,
                "opts": self.model._meta,
            },
        )

    def merit_list_view(self, request):
        if not has_perm(request.user, "admissions.view_merit_list"):
            raise PermissionDenied
        years = AcademicYear.objects.all()
        programmes = Programme.objects.filter(is_active=True)
        year = (
            years.filter(pk=request.GET.get("year") or 0).first()
            or years.filter(is_current=True).first()
        )
        programme = programmes.filter(pk=request.GET.get("programme") or 0).first()
        community = request.GET.get("community", "")
        rows = list(services.merit_list(year, programme, community)) if year and programme else []
        show_category = sees_sensitive(request)
        if request.GET.get("format") == "xlsx" and rows:
            return self.merit_list_xlsx(rows, programme, year, show_category)
        return TemplateResponse(
            request,
            "admin/admissions/merit_list.html",
            {
                **self.admin_site.each_context(request),
                "title": "Rank list",
                "years": years,
                "programmes": programmes,
                "communities": config.choices(request.college, "communities"),
                "year": year,
                "programme": programme,
                "community": community,
                "rows": rows,
                "show_category": show_category,
                "opts": self.model._meta,
            },
        )

    def merit_list_xlsx(self, rows, programme, year, show_category):
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.title = "Rank list"
        header = ["Rank", "Application", "Name", "Date of birth", "Quota", "Marks %", "Merit"]
        if show_category:
            header.insert(4, "Community")
        sheet.append(header)
        for rank, row in enumerate(rows, start=1):
            values = [
                rank,
                row.application_number,
                row.display_name,
                row.date_of_birth,
                row.quota,
                row.qualifying_percent,
                row.merit_score,
            ]
            if show_category:
                values.insert(4, row.community)
            sheet.append(values)
        out = BytesIO()
        book.save(out)
        response = HttpResponse(
            out.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        name = f"rank-list-{programme.code}-{year.label}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
