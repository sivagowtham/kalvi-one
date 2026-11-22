"""Writes AuditEvent rows. The only place that creates them."""

from __future__ import annotations

import json

from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder

from apps.tenancy.context import get_current_college

from .context import get_audit_context
from .models import AuditEvent

MASKED = "***"


def _json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def snapshot(instance) -> dict:
    """Field values of ``instance`` as JSON-safe data, keyed by attribute name."""
    exclude = set(getattr(instance, "audit_exclude", ()))
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in exclude or field.attname in exclude:
            continue
        data[field.attname] = _json_safe(field.value_from_object(instance))
    return data


def diff(instance, before: dict | None, after: dict) -> dict:
    masked = set(getattr(instance, "audit_mask", ()))
    changes = {}
    for key, new in after.items():
        old = None if before is None else before.get(key)
        if before is not None and old == new:
            continue
        if before is None and new in (None, "", [], {}):
            continue
        changes[key] = [MASKED, MASKED] if key in masked else [old, new]
    return changes


def college_id_for(instance) -> int | None:
    from apps.tenancy.models import College

    if isinstance(instance, College):
        return instance.pk
    college_id = getattr(instance, "college_id", None)
    if college_id is not None:
        return college_id
    current = get_current_college()
    return current.pk if current is not None else None


def record(action, *, instance=None, changes=None, college_id=None, actor=None, extra=None):
    ctx = get_audit_context()
    if college_id is None and instance is not None:
        college_id = college_id_for(instance)
    if college_id is None and instance is None:
        current = get_current_college()
        college_id = current.pk if current is not None else None
    event = AuditEvent(
        college_id=college_id,
        actor_id=actor.pk if actor is not None else ctx.actor_id,
        actor_label=actor.get_username() if actor is not None else ctx.actor_label,
        action=action,
        changes=changes or {},
        extra=extra or {},
        request_id=ctx.request_id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
    )
    if instance is not None:
        event.content_type = ContentType.objects.get_for_model(instance)
        event.object_id = str(instance.pk)
        event.object_repr = str(instance)[:200]
    event.save()
    return event
