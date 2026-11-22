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
