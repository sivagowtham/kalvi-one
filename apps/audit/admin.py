from django.contrib import admin

from apps.tenancy.admin import TenantModelAdmin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(TenantModelAdmin):
    """Read-only. Nobody, including the principal, can add, edit or delete audit rows."""

    list_display = ["created_at", "actor_label", "action", "content_type", "object_repr"]
    list_filter = ["action", "content_type"]
    search_fields = ["actor_label", "object_repr", "object_id", "request_id"]
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
