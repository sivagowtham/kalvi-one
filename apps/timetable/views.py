"""Phone-first timetable pages: your own day, and a section's week (D36)."""

from __future__ import annotations

from collections import OrderedDict

from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.academics.models import Semester
from apps.accounts.permissions import require_perm
from apps.students.models import Section

from . import config, workdays
from .models import TimetableEntry

ENTRY_RELATED = [
    "period",
    "allocation__course",
    "allocation__section__batch__programme",
    "allocation__lab_group",
]


def _term(request):
    terms = Semester.objects.select_related("academic_year").order_by("-start_date")
    chosen = request.GET.get("term", "")
    if chosen.isdigit():
        found = terms.filter(pk=int(chosen)).first()
        if found:
            return found, terms
    return terms.filter(is_current=True).first() or terms.first(), terms


def _with_teachers(entries):
    entries = list(entries.prefetch_related("allocation__teachers__teacher"))
    for entry in entries:
        entry.teacher_names = ", ".join(
            t.teacher.get_full_name() or t.teacher.username for t in entry.allocation.teachers.all()
        )
    return entries


@require_perm("timetable.view")
def my_timetable(request):
    college = request.college
    term, terms = _term(request)
    days = config.timetable_days(college)
    today = timezone.localdate()
    calendar = workdays.day_for(today)
    today_day = calendar.day if calendar and calendar.is_working else None
    asked = request.GET.get("day", "")
    valid = dict(days)
    if asked.isdigit() and int(asked) in valid:
        day = int(asked)
    else:
        day = today_day or (days[0][0] if days else None)
    entries = []
    if term and day:
        entries = _with_teachers(
            TimetableEntry.objects.filter(
                allocation__semester=term, allocation__teachers__teacher=request.user, day=day
            )
            .select_related(*ENTRY_RELATED)
            .order_by("period__start_time")
        )
    return render(
        request,
        "timetable/my_timetable.html",
        {
            "college": college,
            "term": term,
            "terms": terms,
            "days": days,
            "day": day,
            "day_label": valid.get(day, ""),
            "today": today,
            "calendar": calendar,
            "today_day": today_day,
            "entries": entries,
        },
    )


@require_perm("timetable.view")
def section_list(request):
    term, terms = _term(request)
    sections = (
        Section.objects.filter(allocations__semester=term)
        .distinct()
        .select_related("batch__programme")
        .order_by("batch__programme__code", "batch__label", "name")
        if term
        else Section.objects.none()
    )
    return render(
        request,
        "timetable/section_list.html",
        {"college": request.college, "term": term, "terms": terms, "sections": sections},
    )


@require_perm("timetable.view")
def section_timetable(request, pk):
    college = request.college
    section = get_object_or_404(Section.objects.select_related("batch__programme"), pk=pk)
    term, terms = _term(request)
    by_day = OrderedDict((number, (label, [])) for number, label in config.timetable_days(college))
    if term:
        entries = _with_teachers(
            TimetableEntry.objects.filter(allocation__semester=term, allocation__section=section)
            .select_related(*ENTRY_RELATED)
            .order_by("day", "period__start_time", "allocation__lab_group__name")
        )
        for entry in entries:
            if entry.day in by_day:
                by_day[entry.day][1].append(entry)
    return render(
        request,
        "timetable/section_timetable.html",
        {
            "college": college,
            "section": section,
            "term": term,
            "terms": terms,
            "days": [(number, label, entries) for number, (label, entries) in by_day.items()],
        },
    )
