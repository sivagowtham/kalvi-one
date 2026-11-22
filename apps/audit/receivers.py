"""Signal handlers that feed the audit log (D8)."""

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.accounts.permissions import permission_denied

from . import recorder
from .mixins import Audited
from .models import AuditEvent

Action = AuditEvent.Action


@receiver(pre_save, dispatch_uid="audit_pre_save")
def remember_previous_state(sender, instance, raw=False, **kwargs):
    if raw or not isinstance(instance, Audited):
        return
    previous = None
    if instance.pk is not None:
        stored = type(instance)._base_manager.filter(pk=instance.pk).first()
        if stored is not None:
            previous = recorder.snapshot(stored)
    instance._audit_before = previous


@receiver(post_save, dispatch_uid="audit_post_save")
def record_save(sender, instance, created, raw=False, **kwargs):
    if raw or not isinstance(instance, Audited):
        return
    before = None if created else getattr(instance, "_audit_before", None)
    changes = recorder.diff(instance, before, recorder.snapshot(instance))
    instance._audit_before = None
    if not created and not changes:
        return  # nothing actually changed
    recorder.record(Action.CREATE if created else Action.UPDATE, instance=instance, changes=changes)


@receiver(post_delete, dispatch_uid="audit_post_delete")
def record_delete(sender, instance, **kwargs):
    if not isinstance(instance, Audited):
        return
    masked = set(instance.audit_mask)
    final = {
        key: [recorder.MASKED if key in masked else value, None]
        for key, value in recorder.snapshot(instance).items()
    }
    recorder.record(Action.DELETE, instance=instance, changes=final)


@receiver(user_logged_in, dispatch_uid="audit_login")
def record_login(sender, request, user, **kwargs):
    recorder.record(Action.LOGIN, instance=user, actor=user, college_id=user.college_id)


@receiver(user_logged_out, dispatch_uid="audit_logout")
def record_logout(sender, request, user, **kwargs):
    if user is not None:
        recorder.record(Action.LOGOUT, instance=user, actor=user, college_id=user.college_id)


@receiver(user_login_failed, dispatch_uid="audit_login_failed")
def record_login_failed(sender, credentials, request=None, **kwargs):
    # Django already removes the password from ``credentials``.
    recorder.record(Action.LOGIN_FAILED, extra={"username": credentials.get("username", "")})


@receiver(permission_denied, dispatch_uid="audit_permission_denied")
def record_permission_denied(sender, request, code, **kwargs):
    recorder.record(
        Action.PERMISSION_DENIED, extra={"permission": code, "path": request.path[:200]}
    )
