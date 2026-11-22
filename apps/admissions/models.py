"""Admissions: seats per quota and the application from draft to enrolled (D21).

Admissions depends on students, never the reverse (D16).
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicYear, Programme
from apps.audit.mixins import Audited
from apps.students import config
from apps.students.models import PersonDetails, SensitiveFieldsMixin, Student
from apps.students.validators import mobile_validator
from apps.tenancy.context import require_current_college
from apps.tenancy.models import TenantModel


class Intake(Audited, TenantModel):
    """Sanctioned seats for one programme, year and quota, e.g. B.E. CSE 2026-27 GOVT 60."""

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="intakes")
    quota = models.CharField(max_length=30)
    sanctioned_seats = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["academic_year", "programme", "quota"]
        constraints = [
            models.UniqueConstraint(
                fields=["college", "academic_year", "programme", "quota"],
                name="unique_intake",
            )
        ]

    def __str__(self) -> str:
        return f"{self.programme.code} {self.academic_year} {self.quota}: {self.sanctioned_seats}"

    def save(self, *args, **kwargs):
        if self.college_id is None:
            self.college = require_current_college()
        if self.quota not in config.codes(self.college, "quotas"):
            raise ValidationError({"quota": f"{self.quota} is not a quota this college uses."})
        super().save(*args, **kwargs)

    @property
    def scope_department_id(self) -> int | None:
        return self.programme.department_id if self.programme_id else None

    def filled(self) -> int:
        return Application.objects.filter(
            academic_year=self.academic_year,
            programme=self.programme,
            quota=self.quota,
            status__in=Application.HOLDS_A_SEAT,
        ).count()


class Application(SensitiveFieldsMixin, Audited, PersonDetails, TenantModel):
    """One applicant's application to one programme in one academic year (D21)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        OFFERED = "offered", "Offered a seat"
        CONFIRMED = "confirmed", "Confirmed"
        ENROLLED = "enrolled", "Enrolled"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    HOLDS_A_SEAT = ("offered", "confirmed", "enrolled")
    CLOSED = ("rejected", "withdrawn")

    application_number = models.CharField(max_length=30, blank=True)
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="applications"
    )
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="applications")
    father_name = models.CharField(max_length=200, blank=True)
    mother_name = models.CharField(max_length=200, blank=True)
    guardian_mobile = models.CharField(max_length=10, blank=True, validators=[mobile_validator])
    annual_income_ciphertext = models.TextField(blank=True, editable=False)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    status_changed_at = models.DateTimeField(default=timezone.now, editable=False)
    fee_paid = models.BooleanField(
        default=False, help_text="Ticked by hand until the fees module exists."
    )
    fee_receipt_no = models.CharField(max_length=50, blank=True)
    documents = models.JSONField(
        default=dict, blank=True, help_text="Document code to received (true or false)."
    )
    merit_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="Used for rank lists."
    )
    notes = models.TextField(blank=True)
    student = models.OneToOneField(
        Student,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="application",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    sensitive_fields = ("aadhaar", "community_cert_no", "annual_income")
    audit_mask = (*PersonDetails.audit_mask, "annual_income_ciphertext")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["college", "application_number"], name="unique_application_number"
            ),
            models.CheckConstraint(
                condition=models.Q(status="enrolled", student__isnull=False)
                | (~models.Q(status="enrolled") & models.Q(student__isnull=True)),
                name="enrolled_iff_student",
            ),
            models.UniqueConstraint(
                fields=["college", "academic_year", "aadhaar_hash"],
                condition=~models.Q(aadhaar_hash="")
                & ~models.Q(status__in=["rejected", "withdrawn"]),
                name="one_open_application_per_aadhaar",
            ),
            models.CheckConstraint(
                condition=models.Q(mobile="") | models.Q(mobile__regex=r"^[6-9][0-9]{9}$"),
                name="application_mobile_format",
            ),
        ]
        indexes = [models.Index(fields=["college", "academic_year", "programme", "status"])]

    def __str__(self) -> str:
        return f"{self.application_number} {self.display_name}"

    def save(self, *args, **kwargs):
        if self.college_id is None:
            self.college = require_current_college()
        self.check_config_codes()
        if not self.application_number:
            from apps.students.numbering import next_number

            self.application_number = next_number(
                self.college,
                "application_number_pattern",
                lambda n: Application.objects.filter(application_number=n).exists(),
                yy=f"{self.academic_year.start_date.year % 100:02d}",
            )
        super().save(*args, **kwargs)

    @property
    def scope_department_id(self) -> int | None:
        return self.programme.department_id if self.programme_id else None

    def missing_documents(self) -> list[str]:
        required = config.setting(self.college, "required_documents")
        return [label for code, label in required if not self.documents.get(code)]

    def clean(self) -> None:
        super().clean()
        if self.college_id is None:
            self.college = require_current_college()
        self.check_config_codes()
