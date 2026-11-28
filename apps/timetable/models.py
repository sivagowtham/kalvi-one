"""Timetable: bell schedules, the working calendar, who teaches what, and the weekly plan.

Timetable depends on academics and students, never the reverse (D34). Attendance builds on it.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

from apps.academics.models import Course, Programme, Semester
from apps.audit.mixins import Audited
from apps.students.models import Section, Student
from apps.tenancy.models import TenantModel

from . import config


class BellSchedule(Audited, TenantModel):
    """A set of period timings. Most colleges have one; shift colleges have one per shift."""

    name = models.CharField(max_length=60, help_text="e.g. Regular, Shift I, Shift II")
    is_default = models.BooleanField(
        default=False,
        help_text="Used by every programme that is not given another schedule.",
    )

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(fields=["college", "name"], name="unique_bell_schedule_name"),
            models.UniqueConstraint(
                fields=["college"],
                condition=models.Q(is_default=True),
                name="one_default_bell_schedule",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PeriodSlot(Audited, TenantModel):
    """One teaching period of a bell schedule, such as period 1 from 9:00 to 9:50."""

    schedule = models.ForeignKey(BellSchedule, on_delete=models.PROTECT, related_name="periods")
    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(16)]
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["schedule", "number"]
        constraints = [
            models.UniqueConstraint(fields=["schedule", "number"], name="unique_period_number"),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="period_ends_after_it_starts",
            ),
            models.CheckConstraint(
                condition=models.Q(number__gte=1, number__lte=16), name="period_number_range"
            ),
        ]

    def __str__(self) -> str:
        return f"Period {self.number} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"

    def overlaps(self, other: PeriodSlot) -> bool:
        return self.start_time < other.end_time and other.start_time < self.end_time

    def clean(self):
        super().clean()
        if not (self.schedule_id and self.start_time and self.end_time):
            return
        if self.end_time <= self.start_time:
            raise ValidationError({"end_time": "A period must end after it starts."})
        others = PeriodSlot.objects.filter(schedule_id=self.schedule_id).exclude(pk=self.pk)
        for other in others:
            if self.overlaps(other):
                raise ValidationError(f"This overlaps period {other.number} of the schedule.")


class ScheduleProgramme(Audited, TenantModel):
    """A programme that follows a bell schedule other than the default one."""

    schedule = models.ForeignKey(BellSchedule, on_delete=models.PROTECT, related_name="programmes")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["schedule", "programme"]
        verbose_name = "programme on this schedule"
        constraints = [
            models.UniqueConstraint(fields=["programme"], name="one_bell_schedule_per_programme"),
        ]

    def __str__(self) -> str:
        return f"{self.programme} on {self.schedule}"


def schedule_for(programme: Programme) -> BellSchedule | None:
    """The bell schedule a programme follows: its own, or the college's default."""
    own = ScheduleProgramme.objects.filter(programme=programme).select_related("schedule").first()
    if own:
        return own.schedule
    return BellSchedule.objects.filter(is_default=True).first()


class CalendarDay(Audited, TenantModel):
    """One date in the college calendar: a working day and the timetable day it follows, or not.

    In a weekday cycle ``day`` is the weekday whose timetable runs (usually the date's own;
    a Saturday may follow Monday's). In a day-order cycle it is the day order (D35).
    """

    date = models.DateField()
    is_working = models.BooleanField(default=True)
    day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="The timetable day this date follows. Empty on holidays.",
    )
    note = models.CharField(
        max_length=200, blank=True, help_text="e.g. Pongal, Sports day, Saturday follows Monday"
    )

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["college", "date"], name="one_calendar_row_per_date"),
            models.CheckConstraint(
                condition=(
                    models.Q(is_working=True, day__isnull=False)
                    | models.Q(is_working=False, day__isnull=True)
                ),
                name="working_days_follow_a_timetable_day",
            ),
        ]

    def __str__(self) -> str:
        if not self.is_working:
            return f"{self.date:%d %b %Y}: holiday{f' ({self.note})' if self.note else ''}"
        return f"{self.date:%d %b %Y}: {self.day_label}"

    @property
    def day_label(self) -> str:
        return config.day_label(self.college, self.day)

    def clean(self):
        super().clean()
        if self.is_working and not self.day:
            raise ValidationError({"day": "Choose which timetable day this working day follows."})
        if not self.is_working:
            self.day = None
        if self.day and self.college_id:
            valid = dict(config.timetable_days(self.college))
            if self.day not in valid:
                raise ValidationError({"day": "This is not one of the college's timetable days."})


class LabGroup(Audited, TenantModel):
    """Part of a section that has a lab or tutorial on its own, such as B1 or B2, for one term."""

    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="lab_groups")
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="lab_groups")
    name = models.CharField(max_length=20, help_text="e.g. B1")

    class Meta:
        ordering = ["semester", "section", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "semester", "name"], name="unique_lab_group_name"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.section} {self.name}"

    @property
    def scope_department_id(self) -> int | None:
        return self.section.scope_department_id if self.section_id else None


class LabGroupMember(Audited, TenantModel):
    group = models.ForeignKey(LabGroup, on_delete=models.CASCADE, related_name="members")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="lab_groups")

    class Meta:
        ordering = ["group", "student__roll_number"]
        constraints = [
            models.UniqueConstraint(fields=["group", "student"], name="unique_lab_group_member"),
        ]

    def __str__(self) -> str:
        return f"{self.student.roll_number} in {self.group}"

    @property
    def scope_department_id(self) -> int | None:
        return self.group.scope_department_id if self.group_id else None

    def clean(self):
        super().clean()
        if not (self.group_id and self.student_id):
            return
        if self.student.batch_id != self.group.section.batch_id:
            raise ValidationError({"student": "The student is not in this section's batch."})
        other = (
            LabGroupMember.objects.filter(
                student_id=self.student_id,
                group__section_id=self.group.section_id,
                group__semester_id=self.group.semester_id,
            )
            .exclude(pk=self.pk)
            .select_related("group")
            .first()
        )
        if other:
            raise ValidationError({"student": f"The student is already in {other.group.name}."})


class Allocation(Audited, TenantModel):
    """A course taught to a section, or to one lab group of it, in one term (D36)."""

    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="allocations")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="allocations")
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="allocations")
    lab_group = models.ForeignKey(
        LabGroup,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="allocations",
        help_text="Only for a lab or tutorial taught to part of the section.",
    )
    hours_per_week = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(40)],
        help_text="Periods a week (or a cycle), for the timetable generator.",
    )
    block_length = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Periods taken together, e.g. 3 for a lab.",
    )

    class Meta:
        ordering = ["semester", "section", "course__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["semester", "course", "section", "lab_group"],
                name="unique_allocation",
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        who = self.lab_group.name if self.lab_group_id else ""
        return f"{self.course.code} · {self.section}{f' {who}' if who else ''}"

    @property
    def scope_department_id(self) -> int | None:
        return self.section.scope_department_id if self.section_id else None

    def teacher_ids(self) -> set[int]:
        return set(self.teachers.values_list("teacher_id", flat=True))

    def clean(self):
        super().clean()
        if (
            self.course_id
            and self.section_id
            and self.course.programme_id != self.section.batch.programme_id
        ):
            raise ValidationError(
                {"course": "The course belongs to another programme than the section."}
            )
        if self.lab_group_id and (
            self.lab_group.section_id != self.section_id
            or self.lab_group.semester_id != self.semester_id
        ):
            raise ValidationError(
                {"lab_group": "The lab group must be of this section and this term."}
            )


class AllocationTeacher(Audited, TenantModel):
    """A teacher of an allocation. Labs often have two."""

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name="teachers")
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="allocations"
    )

    class Meta:
        ordering = ["allocation", "teacher__full_name"]
        verbose_name = "teacher"
        constraints = [
            models.UniqueConstraint(
                fields=["allocation", "teacher"], name="unique_allocation_teacher"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.teacher.get_full_name() or self.teacher.username} for {self.allocation}"

    @property
    def scope_department_id(self) -> int | None:
        return self.allocation.scope_department_id if self.allocation_id else None

    def clean(self):
        super().clean()
        if not (self.teacher_id and self.allocation_id):
            return
        if self.teacher.college_id != self.allocation.college_id or not self.teacher.is_active:
            raise ValidationError({"teacher": "Choose an active staff member of this college."})
        for entry in self.allocation.entries.select_related("period"):
            clash = entry.find_clashes(extra_teacher_ids={self.teacher_id}, only="teacher")
            if clash:
                raise ValidationError({"teacher": clash[0]})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.allocation_id:
                _lock_term(self.allocation.semester_id)
            self.clean()
            super().save(*args, **kwargs)


class AllocationStudent(Audited, TenantModel):
    """A student on an elective's roster. An allocation with none uses its section or group."""

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name="roster")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="electives")

    class Meta:
        ordering = ["allocation", "student__roll_number"]
        verbose_name = "student on the roster"
        verbose_name_plural = "roster (electives only)"
        constraints = [
            models.UniqueConstraint(
                fields=["allocation", "student"], name="unique_allocation_student"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student.roll_number} in {self.allocation}"

    @property
    def scope_department_id(self) -> int | None:
        return self.allocation.scope_department_id if self.allocation_id else None

    def clean(self):
        super().clean()
        if (
            self.allocation_id
            and self.student_id
            and self.student.batch.programme_id != self.allocation.course.programme_id
        ):
            raise ValidationError({"student": "The student is not in the course's programme."})


def _lock_term(semester_id: int) -> None:
    """Serialise timetable writes for a term, so two people cannot book one slot at once."""
    list(Semester.objects.select_for_update().filter(pk=semester_id).values_list("pk"))


class TimetableEntry(Audited, TenantModel):
    """One period of the weekly (or day-order) plan: an allocation on a day, in a period.

    Clashes (a section, lab group, teacher or room in two places at once) are refused on every
    save, comparing period times, so programmes on different bell schedules are checked too.
    """

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name="entries")
    day = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Weekday (1 is Monday) or day order, as the college's cycle says.",
    )
    period = models.ForeignKey(PeriodSlot, on_delete=models.PROTECT, related_name="entries")
    room = models.CharField(max_length=40, blank=True, help_text="e.g. CS-201 or Lab 3")

    class Meta:
        ordering = ["day", "period__start_time"]
        verbose_name = "timetable entry"
        verbose_name_plural = "timetable entries"
        constraints = [
            models.UniqueConstraint(
                fields=["allocation", "day", "period"], name="unique_timetable_entry"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day_label} period {self.period.number}: {self.allocation}"

    @property
    def day_label(self) -> str:
        return config.day_label(self.college, self.day)

    @property
    def scope_department_id(self) -> int | None:
        return self.allocation.scope_department_id if self.allocation_id else None

    def find_clashes(self, *, extra_teacher_ids=frozenset(), only=None) -> list[str]:
        """Plain-word clashes with other entries of the same term, day and time."""
        allocation = self.allocation
        teachers = allocation.teacher_ids() | set(extra_teacher_ids)
        room = self.room.strip().casefold()
        others = (
            TimetableEntry.objects.filter(
                allocation__semester_id=allocation.semester_id, day=self.day
            )
            .exclude(pk=self.pk)
            .select_related("period", "allocation__course", "allocation__section__batch")
            .select_related("allocation__lab_group")
            .prefetch_related("allocation__teachers")
        )
        found = []
        for other in others:
            if not self.period.overlaps(other.period):
                continue
            theirs = other.allocation
            what = f"{theirs} in period {other.period.number}"
            same_group = (
                theirs.lab_group_id is None
                or allocation.lab_group_id is None
                or theirs.lab_group_id == allocation.lab_group_id
            )
            same_section = theirs.section_id == allocation.section_id
            if only in (None, "section") and same_section and same_group:
                found.append(f"The section already has {what}.")
            shared = teachers & {t.teacher_id for t in theirs.teachers.all()}
            if only in (None, "teacher") and shared:
                found.append(f"A teacher of this class already has {what}.")
            if only in (None, "room") and room and other.room.strip().casefold() == room:
                found.append(f"Room {self.room} is already taken by {what}.")
        return found

    def clean(self):
        super().clean()
        if not (self.allocation_id and self.period_id and self.day):
            return
        errors = {}
        if self.day not in dict(config.timetable_days(self.allocation.college)):
            errors["day"] = "This is not one of the college's timetable days."
        schedule = schedule_for(self.allocation.section.batch.programme)
        if schedule is not None and self.period.schedule_id != schedule.pk:
            errors["period"] = f"This programme follows the {schedule} bell schedule."
        if errors:
            raise ValidationError(errors)
        clashes = self.find_clashes()
        if clashes:
            raise ValidationError(clashes)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            _lock_term(self.allocation.semester_id)
            self.clean()
            super().save(*args, **kwargs)
