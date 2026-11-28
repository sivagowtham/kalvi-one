"""Filling in the calendar, day orders and the timetable day of a date (D35)."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction

from apps.tenancy.context import college_context
from apps.timetable import workdays
from apps.timetable.models import CalendarDay

pytestmark = pytest.mark.django_db

MON = dt.date(2026, 12, 7)  # a Monday


def _days(start, end):
    return {d.date: d for d in CalendarDay.objects.filter(date__range=(start, end))}


def test_weekday_cycle_follows_the_weekday(college_a):
    with college_context(college_a):
        result = workdays.fill(MON, MON + dt.timedelta(days=13), {MON + dt.timedelta(1): "Fake"})
        days = _days(MON, MON + dt.timedelta(days=13))
    assert result.created == 14
    assert result.holidays == 3  # two Sundays and the Tuesday holiday
    assert days[MON].day == 1
    assert not days[MON + dt.timedelta(1)].is_working
    assert days[MON + dt.timedelta(1)].note == "Fake"
    assert days[MON + dt.timedelta(5)].day == 6  # Saturday works by default
    assert not days[MON + dt.timedelta(6)].is_working


def test_a_five_day_week_is_a_setting(college_a):
    college_a.config = {"timetable": {"working_weekdays": [1, 2, 3, 4, 5]}}
    college_a.save()
    with college_context(college_a):
        workdays.fill(MON, MON + dt.timedelta(6))
        assert not CalendarDay.objects.get(date=MON + dt.timedelta(5)).is_working


def test_day_orders_skip_holidays_and_carry_on(college_a):
    college_a.config = {"timetable": {"cycle": "day_order", "day_order_count": 6}}
    college_a.save()
    with college_context(college_a):
        workdays.fill(MON, MON + dt.timedelta(6), {MON + dt.timedelta(2): "Fake holiday"})
        days = _days(MON, MON + dt.timedelta(6))
        orders = [days[MON + dt.timedelta(i)].day for i in range(7)]
        assert orders == [1, 2, None, 3, 4, 5, None]
        # The next week carries on from Day 5.
        workdays.fill(MON + dt.timedelta(7), MON + dt.timedelta(8))
        assert CalendarDay.objects.get(date=MON + dt.timedelta(7)).day == 6
        assert CalendarDay.objects.get(date=MON + dt.timedelta(8)).day == 1


def test_a_new_holiday_moves_later_day_orders_on(college_a):
    college_a.config = {"timetable": {"cycle": "day_order"}}
    college_a.save()
    with college_context(college_a):
        workdays.fill(MON, MON + dt.timedelta(5))
        tuesday = CalendarDay.objects.get(date=MON + dt.timedelta(1))
        tuesday.is_working = False
        tuesday.day = None
        tuesday.note = "Rain holiday"
        tuesday.save()
        moved = workdays.renumber_from(tuesday.date)
        orders = [d.day for d in CalendarDay.objects.filter(date__gte=MON).order_by("date")]
    assert orders == [1, None, 2, 3, 4, 5]
    assert moved == 4


def test_existing_dates_are_kept(college_a):
    with college_context(college_a):
        CalendarDay.objects.create(date=MON + dt.timedelta(5), is_working=True, day=1, note="Sat")
        result = workdays.fill(MON, MON + dt.timedelta(6))
        assert result.kept == 1
        assert CalendarDay.objects.get(date=MON + dt.timedelta(5)).day == 1


def test_working_days_need_a_day_and_holidays_have_none(college_a):
    with college_context(college_a), transaction.atomic(), pytest.raises(IntegrityError):
        CalendarDay.objects.create(date=MON, is_working=True)


def test_day_for_falls_back_to_the_weekday(college_a):
    with college_context(college_a):
        assert workdays.day_for(MON).day == 1
        assert not workdays.day_for(MON + dt.timedelta(6)).is_working
    college_a.config = {"timetable": {"cycle": "day_order"}}
    college_a.save()
    with college_context(college_a):
        assert workdays.day_for(MON) is None


def test_parse_holidays():
    parsed = workdays.parse_holidays("2027-01-15 Pongal\n\n16/01/2027 Thiruvalluvar Day")
    assert parsed == {dt.date(2027, 1, 15): "Pongal", dt.date(2027, 1, 16): "Thiruvalluvar Day"}
    with pytest.raises(ValueError, match="Line 1"):
        workdays.parse_holidays("Pongal 15 Jan")
