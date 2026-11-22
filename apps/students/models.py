"""Students (D16, D17). This file starts with batches and sections; the student record follows."""

from django.core.validators import MinValueValidator
from django.db import models

from apps.academics.models import AcademicYear, Programme
from apps.audit.mixins import Audited
from apps.tenancy.models import TenantModel


class Batch(Audited, TenantModel):
    """The students admitted into one programme in one academic year, e.g. B.E. CSE 2026-2030.

    Lateral entry students join an existing batch at semester 3 (D17).
    """

    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="batches")
    admission_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="admitted_batches",
        help_text="The academic year in which the batch joined.",
    )
    label = models.CharField(
        max_length=20, blank=True, help_text="e.g. 2026-2030. Filled in from the programme."
    )
    regulation = models.CharField(
        max_length=30,
        blank=True,
        help_text="Copied from the programme when left blank. Regulations change by batch.",
    )
    is_active = models.BooleanField(default=True, help_text="Untick once the batch passes out.")

    class Meta:
        ordering = ["programme", "-admission_year__start_date"]
        verbose_name_plural = "batches"
        constraints = [
            models.UniqueConstraint(
                fields=["college", "programme", "admission_year"], name="unique_batch_per_year"
            )
        ]

    def __str__(self) -> str:
        return f"{self.programme.code} {self.label}"

    @property
    def scope_department_id(self) -> int | None:
        return self.programme.department_id if self.programme_id else None

    def default_label(self) -> str:
        start = self.admission_year.start_date.year
        return f"{start}-{start + self.programme.duration_years}"

    def save(self, *args, **kwargs):
        if self.programme_id and self.admission_year_id:
            if not self.label:
                self.label = self.default_label()
            if not self.regulation:
                self.regulation = self.programme.regulation
        super().save(*args, **kwargs)


class Section(Audited, TenantModel):
    """A section within a batch, such as A or B. Students are placed per term (D17)."""

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="sections")
    name = models.CharField(max_length=10, help_text="e.g. A")
    capacity = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )

    class Meta:
        ordering = ["batch", "name"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "name"], name="unique_section_per_batch"),
            models.CheckConstraint(
                condition=models.Q(capacity__isnull=True) | models.Q(capacity__gte=1),
                name="section_capacity_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.batch} {self.name}"

    @property
    def scope_department_id(self) -> int | None:
        return self.batch.programme.department_id if self.batch_id else None
