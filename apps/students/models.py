"""Students: batches, sections and the student master record (D16 to D20)."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicYear, Programme
from apps.audit.mixins import Audited
from apps.tenancy.models import TenantModel

from .validators import mobile_validator, pincode_validator


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


class SensitiveFieldsMixin:
    """Encrypted fields that are written with ``set_secret`` and read with ``reveal`` (D18, D19).

    Each name in ``sensitive_fields`` is stored in ``<name>_ciphertext``. When the model also
    has ``<name>_last4`` and ``<name>_hash`` columns, they hold the last four characters for
    display and a keyed hash for duplicate checks.
    """

    sensitive_fields: tuple[str, ...] = ()
    sensitive_permission = "students.view_sensitive"

    def set_secret(self, name: str, value: str) -> None:
        from . import crypto

        if name not in self.sensitive_fields:
            raise KeyError(name)
        value = (value or "").strip()
        setattr(self, f"{name}_ciphertext", crypto.encrypt(value))
        if hasattr(self, f"{name}_last4"):
            setattr(self, f"{name}_last4", value[-4:])
        if hasattr(self, f"{name}_hash"):
            setattr(self, f"{name}_hash", crypto.keyed_hash(value))

    def has_secret(self, name: str) -> bool:
        return bool(getattr(self, f"{name}_ciphertext"))

    def masked(self, name: str) -> str:
        if not self.has_secret(name):
            return ""
        last4 = getattr(self, f"{name}_last4", "")
        return f"XXXX XXXX {last4}" if last4 else "(hidden)"

    def reveal(self, name: str, user) -> str:
        """The decrypted value, for a user holding the permission. Every reveal is audited."""
        from django.core.exceptions import PermissionDenied

        from apps.accounts.permissions import has_perm
        from apps.audit.models import AuditEvent
        from apps.audit.recorder import record

        from . import crypto

        if name not in self.sensitive_fields:
            raise KeyError(name)
        if not has_perm(user, self.sensitive_permission, self):
            raise PermissionDenied
        record(AuditEvent.Action.VIEW_SENSITIVE, instance=self, actor=user, extra={"field": name})
        return crypto.decrypt(getattr(self, f"{name}_ciphertext"))


def check_user_college(instance, field: str = "user") -> None:
    """Users are not TenantModels, so a link to one is checked by hand (D12)."""
    from apps.tenancy.context import CrossCollegeError

    user = getattr(instance, field, None)
    if user is not None and user.college_id != instance.college_id:
        raise CrossCollegeError(f"{type(instance).__name__}.{field} belongs to another college.")


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    TRANSGENDER = "transgender", "Transgender"


class BloodGroup(models.TextChoices):
    A_POS = "A+", "A+"
    A_NEG = "A-", "A-"
    B_POS = "B+", "B+"
    B_NEG = "B-", "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS = "O+", "O+"
    O_NEG = "O-", "O-"


class AdmissionType(models.TextChoices):
    REGULAR = "regular", "Regular"
    LATERAL = "lateral", "Lateral entry"
    TRANSFER = "transfer", "Transfer from another college"


class QualifyingExam(models.TextChoices):
    HSC = "hsc", "Higher secondary (12th)"
    DIPLOMA = "diploma", "Diploma"
    UG = "ug", "Undergraduate degree"
    OTHER = "other", "Other"


class Residence(models.TextChoices):
    DAY_SCHOLAR = "day_scholar", "Day scholar"
    HOSTEL = "hostel", "Hostel"


class PersonDetails(models.Model):
    """Personal fields shared by Student and, later, the admission Application (D16).

    Community and quota are codes checked against the college's config (D20), so they are
    plain text here, not database choices.
    """

    name = models.CharField(max_length=200, help_text="As in the 12th mark sheet.")
    initials = models.CharField(max_length=20, blank=True, help_text="e.g. K. or R.S.")
    name_tamil = models.CharField(max_length=200, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=12, choices=Gender.choices)
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices, blank=True)

    community = models.CharField(max_length=20, blank=True)
    caste = models.CharField(max_length=100, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    nationality = models.CharField(max_length=50, default="Indian")
    mother_tongue = models.CharField(max_length=50, blank=True)
    is_first_graduate = models.BooleanField(default=False)
    first_graduate_cert_no = models.CharField(max_length=50, blank=True)
    is_govt_school_student = models.BooleanField(
        default=False, help_text="Studied 6th to 12th in a government school (7.5% reservation)."
    )
    is_differently_abled = models.BooleanField(default=False)
    disability_note = models.CharField(max_length=200, blank=True)

    quota = models.CharField(max_length=30, blank=True)
    admission_type = models.CharField(
        max_length=10, choices=AdmissionType.choices, default=AdmissionType.REGULAR
    )

    qualifying_exam = models.CharField(
        max_length=10, choices=QualifyingExam.choices, default=QualifyingExam.HSC
    )
    qualifying_board = models.CharField(max_length=100, blank=True)
    school_name = models.CharField(max_length=200, blank=True)
    year_of_passing = models.PositiveSmallIntegerField(null=True, blank=True)
    qualifying_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    cutoff_marks = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="Engineering cut-off."
    )
    tnea_application_no = models.CharField(max_length=30, blank=True)
    tnea_rank = models.PositiveIntegerField(null=True, blank=True)

    residence = models.CharField(
        max_length=12, choices=Residence.choices, default=Residence.DAY_SCHOLAR
    )

    mobile = models.CharField(max_length=10, blank=True, validators=[mobile_validator])
    email = models.EmailField(blank=True)
    communication_address = models.TextField(blank=True)
    permanent_address = models.TextField(blank=True)
    pincode = models.CharField(max_length=6, blank=True, validators=[pincode_validator])

    emis_id = models.CharField("EMIS ID", max_length=30, blank=True, help_text="School ID.")
    umis_id = models.CharField(
        "UMIS ID", max_length=30, blank=True, help_text="Tamil Nadu higher education ID."
    )
    apaar_id = models.CharField("APAAR / ABC ID", max_length=30, blank=True)

    # Encrypted (D18): written with set_secret(), read with reveal().
    aadhaar_ciphertext = models.TextField(blank=True, editable=False)
    aadhaar_last4 = models.CharField(max_length=4, blank=True, editable=False)
    aadhaar_hash = models.CharField(max_length=64, blank=True, editable=False)
    community_cert_no_ciphertext = models.TextField(blank=True, editable=False)

    sensitive_fields = ("aadhaar", "community_cert_no")
    audit_mask = ("aadhaar_ciphertext", "aadhaar_hash", "community_cert_no_ciphertext")

    class Meta:
        abstract = True

    @property
    def display_name(self) -> str:
        return f"{self.initials} {self.name}".strip() if self.initials else self.name

    def check_config_codes(self) -> None:
        """Community and quota must be codes the college has configured (D20)."""
        from django.core.exceptions import ValidationError

        from . import config

        college = self.college
        errors = {}
        if self.community and self.community not in config.codes(college, "communities"):
            errors["community"] = f"{self.community} is not a community this college uses."
        if self.quota and self.quota not in config.codes(college, "quotas"):
            errors["quota"] = f"{self.quota} is not a quota this college uses."
        if errors:
            raise ValidationError(errors)


class Student(SensitiveFieldsMixin, Audited, PersonDetails, TenantModel):
    """The student master record (D16)."""

    class Status(models.TextChoices):
        STUDYING = "studying", "Studying"
        BREAK = "break", "Break of study"
        DISCONTINUED = "discontinued", "Discontinued"
        TRANSFERRED = "transferred", "Transferred out"
        COMPLETED = "completed", "Course completed"
        PASSED_OUT = "passed_out", "Passed out"

    roll_number = models.CharField(max_length=30, help_text="College-assigned, e.g. 26CSE001.")
    admission_number = models.CharField(max_length=30)
    register_number = models.CharField(
        max_length=30, blank=True, help_text="Assigned by the university after admission."
    )
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="student",
        help_text="The student's login. Its username is the roll number.",
    )
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="students")
    admission_date = models.DateField(null=True, blank=True)
    entry_semester = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="1, or 3 for lateral entry.",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.STUDYING)
    status_date = models.DateField(null=True, blank=True)
    status_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Set here, not only on PersonDetails, because the mixins come first in the MRO.
    sensitive_fields = PersonDetails.sensitive_fields
    audit_mask = PersonDetails.audit_mask
    audit_exclude = ("updated_at",)

    class Meta:
        ordering = ["roll_number"]
        constraints = [
            models.UniqueConstraint(fields=["college", "roll_number"], name="unique_roll_number"),
            models.UniqueConstraint(
                fields=["college", "admission_number"], name="unique_admission_number"
            ),
            models.UniqueConstraint(
                fields=["college", "register_number"],
                condition=~models.Q(register_number=""),
                name="unique_register_number",
            ),
            models.UniqueConstraint(
                fields=["college", "aadhaar_hash"],
                condition=~models.Q(aadhaar_hash=""),
                name="unique_student_aadhaar",
            ),
            models.CheckConstraint(
                condition=models.Q(entry_semester__gte=1, entry_semester__lte=12),
                name="student_entry_semester_range",
            ),
            models.CheckConstraint(
                condition=models.Q(mobile="") | models.Q(mobile__regex=r"^[6-9][0-9]{9}$"),
                name="student_mobile_format",
            ),
            models.CheckConstraint(
                condition=models.Q(pincode="") | models.Q(pincode__regex=r"^[1-9][0-9]{5}$"),
                name="student_pincode_format",
            ),
        ]
        indexes = [
            models.Index(fields=["college", "batch", "status"]),
            models.Index(fields=["college", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.roll_number} {self.display_name}"

    def save(self, *args, **kwargs):
        from apps.tenancy.context import require_current_college

        if self.college_id is None:
            self.college = require_current_college()
        self.check_config_codes()
        check_user_college(self)
        super().save(*args, **kwargs)

    @property
    def programme(self):
        return self.batch.programme

    @property
    def scope_department_id(self) -> int | None:
        return self.batch.programme.department_id if self.batch_id else None

    def clean(self) -> None:
        super().clean()
        if self.college_id is None:
            from apps.tenancy.context import require_current_college

            self.college = require_current_college()
        self.check_config_codes()


class Guardian(SensitiveFieldsMixin, Audited, TenantModel):
    """A parent or guardian of a student. One is the primary contact."""

    class Relation(models.TextChoices):
        FATHER = "father", "Father"
        MOTHER = "mother", "Mother"
        GUARDIAN = "guardian", "Guardian"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="guardians")
    relation = models.CharField(max_length=10, choices=Relation.choices)
    name = models.CharField(max_length=200)
    occupation = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=10, blank=True, validators=[mobile_validator])
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False, help_text="The contact for calls and SMS.")
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="guardian_of",
        help_text="The parent login, once parent accounts exist.",
    )
    annual_income_ciphertext = models.TextField(blank=True, editable=False)

    sensitive_fields = ("annual_income",)
    audit_mask = ("annual_income_ciphertext",)

    class Meta:
        ordering = ["student", "-is_primary", "relation"]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_primary=True),
                name="one_primary_guardian",
            ),
            models.CheckConstraint(
                condition=models.Q(mobile="") | models.Q(mobile__regex=r"^[6-9][0-9]{9}$"),
                name="guardian_mobile_format",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_relation_display()})"

    @property
    def scope_department_id(self) -> int | None:
        return self.student.scope_department_id if self.student_id else None

    def save(self, *args, **kwargs):
        from apps.tenancy.context import require_current_college

        if self.college_id is None:
            self.college = require_current_college()
        check_user_college(self)
        super().save(*args, **kwargs)


class Consent(Audited, TenantModel):
    """Consent to process a student's personal data under a given notice (DPDP Act, D18).

    For a student under 18 the consent comes from a guardian.
    """

    class GivenBy(models.TextChoices):
        STUDENT = "student", "Student"
        GUARDIAN = "guardian", "Guardian"

    class Method(models.TextChoices):
        PAPER = "paper", "Signed on paper"
        ONLINE = "online", "Online"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="consents")
    notice_version = models.CharField(max_length=20)
    given_by = models.CharField(max_length=10, choices=GivenBy.choices)
    guardian = models.ForeignKey(
        Guardian, on_delete=models.PROTECT, null=True, blank=True, related_name="consents"
    )
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.PAPER)
    given_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["student", "-given_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(given_by="guardian") | models.Q(guardian__isnull=False),
                name="guardian_consent_names_guardian",
            ),
            models.CheckConstraint(
                condition=models.Q(withdrawn_at__isnull=True)
                | models.Q(withdrawn_at__gte=models.F("given_at")),
                name="consent_withdrawn_after_given",
            ),
        ]

    def __str__(self) -> str:
        return f"Consent {self.notice_version} for {self.student}"

    @property
    def scope_department_id(self) -> int | None:
        return self.student.scope_department_id if self.student_id else None

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        if self.guardian_id and self.guardian.student_id != self.student_id:
            raise ValidationError("The guardian must belong to the same student.")
        super().save(*args, **kwargs)


class StudentSemester(Audited, TenantModel):
    """Where a student is in one term: semester number and section (D17).

    One row per student per term, so section changes and promotions keep their history.
    """

    class Status(models.TextChoices):
        STUDYING = "studying", "Studying"
        DETAINED = "detained", "Detained"
        BREAK = "break", "Break of study"
        COMPLETED = "completed", "Completed"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="semesters")
    semester = models.ForeignKey(
        "academics.Semester",
        on_delete=models.PROTECT,
        related_name="student_semesters",
        help_text="The term (odd or even) of an academic year.",
    )
    semester_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="placements")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.STUDYING)

    class Meta:
        ordering = ["student", "semester__start_date"]
        verbose_name = "student semester"
        constraints = [
            models.UniqueConstraint(fields=["student", "semester"], name="one_row_per_term"),
            models.CheckConstraint(
                condition=models.Q(semester_number__gte=1, semester_number__lte=12),
                name="student_semester_number_range",
            ),
        ]
        indexes = [models.Index(fields=["section", "semester"])]

    def __str__(self) -> str:
        return f"{self.student.roll_number} semester {self.semester_number} ({self.semester})"

    def save(self, *args, **kwargs):
        self.check_placement()
        super().save(*args, **kwargs)

    @property
    def scope_department_id(self) -> int | None:
        return self.student.scope_department_id if self.student_id else None

    def check_placement(self) -> None:
        """Section in the student's batch, a semester the programme has, and the right term."""
        from django.core.exceptions import ValidationError

        errors = {}
        if self.section_id and self.student_id and self.section.batch_id != self.student.batch_id:
            errors["section"] = "The section must belong to the student's batch."
        if self.student_id and self.semester_number:
            total = self.student.batch.programme.total_semesters
            if self.semester_number > total:
                errors["semester_number"] = f"The programme has only {total} semesters."
            elif self.semester_id and self.semester_number not in self.semester.semester_numbers(
                total
            ):
                errors["semester_number"] = (
                    f"Semester {self.semester_number} does not run in the "
                    f"{self.semester.get_term_display().lower()} term."
                )
        if errors:
            raise ValidationError(errors)

    def clean(self) -> None:
        super().clean()
        self.check_placement()


class NumberCounter(TenantModel):
    """The last number handed out for one prefix, e.g. 26CSE -> 42 (D21).

    Not audited: it holds no personal data, and every number it gives out is recorded on the
    row that uses it.
    """

    key = models.CharField(max_length=50)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["college", "key"], name="unique_counter_key")
        ]

    def __str__(self) -> str:
        return f"{self.key}: {self.last_value}"
