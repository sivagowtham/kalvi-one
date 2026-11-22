from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.accounts.permissions import hod_department_ids, roles_for
from apps.accounts.roles import Role
from apps.tenancy.admin import TenantModelAdmin

from .models import AcademicYear, Course, Department, Programme, Semester


def is_hod_only(request, code: str) -> bool:
    """True when the user's access to ``code`` comes only from an HOD role."""
    from apps.accounts.permissions import registered

    granting = roles_for(request.user, request.college) & registered()[code].roles
    return granting == {Role.HOD}


class DepartmentScopedAdmin(TenantModelAdmin):
    """Enforces D14 on saves: an HOD may only save objects inside their own department."""

    def save_model(self, request, obj, form, change):
        action = "change" if change else "add"
        code = f"{self.opts.app_label}.{action}_{self.opts.model_name}"
        if not request.user.has_perm(code, obj):
            raise PermissionDenied
        super().save_model(request, obj, form, change)


@admin.register(Department)
class DepartmentAdmin(DepartmentScopedAdmin):
    list_display = ["code", "name", "is_active"]
    search_fields = ["code", "name"]


@admin.register(Programme)
class ProgrammeAdmin(DepartmentScopedAdmin):
    list_display = ["code", "name", "department", "level", "total_semesters", "regulation"]
    list_filter = ["level", "department", "regulation"]
    search_fields = ["code", "name"]


@admin.register(Course)
class CourseAdmin(DepartmentScopedAdmin):
    list_display = ["code", "title", "programme", "semester_number", "credits", "course_type"]
    list_filter = ["programme", "semester_number", "course_type"]
    search_fields = ["code", "title"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "programme" and is_hod_only(request, "academics.add_course"):
            departments = hod_department_ids(request.user, request.college)
            kwargs["queryset"] = Programme.objects.filter(department_id__in=departments)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SemesterInline(admin.TabularInline):
    model = Semester
    extra = 0


@admin.register(AcademicYear)
class AcademicYearAdmin(TenantModelAdmin):
    list_display = ["label", "start_date", "end_date", "is_current"]
    inlines = [SemesterInline]


@admin.register(Semester)
class SemesterAdmin(TenantModelAdmin):
    list_display = ["__str__", "start_date", "end_date", "is_current"]
    list_filter = ["academic_year", "term"]
