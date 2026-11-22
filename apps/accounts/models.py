from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

from apps.audit.mixins import Audited
from apps.tenancy.context import CrossCollegeError
from apps.tenancy.models import College, TenantModel

from . import permissions
from .roles import Role


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, *, college=None, **fields):
        if not username:
            raise ValueError("A username is required.")
        user = self.model(username=username, college=college, **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **fields):
        """Platform superuser: belongs to no college (D6)."""
        fields.update(is_staff=True, is_superuser=True)
        return self.create_user(username, password, college=None, **fields)


class User(Audited, AbstractBaseUser):
    """A person who can log in. Belongs to one college, or to none for platform staff (D6)."""

    audit_exclude = ("last_login",)
    audit_mask = ("password",)

    college = models.ForeignKey(
        College,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        help_text="Empty only for platform staff.",
    )
    username = models.CharField(
        max_length=150, help_text="Unique within the college. Staff email or student roll number."
    )
    full_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can open the admin site.")
    is_superuser = models.BooleanField(
        default=False, help_text="Platform staff only: every permission on platform hosts."
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["college", "username"], name="unique_username_per_college"
            ),
            models.UniqueConstraint(
                fields=["username"],
                condition=models.Q(college__isnull=True),
                name="unique_platform_username",
            ),
            models.CheckConstraint(
                condition=models.Q(is_superuser=False) | models.Q(college__isnull=True),
                name="superuser_is_platform_only",
            ),
        ]
        ordering = ["username"]

    def __str__(self) -> str:
        return self.full_name or self.username

    @property
    def is_platform_staff(self) -> bool:
        return self.college_id is None

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.username

    # Django's auth API (used by admin) goes through the same default-deny registry.
    def has_perm(self, perm: str, obj=None) -> bool:
        return permissions.has_perm_or_deny(self, perm, obj)

    def has_perms(self, perm_list, obj=None) -> bool:
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label: str) -> bool:
        prefix = f"{app_label}."
        return any(
            code.startswith(prefix) and self.has_perm(code) for code in permissions.registered()
        )

    def roles(self) -> frozenset[Role]:
        """Roles held in the user's own college."""
        if self.college_id is None:
            return frozenset()
        return permissions.roles_for(self, self.college)


class RoleAssignment(Audited, TenantModel):
    """Gives a user one role in their college. A user may hold several (D7)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.CharField(max_length=20, choices=Role.choices)
    department = models.ForeignKey(
        "academics.Department",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
        help_text="Required for HOD: the department they head. Optional for other roles.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"],
                condition=~models.Q(role=Role.HOD),
                name="unique_role_per_user",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "department"],
                condition=models.Q(role=Role.HOD),
                name="unique_hod_per_department",
            ),
            models.CheckConstraint(
                condition=~models.Q(role=Role.HOD) | models.Q(department__isnull=False),
                name="hod_needs_department",
            ),
        ]
        ordering = ["user", "role"]

    def __str__(self) -> str:
        return f"{self.user} as {self.get_role_display()}"

    def save(self, *args, **kwargs):
        if self.user.college_id is None:
            raise CrossCollegeError("Platform staff cannot hold college roles.")
        if self.college_id is None:
            self.college_id = self.user.college_id
        if self.college_id != self.user.college_id:
            raise CrossCollegeError("A role must be in the user's own college.")
        self.user.__dict__.pop("_kalvi_roles", None)
        self.user.__dict__.pop("_kalvi_hod_departments", None)
        super().save(*args, **kwargs)
