"""Per-college settings for the timetable, stored in College.config["timetable"] (D13, D35).

Every key has a default here, so a college needs config only where it differs. The values
come from the college's answers to the onboarding questionnaire.
"""

from __future__ import annotations

from typing import Any

WEEKDAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

DEFAULTS: dict[str, Any] = {
    # "weekday": the timetable repeats every week, Monday to Saturday.
    # "day_order": the timetable repeats over numbered days (Day 1 to Day 6) that move on
    # only on working days, so a holiday does not lose a day's classes.
    "cycle": "weekday",
    # Days in a day-order cycle.
    "day_order_count": 6,
    # Working weekdays as ISO numbers (1 is Monday). Remove 6 for a five-day week.
    "working_weekdays": [1, 2, 3, 4, 5, 6],
    # Label for a day order, with {n} for its number.
    "day_order_label": "Day {n}",
}

CYCLES = {"weekday", "day_order"}


def setting(college, key: str) -> Any:
    return (college.config or {}).get("timetable", {}).get(key, DEFAULTS[key])


def uses_day_order(college) -> bool:
    return setting(college, "cycle") == "day_order"


def timetable_days(college) -> list[tuple[int, str]]:
    """The days a timetable is planned for, as (number, label)."""
    if uses_day_order(college):
        label = setting(college, "day_order_label")
        return [(n, label.format(n=n)) for n in range(1, setting(college, "day_order_count") + 1)]
    return [(n, WEEKDAY_NAMES[n]) for n in sorted(setting(college, "working_weekdays"))]


def day_label(college, number: int | None) -> str:
    return dict(timetable_days(college)).get(number, "") if number else ""
