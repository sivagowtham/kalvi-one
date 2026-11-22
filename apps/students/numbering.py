"""Roll, admission and application numbers from per-college patterns (D20, D21)."""

from __future__ import annotations

import re

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from . import config
from .models import NumberCounter

_SEQ = re.compile(r"\{seq(:[^}]*)?\}")


def _clean(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", code).upper()


def _split(pattern: str, **values) -> tuple[str, str, str]:
    """(prefix, seq format, suffix), with everything but {seq} filled in."""
    match = _SEQ.search(pattern)
    if match is None:
        raise ImproperlyConfigured(f"Number pattern {pattern!r} has no {{seq}}.")
    try:
        prefix = pattern[: match.start()].format(**values)
        suffix = pattern[match.end() :].format(**values)
    except KeyError as error:
        raise ImproperlyConfigured(f"Unknown placeholder {error} in {pattern!r}.") from None
    return prefix, "{0" + (match.group(1) or "") + "}", suffix


def next_number(college, pattern_key: str, taken, **values) -> str:
    """The next free number for the college's pattern. ``taken(number)`` says if it is used.

    The counter row is locked for the rest of the transaction, so two people enrolling at
    the same time never get the same number.
    """
    return next_number_for_pattern(
        config.setting(college, pattern_key), pattern_key, taken, **values
    )


def next_number_for_pattern(pattern: str, pattern_key: str, taken, **values) -> str:
    """Like next_number, for a pattern another module keeps in its own config."""
    prefix, seq_format, suffix = _split(pattern, **values)
    key = f"{pattern_key}:{prefix}|{suffix}"[:50]
    with transaction.atomic():
        counter, _ = NumberCounter.objects.select_for_update().get_or_create(key=key)
        while True:
            counter.last_value += 1
            number = f"{prefix}{seq_format.format(counter.last_value)}{suffix}"
            if not taken(number):
                break
        counter.save()
    return number


def roll_number(batch) -> str:
    from .models import Student

    programme = batch.programme
    return next_number(
        batch.college,
        "roll_number_pattern",
        lambda n: Student.objects.filter(roll_number=n).exists(),
        yy=f"{batch.admission_year.start_date.year % 100:02d}",
        dept=_clean(programme.department.code),
        prog=_clean(programme.code),
    )


def admission_number(college, year) -> str:
    from .models import Student

    return next_number(
        college,
        "admission_number_pattern",
        lambda n: Student.objects.filter(admission_number=n).exists(),
        yy=f"{year.start_date.year % 100:02d}",
    )
