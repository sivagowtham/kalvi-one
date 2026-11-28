"""The working calendar: filling in a term's dates and keeping day orders in step (D35)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db import transaction

from apps.tenancy.context import require_current_college

from . import config
from .models import CalendarDay


@dataclass
class FillResult:
    created: int
    working: int
    holidays: int
    kept: int


def _next_order(college, before: dt.date) -> int:
    """The day order that follows the last working day before ``before``."""
    last = CalendarDay.objects.filter(date__lt=before, is_working=True).order_by("-date").first()
    if last is None:
        return 1
    return last.day % config.setting(college, "day_order_count") + 1


@transaction.atomic
def fill(start: dt.date, end: dt.date, holidays: dict[dt.date, str] | None = None) -> FillResult:
    """Add a calendar row for every date from ``start`` to ``end`` that has none yet.

    Weekdays the college does not work and the given holidays are holidays. In a weekday cycle a
    working day follows its own weekday; in a day-order cycle day orders run on from the last
    working day before ``start``. Dates that already have a row are kept as they are.
    """
    college = require_current_college()
    holidays = holidays or {}
    working_weekdays = set(config.setting(college, "working_weekdays"))
    day_order = config.uses_day_order(college)
    count = config.setting(college, "day_order_count")
    existing = {d.date: d for d in CalendarDay.objects.filter(date__range=(start, end))}
    order = _next_order(college, start)
    result = FillResult(0, 0, 0, 0)
    date = start
    while date <= end:
        row = existing.get(date)
        if row is not None:
            result.kept += 1
            if row.is_working and day_order:
                order = row.day % count + 1
        else:
            working = date.isoweekday() in working_weekdays and date not in holidays
            if working:
                day = order if day_order else date.isoweekday()
                CalendarDay.objects.create(date=date, is_working=True, day=day)
                order = order % count + 1
                result.working += 1
            else:
                CalendarDay.objects.create(
                    date=date, is_working=False, note=holidays.get(date, "")[:200]
                )
                result.holidays += 1
            result.created += 1
        date += dt.timedelta(days=1)
    return result


@transaction.atomic
def renumber_from(start: dt.date) -> int:
    """Run day orders on again from ``start``, after a holiday was added or removed.

    Only for a day-order cycle. Returns how many dates changed their day order.
    """
    college = require_current_college()
    if not config.uses_day_order(college):
        return 0
    count = config.setting(college, "day_order_count")
    order = _next_order(college, start)
    changed = 0
    for row in CalendarDay.objects.filter(date__gte=start, is_working=True).order_by("date"):
        if row.day != order:
            row.day = order
            row.save(update_fields=["day"])
            changed += 1
        order = order % count + 1
    return changed


def day_for(date: dt.date) -> CalendarDay | None:
    """The calendar row for ``date``, or a working day worked out from the weekday.

    A weekday-cycle college that has not filled in its calendar still gets today's timetable.
    A day-order college needs its calendar, so an unknown date gives None.
    """
    row = CalendarDay.objects.filter(date=date).first()
    if row is not None:
        return row
    college = require_current_college()
    if config.uses_day_order(college):
        return None
    working = date.isoweekday() in set(config.setting(college, "working_weekdays"))
    return CalendarDay(
        college=college,
        date=date,
        is_working=working,
        day=date.isoweekday() if working else None,
    )


def parse_holidays(text: str) -> dict[dt.date, str]:
    """Lines like '2027-01-15 Pongal' or '15/01/2027 Pongal' into a date-to-note map."""
    holidays = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        first, _, note = line.partition(" ")
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                holidays[dt.datetime.strptime(first, fmt).date()] = note.strip()
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Line {number}: '{first}' is not a date like 2027-01-15.")
    return holidays
