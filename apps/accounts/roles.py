from django.db import models


class Role(models.TextChoices):
    """The fixed set of roles (D7). Adding a role is a code change and a decision entry."""

    PRINCIPAL = "principal", "Principal"
    HOD = "hod", "Head of Department"
    FACULTY = "faculty", "Faculty"
    OFFICE = "office", "Office"
    ACCOUNTS = "accounts", "Accounts"
    EXAM_CELL = "exam_cell", "Exam cell"
    STUDENT = "student", "Student"
    PARENT = "parent", "Parent"


STAFF_ROLES = frozenset(
    {Role.PRINCIPAL, Role.HOD, Role.FACULTY, Role.OFFICE, Role.ACCOUNTS, Role.EXAM_CELL}
)
