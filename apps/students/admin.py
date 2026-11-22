from django.contrib import admin

from apps.academics.admin import DepartmentScopedAdmin, is_hod_only
from apps.academics.models import Programme
from apps.accounts.permissions import hod_department_ids

from .models import Batch, Section


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
