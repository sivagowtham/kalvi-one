from django.contrib import admin

from .models import College, CollegeFeature


class CollegeFeatureInline(admin.TabularInline):
    model = CollegeFeature
    extra = 0


@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "slug", "college_type", "affiliation_status", "is_active"]
    list_filter = ["college_type", "affiliation_status", "is_active"]
    search_fields = ["name", "code", "slug"]
    inlines = [CollegeFeatureInline]


class TenantModelAdmin(admin.ModelAdmin):
    """Admin base for TenantModel subclasses.

    Rows are filtered by the model's default manager (D12). On platform hosts
    there is no college, so college-owned models are hidden entirely.
    """

    def _on_college_host(self, request) -> bool:
        return getattr(request, "college", None) is not None

    def has_module_permission(self, request):
        return self._on_college_host(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._on_college_host(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self._on_college_host(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self._on_college_host(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._on_college_host(request) and super().has_delete_permission(request, obj)
