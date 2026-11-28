from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.academics.admin import DepartmentScopedAdmin, is_hod_only
from apps.academics.models import Course, Semester
from apps.accounts.models import User
from apps.accounts.permissions import has_perm, hod_department_ids
from apps.students.models import Section, StudentSemester
from apps.tenancy.admin import TenantModelAdmin

from . import config, workdays
from .models import (
    Allocation,
    AllocationStudent,
    AllocationTeacher,
    BellSchedule,
    CalendarDay,
    LabGroup,
    LabGroupMember,
    PeriodSlot,
    ScheduleProgramme,
    TimetableEntry,
)


class PeriodSlotInline(admin.TabularInline):
    model = PeriodSlot
    extra = 0


class ScheduleProgrammeInline(admin.TabularInline):
    model = ScheduleProgramme
    extra = 0


@admin.register(BellSchedule)
class BellScheduleAdmin(TenantModelAdmin):
    list_display = ["name", "is_default"]
    inlines = [PeriodSlotInline, ScheduleProgrammeInline]


class FillCalendarForm(forms.Form):
    semester = forms.ModelChoiceField(queryset=Semester.all_colleges.none(), label="Term")
    holidays = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="One holiday a line, a date and its name, e.g. 2027-01-15 Pongal.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["semester"].queryset = Semester.objects.order_by("-start_date")

    def clean_holidays(self):
        try:
            return workdays.parse_holidays(self.cleaned_data["holidays"])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from None


class CalendarDayForm(forms.ModelForm):
    class Meta:
        model = CalendarDay
        fields = ["date", "is_working", "day", "note"]

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None:
            self.fields["day"] = forms.TypedChoiceField(
                choices=[("", "---------"), *config.timetable_days(college)],
                coerce=int,
                empty_value=None,
                required=False,
                help_text=CalendarDay._meta.get_field("day").help_text,
            )


@admin.register(CalendarDay)
class CalendarDayAdmin(TenantModelAdmin):
    list_display = ["date", "weekday", "is_working", "day_label", "note"]
    list_filter = ["is_working"]
    date_hierarchy = "date"
    search_fields = ["note"]
    actions = ["renumber"]
    change_list_template = "admin/timetable/calendarday/change_list.html"

    @admin.display(description="Weekday")
    def weekday(self, obj):
        return f"{obj.date:%A}"

    @admin.display(description="Follows")
    def day_label(self, obj):
        return obj.day_label or "-"

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, form=CalendarDayForm, **kwargs)

        class Form(base):
            def __init__(self, *args, **inner):
                super().__init__(*args, college=request.college, **inner)

        return Form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "is_working" in form.changed_data and config.uses_day_order(request.college):
            moved = workdays.renumber_from(obj.date)
            if moved:
                messages.info(request, f"Day orders moved on for {moved} later dates.")

    @admin.action(description="Run day orders on again from the earliest selected date")
    def renumber(self, request, queryset):
        if not has_perm(request.user, "timetable.fill_calendar"):
            raise PermissionDenied
        first = queryset.order_by("date").first()
        moved = workdays.renumber_from(first.date) if first else 0
        self.message_user(request, f"{moved} dates changed their day order.")

    def get_urls(self):
        fill = path(
            "fill/",
            self.admin_site.admin_view(self.fill_view),
            name="timetable_calendarday_fill",
        )
        return [fill, *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        extra = {"can_fill": has_perm(request.user, "timetable.fill_calendar")}
        return super().changelist_view(request, extra | (extra_context or {}))

    def fill_view(self, request):
        if not has_perm(request.user, "timetable.fill_calendar"):
            raise PermissionDenied
        form = FillCalendarForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            term = form.cleaned_data["semester"]
            result = workdays.fill(term.start_date, term.end_date, form.cleaned_data["holidays"])
            messages.success(
                request,
                f"Added {result.created} dates to the calendar for {term}: {result.working} "
                f"working days and {result.holidays} holidays. {result.kept} dates were already "
                "there and were kept.",
            )
            return redirect(reverse("admin:timetable_calendarday_changelist"))
        context = self.admin_site.each_context(request) | {
            "title": "Fill in a term's calendar",
            "form": form,
            "opts": self.model._meta,
            "cycle": config.setting(request.college, "cycle"),
        }
        return TemplateResponse(request, "admin/timetable/calendarday/fill.html", context)


def _limit_to_hod(request, code, kwargs, field_name, queryset, department_path):
    if is_hod_only(request, code):
        departments = hod_department_ids(request.user, request.college)
        kwargs["queryset"] = queryset.filter(**{f"{department_path}__in": departments})


class LabGroupMemberInline(admin.TabularInline):
    model = LabGroupMember
    extra = 0
    raw_id_fields = ["student"]


@admin.register(LabGroup)
class LabGroupAdmin(DepartmentScopedAdmin):
    list_display = ["name", "section", "semester", "member_count"]
    list_filter = ["semester"]
    search_fields = ["name", "section__batch__programme__code"]
    inlines = [LabGroupMemberInline]
    actions = ["split_evenly"]

    @admin.display(description="Students")
    def member_count(self, obj):
        return obj.members.count()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "section":
            _limit_to_hod(
                request,
                "timetable.add_labgroup",
                kwargs,
                "section",
                Section.objects.all(),
                "batch__programme__department_id",
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.action(description="Share the section's students evenly by roll number")
    def split_evenly(self, request, queryset):
        groups = list(queryset.order_by("name"))
        keys = {(g.section_id, g.semester_id) for g in groups}
        if len(keys) != 1:
            self.message_user(
                request, "Choose the lab groups of one section and term.", messages.ERROR
            )
            return
        for group in groups:
            if not has_perm(request.user, "timetable.change_labgroup", group):
                raise PermissionDenied
        section_id, semester_id = keys.pop()
        placed = StudentSemester.objects.filter(section_id=section_id, semester_id=semester_id)
        students = [
            p.student for p in placed.select_related("student").order_by("student__roll_number")
        ]
        if not students:
            self.message_user(
                request, "No student is placed in this section for the term.", messages.ERROR
            )
            return
        for group in groups:
            for member in group.members.all():
                member.delete()
        size = -(-len(students) // len(groups))
        for index, student in enumerate(students):
            LabGroupMember.objects.create(group=groups[index // size], student=student)
        self.message_user(request, f"Shared {len(students)} students among {len(groups)} groups.")


class AllocationTeacherInline(admin.TabularInline):
    model = AllocationTeacher
    extra = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "teacher":
            kwargs["queryset"] = User.objects.filter(
                college=request.college, is_active=True
            ).order_by("full_name", "username")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class AllocationStudentInline(admin.TabularInline):
    model = AllocationStudent
    extra = 0
    raw_id_fields = ["student"]


class TimetableEntryForm(forms.ModelForm):
    # Declared here so the form class can be built without a current college (D12).
    period = forms.ModelChoiceField(queryset=PeriodSlot.all_colleges.none())

    class Meta:
        model = TimetableEntry
        fields = ["day", "period", "room"]

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None:
            self.fields["day"] = forms.TypedChoiceField(
                choices=config.timetable_days(college), coerce=int
            )
        self.fields["period"].queryset = PeriodSlot.objects.select_related("schedule")


class TimetableEntryInline(admin.TabularInline):
    model = TimetableEntry
    form = TimetableEntryForm
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        college = request.college

        class Form(TimetableEntryForm):
            def __init__(self, *args, **inner):
                super().__init__(*args, college=college, **inner)

        kwargs["form"] = Form
        return super().get_formset(request, obj, **kwargs)


@admin.register(Allocation)
class AllocationAdmin(DepartmentScopedAdmin):
    list_display = ["course", "section", "lab_group", "semester", "teacher_names", "hours_per_week"]
    list_filter = ["semester", "section__batch__programme"]
    search_fields = ["course__code", "course__title", "teachers__teacher__full_name"]
    inlines = [AllocationTeacherInline, TimetableEntryInline, AllocationStudentInline]

    @admin.display(description="Teachers")
    def teacher_names(self, obj):
        return ", ".join(
            t.teacher.get_full_name() or t.teacher.username
            for t in obj.teachers.select_related("teacher")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "section":
            _limit_to_hod(
                request,
                "timetable.add_allocation",
                kwargs,
                "section",
                Section.objects.all(),
                "batch__programme__department_id",
            )
        if db_field.name == "course":
            _limit_to_hod(
                request,
                "timetable.add_allocation",
                kwargs,
                "course",
                Course.objects.all(),
                "programme__department_id",
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
