"""Deliberate bulk changes that still write one audit record per row."""

from django.db import transaction


def audited_update(queryset, **values) -> int:
    """Update every row in ``queryset`` through save(), so each change is audited."""
    count = 0
    with transaction.atomic():
        for obj in queryset:
            for name, value in values.items():
                setattr(obj, name, value)
            obj.save()
            count += 1
    return count
