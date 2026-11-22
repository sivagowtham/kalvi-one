"""Fees: fee heads, payment accounts and fee structures (D26, D27).

Fees depends on students and academics, never the reverse.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.academics.models import AcademicYear
from apps.audit.mixins import Audited
from apps.students import config as student_config
from apps.students.models import Batch, Residence
from apps.tenancy.context import require_current_college
from apps.tenancy.models import TenantModel

code_validator = RegexValidator(
    r"^[A-Z0-9][A-Z0-9_-]{0,19}$", "Use capital letters, digits, hyphens and underscores only."
)
ZERO = Decimal("0")


class FeeHead(Audited, TenantModel):
    """One kind of fee, e.g. Tuition, Exam or Hostel, and the Tally ledger it is posted to."""

    code = models.CharField(max_length=20, validators=[code_validator], help_text="e.g. TUITION")
    name = models.CharField(max_length=100, help_text="As printed on the receipt.")
    tally_ledger = models.CharField(
        max_length=200,
        help_text="The ledger name in Tally, spelt exactly as it is there, e.g. 'Tuition Fees'.",
    )
    gst_rate = models.DecimalField(
        "GST rate (%)",
        max_digits=4,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("40"))],
        help_text="0 for fees exempt from GST, which is most college fees.",
    )
    hsn_sac = models.CharField(
        "HSN or SAC code", max_length=8, blank=True, help_text="Needed only for taxable heads."
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0, help_text="Lower numbers print first on receipts."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["college", "code"], name="unique_fee_head_code"),
            models.CheckConstraint(
                condition=models.Q(gst_rate__gte=0) & models.Q(gst_rate__lte=40),
                name="fee_head_gst_rate_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_taxable(self) -> bool:
        return self.gst_rate > 0

    def clean(self):
        super().clean()
        if self.is_taxable and not self.hsn_sac:
            raise ValidationError({"hsn_sac": "A taxable fee head needs its HSN or SAC code."})


class PaymentAccount(Audited, TenantModel):
    """Where money is received: the cash counter or a bank account, with its Tally ledger."""

    class Kind(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"

    name = models.CharField(max_length=100, help_text="e.g. Cash counter, or SBI current account")
    kind = models.CharField(max_length=4, choices=Kind.choices)
    tally_ledger = models.CharField(
        max_length=200, help_text="The cash or bank ledger name in Tally, spelt exactly."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["college", "name"], name="unique_payment_account")
        ]

    def __str__(self) -> str:
        return self.name


class FeeStructure(Audited, TenantModel):
    """What one batch pays in one academic year, split into instalments.

    A structure can be limited to one quota and to hostel or day scholars. When several fit a
    student, the most specific one applies (D27).
    """

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="fee_structures")
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="fee_structures"
    )
    quota = models.CharField(max_length=30, blank=True, help_text="Leave blank for every quota.")
    residence = models.CharField(
        max_length=12,
        choices=Residence.choices,
        blank=True,
        help_text="Leave blank for hostel and day scholars alike.",
    )
    notes = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["batch", "academic_year", "quota", "residence"]
        constraints = [
            models.UniqueConstraint(
                fields=["college", "batch", "academic_year", "quota", "residence"],
                name="unique_fee_structure",
            )
        ]

    def __str__(self) -> str:
        parts = [str(self.batch), f"year {self.year_of_study}", self.academic_year.label]
        if self.quota:
            parts.append(self.quota)
        if self.residence:
            parts.append(self.get_residence_display())
        return " ".join(parts)

    @property
    def year_of_study(self) -> int:
        return self.academic_year.start_date.year - self.batch.admission_year.start_date.year + 1

    @property
    def scope_department_id(self) -> int | None:
        return self.batch.scope_department_id if self.batch_id else None

    def check_rules(self) -> None:
        if self.college_id is None:
            self.college = require_current_college()
        errors = {}
        if self.quota and self.quota not in student_config.codes(self.college, "quotas"):
            errors["quota"] = f"{self.quota} is not a quota this college uses."
        if self.batch_id and self.academic_year_id:
            duration = self.batch.programme.duration_years
            if not 1 <= self.year_of_study <= duration:
                errors["academic_year"] = (
                    f"{self.batch} studies from {self.batch.admission_year} for {duration} "
                    f"years, so {self.academic_year} is outside it."
                )
        if errors:
            raise ValidationError(errors)

    def clean(self):
        super().clean()
        self.check_rules()

    def save(self, *args, **kwargs):
        self.check_rules()
        super().save(*args, **kwargs)

    def total(self) -> Decimal:
        return self.lines.aggregate(total=models.Sum("amount"))["total"] or ZERO

    def specificity(self) -> int:
        return bool(self.quota) + bool(self.residence)


class Instalment(Audited, TenantModel):
    """One part of a year's fees with its due date, e.g. 'Semester 1, due 15 July'."""

    structure = models.ForeignKey(
        FeeStructure, on_delete=models.CASCADE, related_name="instalments"
    )
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    label = models.CharField(max_length=50, help_text="e.g. Semester 1, or First instalment")
    due_date = models.DateField()

    class Meta:
        ordering = ["structure", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["college", "structure", "number"], name="unique_instalment_number"
            )
        ]

    def __str__(self) -> str:
        return f"{self.label} (due {self.due_date:%d %b %Y})"


class FeeStructureLine(Audited, TenantModel):
    """The amount of one fee head in one instalment of a structure."""

    structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, related_name="lines")
    instalment_number = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="lines")
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        ordering = ["structure", "instalment_number", "head"]
        constraints = [
            models.UniqueConstraint(
                fields=["college", "structure", "instalment_number", "head"],
                name="unique_fee_line",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="fee_line_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.head} {self.amount}"

    def check_instalment(self) -> None:
        if (
            self.structure_id
            and not self.structure.instalments.filter(number=self.instalment_number).exists()
        ):
            raise ValidationError(
                {"instalment_number": f"Instalment {self.instalment_number} is not set up."}
            )

    def save(self, *args, **kwargs):
        self.check_instalment()
        super().save(*args, **kwargs)
