from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from .context import CrossCollegeError, get_current_college, require_current_college

# Subdomains that can never belong to a college.
RESERVED_SLUGS = frozenset(
    {"www", "admin", "api", "app", "static", "media", "mail", "platform", "status", "help"}
)

slug_validator = RegexValidator(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    "Use lowercase letters, digits and hyphens only, not starting or ending with a hyphen.",
)


def validate_not_reserved(value: str) -> None:
    if value in RESERVED_SLUGS:
        raise ValidationError(f"'{value}' is reserved and cannot be a college subdomain.")


class College(models.Model):
    """A tenant. Every college-owned row points at exactly one College (D4)."""

    class CollegeType(models.TextChoices):
        ENGINEERING = "engineering", "Engineering"
        ARTS_SCIENCE = "arts_science", "Arts and Science"
        OTHER = "other", "Other"

    class AffiliationStatus(models.TextChoices):
        AFFILIATED = "affiliated", "Affiliated"
        AUTONOMOUS = "autonomous", "Autonomous"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True, help_text="Short code, e.g. DCE.")
    slug = models.CharField(
        max_length=63,
        unique=True,
        validators=[slug_validator, validate_not_reserved],
        help_text="Subdomain the college is served on, e.g. 'demo' for demo.kalvione.in.",
    )
    college_type = models.CharField(max_length=20, choices=CollegeType.choices)
    affiliation_status = models.CharField(
        max_length=20, choices=AffiliationStatus.choices, default=AffiliationStatus.AFFILIATED
    )
    affiliating_university = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    # Per-college configuration (D1): grading scheme, fee heads, regulation year, and so on.
    # Keys are added by the modules that need them and documented there.
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def has_feature(self, key: str) -> bool:
        """True when the feature flag ``key`` is switched on for this college."""
        return self.features.filter(key=key, enabled=True).exists()


class CollegeFeature(models.Model):
    """A per-college on/off switch for needs only some colleges have (D1)."""

    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name="features")
    key = models.SlugField(max_length=100)
    enabled = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["college", "key"], name="unique_feature_per_college")
        ]
        ordering = ["college", "key"]

    def __str__(self) -> str:
        return f"{self.college.code}:{self.key}={'on' if self.enabled else 'off'}"


class TenantQuerySet(models.QuerySet):
    def bulk_create(self, objs, *args, **kwargs):
        college = require_current_college()
        for obj in objs:
            if obj.college_id is None:
                obj.college = college
            elif obj.college_id != college.pk:
                raise CrossCollegeError("bulk_create row belongs to a different college.")
        return super().bulk_create(objs, *args, **kwargs)

    def update(self, **kwargs):
        if "college" in kwargs or "college_id" in kwargs:
            raise CrossCollegeError("A row's college can never be changed.")
        return super().update(**kwargs)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager for college-owned models. Filters to the current college, fails closed."""

    def get_queryset(self):
        college = require_current_college()
        return super().get_queryset().filter(college=college)


class AllCollegesManager(models.Manager.from_queryset(TenantQuerySet)):
    """Explicit, unfiltered access for platform-wide work. Use sparingly and on purpose."""


class TenantModel(models.Model):
    """Abstract base for every college-owned model (D4).

    - ``objects`` returns only the current college's rows and raises
      NoCollegeSelected when no college is set.
    - ``all_colleges`` is the deliberate escape hatch for platform tasks.
    - Saving takes the college from the context, refuses to save into another
      college, and refuses foreign keys that point at another college's rows.
    """

    college = models.ForeignKey(College, on_delete=models.PROTECT, related_name="+", editable=False)

    objects = TenantManager()
    all_colleges = AllCollegesManager()

    class Meta:
        abstract = True
        base_manager_name = "all_colleges"

    def save(self, *args, **kwargs):
        current = get_current_college()
        if self.college_id is None:
            self.college = require_current_college()
        elif current is not None and self.college_id != current.pk:
            raise CrossCollegeError(
                f"Cannot save a {type(self).__name__} of another college while working as "
                f"{current.code}."
            )
        elif self.pk is not None:
            stored = type(self).all_colleges.filter(pk=self.pk).values_list("college_id", flat=True)
            stored_id = stored.first()
            if stored_id is not None and stored_id != self.college_id:
                raise CrossCollegeError("A row's college can never be changed.")
        self._check_related_colleges()
        super().save(*args, **kwargs)

    def _check_related_colleges(self) -> None:
        for field in self._meta.concrete_fields:
            if not field.is_relation or field.name == "college":
                continue
            related_model = field.related_model
            if not (isinstance(related_model, type) and issubclass(related_model, TenantModel)):
                continue
            related_pk = getattr(self, field.attname)
            if related_pk is None:
                continue
            related_college = (
                related_model.all_colleges.filter(pk=related_pk)
                .values_list("college_id", flat=True)
                .first()
            )
            if related_college is not None and related_college != self.college_id:
                raise CrossCollegeError(
                    f"{type(self).__name__}.{field.name} points at another college's row."
                )
