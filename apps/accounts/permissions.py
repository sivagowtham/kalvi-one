"""The permission registry and checks (D7). Access is denied unless a role grants it.

Each app declares its permissions in a ``grants.py`` module, loaded from its
AppConfig.ready(). A permission code is either a Django model permission
("academics.change_department") so Django admin works unchanged, or a custom
action ("exams.publish_results").
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps

import django.dispatch
from django.core.exceptions import ImproperlyConfigured, PermissionDenied

from apps.tenancy.context import get_current_college

from .roles import Role

# Sent whenever a check denies access, so the audit log (PR 4) can record it.
permission_denied = django.dispatch.Signal()


class UnknownPermission(LookupError):
    pass


@dataclass(frozen=True)
class Permission:
    code: str
    roles: frozenset[Role]
    description: str


_registry: dict[str, Permission] = {}


def register(code: str, roles: Iterable[Role], description: str) -> None:
    if code in _registry:
        raise ImproperlyConfigured(f"Permission {code!r} is registered twice.")
    _registry[code] = Permission(code, frozenset(roles), description)


def registered() -> dict[str, Permission]:
    return dict(_registry)


def roles_for(user, college) -> frozenset[Role]:
    """The roles ``user`` holds in ``college``, cached on the user object for the request."""
    cache = user.__dict__.setdefault("_kalvi_roles", {})
    if college.pk not in cache:
        from .models import RoleAssignment

        cache[college.pk] = frozenset(
            Role(value)
            for value in RoleAssignment.all_colleges.filter(user=user, college=college).values_list(
                "role", flat=True
            )
        )
    return cache[college.pk]


def has_perm(user, code: str, obj=None) -> bool:
    """True when ``user`` may do ``code`` in the current college. Unknown codes raise."""
    try:
        permission = _registry[code]
    except KeyError:
        raise UnknownPermission(code) from None
    return _check(user, permission)


def has_perm_or_deny(user, code: str) -> bool:
    """Like has_perm, but an unknown code is simply denied. Used by Django's auth API."""
    permission = _registry.get(code)
    return permission is not None and _check(user, permission)


def _check(user, permission: Permission) -> bool:
    if user is None or not user.is_authenticated or not user.is_active:
        return False
    college = get_current_college()
    if user.college_id is None:
        # Platform staff: only superusers, and only on platform hosts.
        return college is None and user.is_superuser
    if college is None or user.college_id != college.pk:
        return False
    return bool(roles_for(user, college) & permission.roles)


def require_perm(code: str) -> Callable:
    """View decorator: login required, then ``code`` required; otherwise 403."""
    if code not in _registry:
        raise ImproperlyConfigured(f"require_perm({code!r}): permission is not registered.")

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            if not has_perm(request.user, code):
                permission_denied.send(sender=None, request=request, code=code)
                raise PermissionDenied
            return view(request, *args, **kwargs)

        wrapped.kalvi_permission = code
        return wrapped

    return decorator


def public(view: Callable) -> Callable:
    """Mark a view as deliberately open to everyone. The default-deny test requires a mark."""
    view.kalvi_public = True
    return view
