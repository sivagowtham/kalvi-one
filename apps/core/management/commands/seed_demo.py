"""Create a fake demo college with one user per role. Development only (D10)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import AcademicYear, Course, Department, Programme, Semester
from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import STAFF_ROLES, Role
from apps.audit.context import audit_context
from apps.tenancy.context import college_context
from apps.tenancy.models import College

DEFAULT_PASSWORD = "kalvione-demo-123"  # noqa: S105  (fake demo data only)


@dataclass(frozen=True)
class CollegeSpec:
    name: str
    code: str
    slug: str
    college_type: str
    university: str
    email_domain: str
    departments: tuple[tuple[str, str], ...]
    programmes: tuple[tuple[str, str, str, str, int], ...]  # code, dept, name, level, years
    courses: tuple[tuple[str, int, str, str, str, str], ...]  # prog, sem, code, title, cr, type
    roll_prefix: str


DEMO = CollegeSpec(
    name="Demo College of Engineering",
    code="DCE",
    slug="demo",
    college_type=College.CollegeType.ENGINEERING,
    university="Demo Technical University",
    email_domain="demo.example",
    departments=(
        ("CSE", "Computer Science and Engineering"),
        ("ECE", "Electronics and Communication Engineering"),
        ("MECH", "Mechanical Engineering"),
    ),
    programmes=(
        ("BE-CSE", "CSE", "B.E. Computer Science and Engineering", "ug", 4),
        ("BE-ECE", "ECE", "B.E. Electronics and Communication Engineering", "ug", 4),
    ),
    courses=(
        ("BE-CSE", 1, "DM1101", "Programming in C", "3", "theory_practical"),
        ("BE-CSE", 3, "DM3301", "Data Structures", "3", "theory"),
        ("BE-CSE", 3, "DM3311", "Data Structures Laboratory", "1.5", "practical"),
        ("BE-CSE", 5, "DM5501", "Database Management Systems", "3", "theory"),
        ("BE-ECE", 3, "DE3301", "Digital Electronics", "3", "theory"),
        ("BE-ECE", 5, "DE5501", "Signals and Systems", "4", "theory"),
    ),
    roll_prefix="26DCE",
)

SAMPLE = CollegeSpec(
    name="Sample College of Arts and Science",
    code="SCAS",
    slug="sample",
    college_type=College.CollegeType.ARTS_SCIENCE,
    university="Sample State University",
    email_domain="sample.example",
    departments=(("ENG", "English"), ("COM", "Commerce")),
    programmes=(
        ("BA-ENG", "ENG", "B.A. English", "ug", 3),
        ("BCOM", "COM", "B.Com.", "ug", 3),
    ),
    courses=(
        ("BA-ENG", 1, "SE101", "Poetry", "4", "theory"),
        ("BCOM", 1, "SC101", "Financial Accounting I", "4", "theory"),
    ),
    roll_prefix="26SCAS",
)

# username suffix, roles, staff?
USERS = (
    ("principal", [Role.PRINCIPAL]),
    ("hod", [Role.HOD, Role.FACULTY]),
    ("faculty", [Role.FACULTY]),
    ("office", [Role.OFFICE]),
    ("accounts", [Role.ACCOUNTS]),
    ("examcell", [Role.EXAM_CELL]),
    ("student", [Role.STUDENT]),
    ("parent", [Role.PARENT]),
)


class Command(BaseCommand):
    help = "Create a fake demo college with fake users for every role. Never use in production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password for every demo user (default: %(default)s).",
        )
        parser.add_argument(
            "--with-second-college",
            action="store_true",
            help="Also create 'Sample College of Arts and Science' to try isolation by hand.",
        )

    def handle(self, *args, password, with_second_college, **options):
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError("seed_demo is disabled in these settings (ALLOW_DEMO_SEED=False).")
        specs = [DEMO, SAMPLE] if with_second_college else [DEMO]
        from faker import Faker

        fake = Faker("en_IN")
        Faker.seed(2026)  # same fake names on every run
        with audit_context(actor_label="seed_demo"):
            for spec in specs:
                with transaction.atomic():
                    self._seed(spec, fake, password)
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"Password for every demo user: {password}")

    def _seed(self, spec: CollegeSpec, fake, password: str) -> None:
        college, _ = College.objects.get_or_create(
            slug=spec.slug,
            defaults={
                "name": spec.name,
                "code": spec.code,
                "college_type": spec.college_type,
                "affiliation_status": College.AffiliationStatus.AFFILIATED,
                "affiliating_university": spec.university,
            },
        )
        with college_context(college):
            departments = {
                code: Department.objects.get_or_create(code=code, defaults={"name": name})[0]
                for code, name in spec.departments
            }
            programmes = {}
            for code, dept, name, level, years in spec.programmes:
                programmes[code] = Programme.objects.get_or_create(
                    code=code,
                    defaults={
                        "department": departments[dept],
                        "name": name,
                        "level": level,
                        "duration_years": years,
                        "total_semesters": years * 2,
                        "regulation": "R2025",
                    },
                )[0]
            for prog, sem, code, title, credits, course_type in spec.courses:
                Course.objects.get_or_create(
                    programme=programmes[prog],
                    code=code,
                    defaults={
                        "semester_number": sem,
                        "title": title,
                        "credits": Decimal(credits),
                        "course_type": course_type,
                    },
                )
            year, _ = AcademicYear.objects.get_or_create(
                label="2026-27",
                defaults={
                    "start_date": dt.date(2026, 6, 1),
                    "end_date": dt.date(2027, 5, 31),
                    "is_current": True,
                },
            )
            Semester.objects.get_or_create(
                academic_year=year,
                term=Semester.Term.ODD,
                defaults={
                    "start_date": dt.date(2026, 6, 15),
                    "end_date": dt.date(2026, 11, 30),
                    "is_current": True,
                },
            )
            Semester.objects.get_or_create(
                academic_year=year,
                term=Semester.Term.EVEN,
                defaults={"start_date": dt.date(2026, 12, 15), "end_date": dt.date(2027, 4, 30)},
            )
            first_department = departments[spec.departments[0][0]]
            self.stdout.write(f"\n{college.name}  ->  http://{college.slug}.localhost:8000/admin/")
            for suffix, roles in USERS:
                username = (
                    f"{spec.roll_prefix}001"
                    if suffix == "student"
                    else f"{suffix}@{spec.email_domain}"
                )
                user = User.objects.filter(college=college, username=username).first()
                if user is None:
                    user = User.objects.create_user(
                        username,
                        password,
                        college=college,
                        full_name=fake.name(),
                        email="" if suffix == "student" else username,
                        is_staff=bool(set(roles) & STAFF_ROLES),
                    )
                for role in roles:
                    RoleAssignment.objects.get_or_create(
                        user=user,
                        role=role,
                        department=first_department if role == Role.HOD else None,
                    )
                self.stdout.write(f"  {', '.join(r.label for r in roles):<28} {username}")
