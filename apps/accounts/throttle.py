"""Pause logins after repeated wrong passwords (D23).

Failed logins are already in the audit log (D8), so the log is the counter: no cache or
extra table is needed, and the count is shared by every web process.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditEvent

# Set on a LOGIN_FAILED event that was refused without checking the password.
LOCKED_REASON = "too_many_attempts"


def client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR") or None


def is_locked(request, username: str) -> bool:
    """True when ``username`` has had too many wrong passwords from this IP address recently.

    Counts failures in the last LOGIN_LOCKOUT_MINUTES on this host's college, since the
    user's last successful login. Refused attempts (already locked) are not counted, so the
    pause ends on time.
    """
    limit = settings.LOGIN_FAILURE_LIMIT
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    college = getattr(request, "college", None)
    college_id = college.pk if college is not None else None
    # all_colleges on purpose: the platform host has no college, and we filter by hand.
    events = AuditEvent.all_colleges.filter(college_id=college_id, created_at__gte=window_start)
    last_success = (
        events.filter(action=AuditEvent.Action.LOGIN, actor_label=username)
        .values_list("created_at", flat=True)
        .first()
    )
    failures = events.filter(
        action=AuditEvent.Action.LOGIN_FAILED,
        extra__username=username,
        ip_address=client_ip(request),
    ).exclude(extra__has_key="reason")
    if last_success is not None:
        failures = failures.filter(created_at__gt=last_success)
    return failures.count() >= limit
