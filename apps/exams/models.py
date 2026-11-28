"""Exams and marks: assessment schemes, grade scales and pass rules (D50 to D52).

Exams depends on academics, students and (from step 2) timetable and attendance, never the
reverse. A scheme says how one kind of course is assessed under one regulation; once results
point at it, it is locked and changes are made on a copy, so old results never move (D51).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction

from apps.academics.models import Course
from apps.audit.mixins import Audited
from apps.tenancy.models import TenantModel

code_validator = RegexValidator(
    r"^[A-Z0-9][A-Z0-9_-]{0,29}$", "Use capital letters, digits, hyphens and underscores only."
)
ZERO = Decimal("0")
HUNDRED = Decimal("100")
percent_validators = [MinValueValidator(ZERO), MaxValueValidator(HUNDRED)]


class SchemeLocked(ValidationError):
    """Raised when something tries to change a scheme or scale that results already use."""


class LockableMixin(models.Model):
    """A row that freezes once in use. Saving a locked row, or its children, is refused."""

    is_locked = models.BooleanField(
        default=False,
        editable=False,
        help_text="Set when marks or results first use it. Make a copy to change it.",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self._refuse_if_locked()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._refuse_if_locked()
        return super().delete(*args, **kwargs)

    def _refuse_if_locked(self) -> None:
        if self.pk is None:
            return
        stored = type(self).all_colleges.filter(pk=self.pk).values_list("is_locked", flat=True)
        if stored.first():
            raise SchemeLocked(f"{self} is in use and locked. Make a copy to change it.")

    def lock(self) -> None:
        """Freeze this row. Called by the marks and results steps when they first use it."""
        if not self.is_locked:
            self.is_locked = True
            # The stored row is still unlocked, so this save passes and is audited (D8).
            super().save(update_fields=["is_locked"])


class GradeScale(Audited, LockableMixin, TenantModel):
    """A set of letter grades with grade points, e.g. Anna University R2021's O to RA."""

    code = models.CharField(max_length=30, validators=[code_validator], help_text="e.g. AU-R2021")
    name = models.CharField(max_length=200)
    fail_letter = models.CharField(
        max_length=5, default="RA", help_text="Printed when a student does not pass, e.g. RA or U."
    )
    absent_letter = models.CharField(
        max_length=5, default="AB", help_text="Printed when a student missed the end semester exam."
    )
    shortage_letter = models.CharField(
        max_length=5, default="SA", help_text="Printed for shortage of attendance."
    )
    withdrawal_letter = models.CharField(
        max_length=5, default="W", help_text="Printed when a student withdrew from the exam."
    )

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["college", "code"], name="unique_grade_scale_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    def bands_high_to_low(self) -> list["GradeBand"]:
        return list(self.bands.order_by("-min_percent"))

    def problems(self) -> list[str]:
        """What stops this scale from being used, in plain words. Empty when it is fine."""
        bands = self.bands_high_to_low()
        if not bands:
            return ["The scale has no grades."]
        found = []
        if bands[-1].min_percent != ZERO:
            found.append(
                f"The lowest grade starts at {bands[-1].min_percent}%, so lower marks get no "
                "grade. Start the lowest grade at 0."
            )
        letters = [band.letter for band in bands]
        if len(set(letters)) != len(letters):
            found.append("Two grades have the same letter.")
        return found

    def band_for(self, percent: Decimal) -> "GradeBand":
        for band in self.bands_high_to_low():
            if percent >= band.min_percent:
                return band
        raise ValidationError(f"{self} has no grade for {percent}%.")

    @transaction.atomic
    def copy(self, code: str) -> "GradeScale":
        """An unlocked copy with the same grades, for changes to a scale already in use."""
        bands = list(self.bands.all())
        new = GradeScale.objects.create(
            code=code,
            name=self.name,
            fail_letter=self.fail_letter,
            absent_letter=self.absent_letter,
            shortage_letter=self.shortage_letter,
            withdrawal_letter=self.withdrawal_letter,
        )
        for band in bands:
            GradeBand.objects.create(
                scale=new,
                letter=band.letter,
                description=band.description,
                grade_point=band.grade_point,
                min_percent=band.min_percent,
                is_pass=band.is_pass,
            )
        return new


class GradeBand(Audited, TenantModel):
    """One grade: from ``min_percent`` up to the next band's start."""

    scale = models.ForeignKey(GradeScale, on_delete=models.CASCADE, related_name="bands")
    letter = models.CharField(max_length=5, help_text="e.g. O, A+, B")
    description = models.CharField(max_length=50, blank=True, help_text="e.g. Outstanding")
    grade_point = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("10"))],
    )
    min_percent = models.DecimalField(
        "From (%)",
        max_digits=5,
        decimal_places=2,
        validators=percent_validators,
        help_text="The lowest total percentage that earns this grade.",
    )
    is_pass = models.BooleanField(
        default=True, help_text="Untick for the failing band, e.g. RA below 50%."
    )

    class Meta:
        ordering = ["scale", "-min_percent"]
        constraints = [
            models.UniqueConstraint(fields=["scale", "letter"], name="unique_grade_letter"),
            models.UniqueConstraint(fields=["scale", "min_percent"], name="unique_grade_start"),
            models.CheckConstraint(
                condition=models.Q(min_percent__gte=0) & models.Q(min_percent__lte=100),
                name="grade_band_percent_range",
            ),
            models.CheckConstraint(
                condition=models.Q(grade_point__gte=0) & models.Q(grade_point__lte=10),
                name="grade_band_point_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.letter} ({self.grade_point}) from {self.min_percent}%"

    def _refuse_if_scale_locked(self) -> None:
        if self.scale_id and GradeScale.all_colleges.filter(pk=self.scale_id, is_locked=True):
            raise SchemeLocked("This grade scale is in use and locked. Make a copy to change it.")

    def save(self, *args, **kwargs):
        self._refuse_if_scale_locked()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._refuse_if_scale_locked()
        return super().delete(*args, **kwargs)


class AssessmentScheme(Audited, LockableMixin, TenantModel):
    """How one kind of course is assessed under one regulation, and what counts as a pass.

    The pass rule lives here because each scheme has exactly one (D51).
    """

    code = models.CharField(
        max_length=30, validators=[code_validator], help_text="e.g. AU-R2021-THEORY"
    )
    name = models.CharField(max_length=200)
    regulation = models.CharField(
        max_length=30,
        blank=True,
        help_text="e.g. R2021, matching the batch's regulation. Blank applies to any regulation.",
    )
    course_type = models.CharField(
        max_length=20,
        choices=Course.CourseType.choices,
        blank=True,
        help_text="Blank applies to any kind of course not covered by a more specific scheme.",
    )
    internal_max = models.DecimalField(
        "Internal (CIA) maximum",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="e.g. 40",
    )
    external_max = models.DecimalField(
        "End semester maximum",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="e.g. 60. Use 0 for a course assessed only inside the college.",
    )
    grade_scale = models.ForeignKey(GradeScale, on_delete=models.PROTECT, related_name="schemes")
    min_external_percent = models.DecimalField(
        "Pass: end semester at least (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=percent_validators,
        help_text="e.g. 45 means at least 27 out of 60 in the end semester exam.",
    )
    min_total_percent = models.DecimalField(
        "Pass: total at least (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=percent_validators,
        help_text="e.g. 50 means at least 50 out of 100 overall.",
    )
    min_internal_percent = models.DecimalField(
        "Pass: internal at least (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=percent_validators,
        help_text="Leave at 0 when the regulation has no internal minimum.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["regulation", "course_type", "code"]
        constraints = [
            models.UniqueConstraint(fields=["college", "code"], name="unique_scheme_code"),
            models.UniqueConstraint(
                fields=["college", "regulation", "course_type"],
                condition=models.Q(is_active=True),
                name="one_active_scheme_per_regulation_and_type",
            ),
            models.CheckConstraint(
                condition=models.Q(internal_max__gte=0) & models.Q(external_max__gte=0),
                name="scheme_maximums_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(internal_max__gt=0) | models.Q(external_max__gt=0),
                name="scheme_has_some_marks",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    @property
    def total_max(self) -> Decimal:
        return self.internal_max + self.external_max

    def problems(self) -> list[str]:
        """What stops this scheme from being used, in plain words. Empty when it is fine."""
        found = []
        components = list(self.components.all())
        weights = sum((c.weight for c in components), ZERO)
        if self.internal_max > 0 and not components:
            found.append("The scheme has an internal maximum but no components.")
        elif weights != self.internal_max:
            found.append(
                f"The components add up to {weights} but the internal maximum is "
                f"{self.internal_max}."
            )
        found.extend(f"Grade scale: {p}" for p in self.grade_scale.problems())
        return found

    def clean(self):
        super().clean()
        if self.min_external_percent and not self.external_max:
            raise ValidationError(
                {"min_external_percent": "There is no end semester exam to set a minimum for."}
            )

    @transaction.atomic
    def copy(self, code: str, *, grade_scale: GradeScale | None = None) -> "AssessmentScheme":
        """An unlocked, inactive copy with the same components, for changes to a scheme in use.

        The copy starts inactive so it can be checked before it replaces the original.
        """
        components = list(self.components.all())
        new = AssessmentScheme.objects.create(
            code=code,
            name=self.name,
            regulation=self.regulation,
            course_type=self.course_type,
            internal_max=self.internal_max,
            external_max=self.external_max,
            grade_scale=grade_scale or self.grade_scale,
            min_external_percent=self.min_external_percent,
            min_total_percent=self.min_total_percent,
            min_internal_percent=self.min_internal_percent,
            is_active=False,
        )
        for component in components:
            SchemeComponent.objects.create(
                scheme=new,
                **{f: getattr(component, f) for f in SchemeComponent.COPIED_FIELDS},
            )
        return new


class SchemeComponent(Audited, TenantModel):
    """One part of the internal marks, e.g. "Tests: best 2 of 3, each out of 100, worth 30"."""

    class Kind(models.TextChoices):
        TEST = "test", "Internal test"
        MODEL_EXAM = "model_exam", "Model exam"
        ASSIGNMENT = "assignment", "Assignment"
        SEMINAR = "seminar", "Seminar or presentation"
        QUIZ = "quiz", "Quiz"
        LAB = "lab", "Lab work and record"
        PROJECT_REVIEW = "project_review", "Project review"
        ATTENDANCE = "attendance", "Attendance marks"
        OTHER = "other", "Other"

    class Rule(models.TextChoices):
        # Adding them up and scaling gives the same marks as averaging, so there is no "sum".
        AVERAGE = "average", "All of them count"
        BEST = "best", "Only the best few count"

    COPIED_FIELDS = [
        "code",
        "name",
        "kind",
        "count",
        "max_marks",
        "rule",
        "best_of",
        "weight",
        "sort_order",
    ]

    scheme = models.ForeignKey(
        AssessmentScheme, on_delete=models.CASCADE, related_name="components"
    )
    code = models.CharField(max_length=20, validators=[code_validator], help_text="e.g. TEST")
    name = models.CharField(max_length=100, help_text="e.g. Internal assessment tests")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    count = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="How many are held, e.g. 3 tests.",
    )
    max_marks = models.DecimalField(
        "Each out of",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="The maximum of each one as the teacher marks it, e.g. 100.",
    )
    rule = models.CharField(max_length=10, choices=Rule.choices, default=Rule.AVERAGE)
    best_of = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text='For "best few": how many count, e.g. 2 of 3.',
    )
    weight = models.DecimalField(
        "Worth (marks)",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text="What this part adds to the internal total, e.g. 30 out of 40.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["scheme", "sort_order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["scheme", "code"], name="unique_component_code"),
            models.CheckConstraint(
                condition=models.Q(count__gte=1) & models.Q(count__lte=20),
                name="component_count_range",
            ),
            models.CheckConstraint(condition=models.Q(max_marks__gt=0), name="component_max_gt_0"),
            models.CheckConstraint(
                condition=models.Q(weight__gte=0), name="component_weight_gte_0"
            ),
            models.CheckConstraint(
                condition=~models.Q(rule="best")
                | (models.Q(best_of__isnull=False) & models.Q(best_of__lte=models.F("count"))),
                name="component_best_of_within_count",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.describe()})"

    def describe(self) -> str:
        each = f"each out of {self.max_marks.normalize():f}"
        if self.count == 1:
            how = f"out of {self.max_marks.normalize():f}"
        elif self.rule == self.Rule.BEST:
            how = f"best {self.best_of} of {self.count}, {each}"
        else:
            how = f"all {self.count}, {each}"
        return f"{how}, worth {self.weight.normalize():f}"

    def clean(self):
        super().clean()
        if self.rule == self.Rule.BEST:
            if not self.best_of:
                raise ValidationError({"best_of": 'Say how many count for "best few".'})
            if self.best_of > self.count:
                raise ValidationError({"best_of": "Cannot count more than are held."})
        elif self.best_of:
            raise ValidationError({"best_of": 'Only used with "best few".'})

    def _refuse_if_scheme_locked(self) -> None:
        if self.scheme_id and AssessmentScheme.all_colleges.filter(
            pk=self.scheme_id, is_locked=True
        ):
            raise SchemeLocked("This scheme is in use and locked. Make a copy to change it.")

    def save(self, *args, **kwargs):
        self._refuse_if_scheme_locked()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._refuse_if_scheme_locked()
        return super().delete(*args, **kwargs)
