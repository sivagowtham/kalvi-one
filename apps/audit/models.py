from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.tenancy.context import require_current_college
from apps.tenancy.models import College


class ImmutableError(RuntimeError):
    """Audit rows can never be changed or deleted."""


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableError("Audit events cannot be updated.")

    def delete(self):
        raise ImmutableError("Audit events cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise ImmutableError("Audit events cannot be updated.")


class AuditEventManager(models.Manager.from_queryset(AuditEventQuerySet)):
    """Only the current college's events; fails closed like TenantManager (D4)."""

    def get_queryset(self):
        return super().get_queryset().filter(college=require_current_college())


class AuditEvent(models.Model):
    """One append-only record of who changed what and when (D8)."""

    class Action(models.TextChoices):
        CREATE = "create", "Created"
        UPDATE = "update", "Updated"
        DELETE = "delete", "Deleted"
        LOGIN = "login", "Logged in"
        LOGIN_FAILED = "login_failed", "Login failed"
        LOGOUT = "logout", "Logged out"
        PERMISSION_DENIED = "permission_denied", "Permission denied"
        VIEW_SENSITIVE = "view_sensitive", "Viewed a sensitive field"
        RESET_REQUESTED = "reset_requested", "Asked for a password reset link"
        PASSWORD_SET = "password_set", "Set a password from an emailed link"

    # Null only for platform-level events (platform staff logins, platform admin work).
    college = models.ForeignKey(
        College, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,  # keep history even if the user row goes
    )
    actor_label = models.CharField(max_length=150, help_text="Username at the time.")
    action = models.CharField(max_length=20, choices=Action.choices)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(default=dict, blank=True, help_text="{field: [before, after]}")
    extra = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditEventManager()
    all_colleges = models.Manager.from_queryset(AuditEventQuerySet)()

    class Meta:
        ordering = ["-created_at", "-id"]
        base_manager_name = "all_colleges"
        indexes = [
            models.Index(fields=["college", "content_type", "object_id"]),
            models.Index(fields=["college", "actor"]),
        ]

    def __str__(self) -> str:
        target = f" {self.object_repr}" if self.object_repr else ""
        return f"{self.actor_label} {self.get_action_display().lower()}{target}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableError("Audit events cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError("Audit events cannot be deleted.")
