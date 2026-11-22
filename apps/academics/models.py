"""Minimal academic core (foundation only): no marks, attendance or fees."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.audit.mixins import Audited
from apps.tenancy.models import TenantModel


class Department(Audited, TenantModel):
    code = models.CharField(max_length=20, help_text="e.g. CSE")
    name = models.CharField(max_length=200, help_text="e.g. Computer Science and Engineering")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["college", "code"], name="unique_department_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    @property
    def scope_department_id(self) -> int | None:
        return self.pk


class Programme(Audited, TenantModel):
    """A degree programme, e.g. B.E. Computer Science and Engineering."""

    class Level(models.TextChoices):
        UG = "ug", "Undergraduate"
        PG = "pg", "Postgraduate"
        DIPLOMA = "diploma", "Diploma"
        DOCTORAL = "doctoral", "Doctoral"

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    code = models.CharField(max_length=30, help_text="e.g. BE-CSE")
    name = models.CharField(max_length=200)
    level = models.CharField(max_length=10, choices=Level.choices)
    duration_years = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    total_semesters = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    # Plain text for now (plan question 6), e.g. "R2021". May become its own model later.
    regulation = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["college", "code"], name="unique_programme_code"),
            models.CheckConstraint(
                condition=models.Q(duration_years__gte=1, duration_years__lte=6),
                name="programme_duration_range",
            ),
            models.CheckConstraint(
                condition=models.Q(total_semesters__gte=1, total_semesters__lte=12),
                name="programme_semesters_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def scope_department_id(self) -> int | None:
        return self.department_id


class Course(Audited, TenantModel):
    """A subject or paper taught in one semester of one programme, e.g. CS3401."""

    class CourseType(models.TextChoices):
        THEORY = "theory", "Theory"
        PRACTICAL = "practical", "Practical"
        THEORY_PRACTICAL = "theory_practical", "Theory with practical"
        PROJECT = "project", "Project"
        ELECTIVE = "elective", "Elective"

    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="courses")
    semester_number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    credits = models.DecimalField(
        max_digits=4, decimal_places=1, validators=[MinValueValidator(Decimal("0"))]
    )
    course_type = models.CharField(max_length=20, choices=CourseType.choices)

    class Meta:
        ordering = ["programme", "semester_number", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["college", "programme", "code"], name="unique_course_code_per_programme"
            ),
            models.CheckConstraint(condition=models.Q(credits__gte=0), name="course_credits_gte_0"),
            models.CheckConstraint(
                condition=models.Q(semester_number__gte=1), name="course_semester_gte_1"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"

    @property
    def scope_department_id(self) -> int | None:
        return self.programme.department_id if self.programme_id else None

    def clean(self) -> None:
        super().clean()
        if self.programme_id and self.semester_number > self.programme.total_semesters:
            raise ValidationError(
                {
                    "semester_number": f"{self.programme} has {self.programme.total_semesters} "
                    "semesters."
                }
            )

    def save(self, *args, **kwargs):
        if self.programme_id and self.semester_number > self.programme.total_semesters:
            raise ValidationError("Semester number is beyond the programme's last semester.")
        super().save(*args, **kwargs)


academic_year_label = RegexValidator(r"^\d{4}-\d{2}$", "Use the form 2026-27.")


class AcademicYear(Audited, TenantModel):
    """A college's academic year, normally June to May."""

    label = models.CharField(max_length=7, validators=[academic_year_label])
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["college", "label"], name="unique_academic_year"),
            models.UniqueConstraint(
                fields=["college"],
                condition=models.Q(is_current=True),
                name="one_current_academic_year",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="academic_year_ends_after_start",
            ),
        ]

    def __str__(self) -> str:
        return self.label


class Semester(Audited, TenantModel):
    """A term (odd or even) of an academic year (D9).

    In the odd term students study semesters 1, 3, 5 and 7; in the even term 2, 4, 6 and 8.
    """

    class Term(models.TextChoices):
        ODD = "odd", "Odd"
        EVEN = "even", "Even"

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="semesters"
    )
    term = models.CharField(max_length=4, choices=Term.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["academic_year", "start_date"]
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "term"], name="unique_term_per_year"),
            models.UniqueConstraint(
                fields=["college"],
                condition=models.Q(is_current=True),
                name="one_current_semester",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="semester_ends_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.academic_year} {self.get_term_display()} term"

    def semester_numbers(self, total_semesters: int) -> list[int]:
        """Which programme semesters run in this term, e.g. [1, 3, 5, 7] for odd."""
        first = 1 if self.term == self.Term.ODD else 2
        return list(range(first, total_semesters + 1, 2))

    def clean(self) -> None:
        super().clean()
        year = self.academic_year if self.academic_year_id else None
        if (
            year
            and self.start_date
            and self.end_date
            and (self.start_date < year.start_date or self.end_date > year.end_date)
        ):
            raise ValidationError("The term must fall inside its academic year.")
