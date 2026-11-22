"""Who is acting, for the audit log. Set per request by AuditContextMiddleware."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditContext:
    actor_id: int | None = None
    actor_label: str = "system"
    request_id: str = ""
    ip_address: str | None = None
    user_agent: str = ""


# AuditContext is a frozen dataclass, so sharing one default instance is safe.
_audit_context: ContextVar[AuditContext] = ContextVar(
    "audit_context",
    default=AuditContext(),  # noqa: B039
)


def get_audit_context() -> AuditContext:
    return _audit_context.get()


@contextmanager
def audit_context(**values) -> Iterator[AuditContext]:
    """Set who is acting for a block of code, e.g. a management command."""
    ctx = AuditContext(**values)
    token = _audit_context.set(ctx)
    try:
        yield ctx
    finally:
        _audit_context.reset(token)


class AuditContextMiddleware:
    """Record the user, request ID, IP and user agent for every change in this request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        authenticated = user is not None and user.is_authenticated
        request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex
        request.request_id = request_id
        with audit_context(
            actor_id=user.pk if authenticated else None,
            actor_label=user.get_username() if authenticated else "anonymous",
            request_id=request_id,
            ip_address=request.META.get("REMOTE_ADDR") or None,
            user_agent=request.headers.get("User-Agent", "")[:300],
        ):
            response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
