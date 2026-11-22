"""The current college for this request, task or test.

Stored in a ContextVar so it is isolated per thread and per asyncio task.
TenantMiddleware sets it for web requests. Scripts, management commands and
tests set it with ``college_context``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import College

_current_college: ContextVar[College | None] = ContextVar("current_college", default=None)


class NoCollegeSelected(RuntimeError):
    """A college-scoped query or save ran with no current college (fail closed, D4)."""


class CrossCollegeError(ValueError):
    """An attempt to write or link data across two colleges."""


def get_current_college() -> College | None:
    return _current_college.get()


def require_current_college() -> College:
    college = _current_college.get()
    if college is None:
        raise NoCollegeSelected(
            "No current college. Use college_context(college), or the all_colleges manager "
            "for deliberate platform-wide work."
        )
    return college


@contextmanager
def college_context(college: College | None) -> Iterator[College | None]:
    """Run a block of code as ``college``. Nesting is allowed; the outer value is restored."""
    token = _current_college.set(college)
    try:
        yield college
    finally:
        _current_college.reset(token)
