from django.contrib import admin

from apps.tenancy.admin import TenantModelAdmin

from .models import Widget

admin.site.register(Widget, TenantModelAdmin)
