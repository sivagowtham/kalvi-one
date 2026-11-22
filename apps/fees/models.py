"""Fees: set-up (D27), concessions and student dues (D28).

Fees depends on students and academics, never the reverse.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.academics.models import AcademicYear
from apps.audit.mixins import Audited
from apps.students import config as student_config
from apps.students.models import Batch, Residence, Student
from apps.tenancy.context import require_current_college
from apps.tenancy.models import TenantModel

from . import config

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


class Concession(Audited, TenantModel):
    """A scholarship or concession for one student in one academic year (D28).

    It counts only once the principal approves it. A percentage can cover every fee head;
    a fixed amount names one head and is taken from that head's earliest instalments first.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Funder(models.TextChoices):
        GOVERNMENT = "government", "Government scholarship"
        COLLEGE = "college", "College concession"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="concessions")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField("type", max_length=20)
    funded_by = models.CharField(max_length=10, choices=Funder.choices, editable=False)
    head = models.ForeignKey(
        FeeHead,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Leave blank for a percentage off every fee head.",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100"))],
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.CharField(max_length=200, help_text="e.g. the sanction order number.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(percent__isnull=False) & models.Q(amount__isnull=True))
                | (
                    models.Q(percent__isnull=True)
                    & models.Q(amount__isnull=False)
                    & models.Q(head__isnull=False)
                ),
                name="concession_percent_or_amount_for_a_head",
            ),
        ]
        indexes = [models.Index(fields=["college", "student", "academic_year", "status"])]

    def __str__(self) -> str:
        size = f"{self.percent}%" if self.percent is not None else f"₹{self.amount}"
        return f"{self.kind} {size} for {self.student.roll_number}"

    @property
    def scope_department_id(self) -> int | None:
        return self.student.scope_department_id if self.student_id else None

    def check_rules(self) -> None:
        if self.college_id is None:
            self.college = require_current_college()
        types = config.concession_types(self.college)
        if self.kind not in types:
            raise ValidationError(
                {"kind": f"{self.kind} is not a concession type of this college."}
            )
        if self.percent is None and self.amount is None:
            raise ValidationError("Give either a percentage or an amount.")
        if self.percent is not None and self.amount is not None:
            raise ValidationError("Give a percentage or an amount, not both.")
        if self.amount is not None and self.head_id is None:
            raise ValidationError({"head": "A fixed amount must name the fee head it is for."})
        if not self.funded_by:
            self.funded_by = types[self.kind][1]

    def clean(self):
        super().clean()
        self.check_rules()

    def save(self, *args, **kwargs):
        self.check_rules()
        super().save(*args, **kwargs)


class StudentDue(Audited, TenantModel):
    """What one student owes for one fee head in one instalment (D28).

    Raised from the student's fee structure. ``waived`` is the college's concession and
    ``govt_share`` the part expected from a government scholarship; neither is the
    student's to pay. ``paid`` is kept up to date by receipts.
    """

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="dues")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="dues")
    instalment_number = models.PositiveSmallIntegerField()
    instalment_label = models.CharField(max_length=50)
    due_date = models.DateField()
    head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="dues")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    waived = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    govt_share = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    paid = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO, editable=False)
    raised_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["student", "due_date", "instalment_number", "head__sort_order"]
        verbose_name = "student due"
        constraints = [
            models.UniqueConstraint(
                fields=["college", "student", "academic_year", "instalment_number", "head"],
                name="unique_student_due",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0)
                & models.Q(waived__gte=0)
                & models.Q(govt_share__gte=0)
                & models.Q(paid__gte=0),
                name="student_due_amounts_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    amount__gte=models.F("waived") + models.F("govt_share") + models.F("paid")
                ),
                name="student_due_not_overpaid",
            ),
        ]
        indexes = [
            models.Index(fields=["college", "student", "academic_year"]),
            models.Index(fields=["college", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.student.roll_number} {self.instalment_label} {self.head}"

    @property
    def scope_department_id(self) -> int | None:
        return self.student.scope_department_id if self.student_id else None

    @property
    def reduction(self) -> Decimal:
        return self.waived + self.govt_share

    @property
    def payable(self) -> Decimal:
        """What the student has to pay, before any payment."""
        return self.amount - self.waived - self.govt_share

    @property
    def balance(self) -> Decimal:
        return self.payable - self.paid


class PaymentMode(models.TextChoices):
    CASH = "cash", "Cash"
    UPI = "upi", "UPI"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer (NEFT, RTGS, IMPS)"
    CHEQUE = "cheque", "Cheque"
    DD = "dd", "Demand draft"


class Receipt(Audited, TenantModel):
    """Money received from one student at one time (D29). Never deleted, only cancelled."""

    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=40, editable=False)
    financial_year = models.CharField(max_length=7, editable=False)
    date = models.DateField(editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="receipts")
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT, related_name="receipts")
    mode = models.CharField(max_length=14, choices=PaymentMode.choices)
    reference = models.CharField(
        max_length=60, blank=True, help_text="UPI transaction ID, cheque or DD number, and so on."
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.CharField(max_length=200, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", editable=False
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.VALID, editable=False
    )
    cancel_reason = models.CharField(max_length=200, blank=True, editable=False)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["college", "number"], name="unique_receipt_number"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="receipt_positive"),
            models.CheckConstraint(
                condition=models.Q(mode="cash") | ~models.Q(reference=""),
                name="receipt_reference_unless_cash",
            ),
        ]
        indexes = [models.Index(fields=["college", "date", "status"])]

    def __str__(self) -> str:
        return self.number

    @property
    def is_cancelled(self) -> bool:
        return self.status == self.Status.CANCELLED


class ReceiptLine(Audited, TenantModel):
    """The part of a receipt that pays one student due, with its GST split if taxable."""

    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, related_name="lines")
    due = models.ForeignKey(StudentDue, on_delete=models.PROTECT, related_name="receipt_lines")
    head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="+")
    instalment_label = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=4, decimal_places=2, default=ZERO)
    taxable_value = models.DecimalField(max_digits=10, decimal_places=2)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ["receipt", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="receipt_line_positive"),
            models.CheckConstraint(
                condition=models.Q(
                    amount=models.F("taxable_value") + models.F("cgst") + models.F("sgst")
                ),
                name="receipt_line_gst_adds_up",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.receipt} {self.head} {self.amount}"

    @property
    def gst_amount(self) -> Decimal:
        return self.cgst + self.sgst
