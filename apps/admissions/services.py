"""Moving an application through its statuses and enrolling it (D21).

All status changes go through ``move`` and ``enrol``, never by editing ``status`` directly.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.academics.models import Semester
from apps.accounts.models import RoleAssignment, User
from apps.accounts.permissions import has_perm
from apps.accounts.roles import Role
from apps.students import config, numbering
from apps.students.models import (
    AdmissionType,
    Batch,
    Consent,
    Guardian,
    PersonDetails,
    Section,
    Student,
)
from apps.students.promotion import place

from .models import Application, Intake

S = Application.Status

# Allowed moves. "enrolled" is reached only through enrol().
TRANSITIONS: dict[str, set[str]] = {
    S.DRAFT: {S.SUBMITTED, S.WITHDRAWN},
    S.SUBMITTED: {S.OFFERED, S.REJECTED, S.WITHDRAWN},
    S.OFFERED: {S.CONFIRMED, S.REJECTED, S.WITHDRAWN},
    S.CONFIRMED: {S.WITHDRAWN},
    S.ENROLLED: set(),
    S.REJECTED: set(),
    S.WITHDRAWN: set(),
}


def seats_left(application: Application) -> int | None:
    """Seats left in the application's quota, or None when no intake is set for it."""
    intake = Intake.objects.filter(
        academic_year=application.academic_year,
        programme=application.programme,
        quota=application.quota,
    ).first()
    return None if intake is None else intake.sanctioned_seats - intake.filled()


@transaction.atomic
def move(application: Application, to: str, user) -> Application:
    """Change the status, checking the allowed moves, seats, fee and documents."""
    if not has_perm(user, "admissions.change_application", application):
        raise PermissionDenied
    application = Application.objects.select_for_update().get(pk=application.pk)
    if to not in TRANSITIONS[application.status]:
        raise ValidationError(
            f"{application.application_number}: cannot go from "
            f"{application.get_status_display().lower()} to {S(to).label.lower()}."
        )
    if to == S.OFFERED:
        if not application.quota:
            raise ValidationError(f"{application.application_number}: choose a quota first.")
        left = seats_left(application)
        if left is not None and left <= 0:
            raise ValidationError(
                f"{application.application_number}: no {application.quota} seats left in "
                f"{application.programme.code}."
            )
    if to == S.CONFIRMED:
        problems = []
        if not application.fee_paid:
            problems.append("the fee is not marked paid")
        missing = application.missing_documents()
        if missing:
            problems.append("missing " + ", ".join(missing))
        if problems:
            raise ValidationError(f"{application.application_number}: {'; '.join(problems)}.")
    application.status = to
    application.status_changed_at = timezone.now()
    application.save()
    return application


PERSON_FIELDS = [f.attname for f in PersonDetails._meta.concrete_fields if f.attname not in {"id"}]


@transaction.atomic
def enrol(
    application: Application,
    user,
    *,
    section: Section,
    term: Semester | None = None,
    consent_by: str = Consent.GivenBy.GUARDIAN,
) -> Student:
    """Turn a confirmed application into a student, a login and a first-term placement.

    Everything happens in one transaction, so a failure leaves nothing half made.
    The new login has no usable password; staff set one or send a reset later.
    """
    if not has_perm(user, "admissions.enrol_application", application):
        raise PermissionDenied
    application = Application.objects.select_for_update().get(pk=application.pk)
    if application.status != S.CONFIRMED:
        raise ValidationError(
            f"{application.application_number}: only a confirmed application can be enrolled."
        )
    batch, _ = Batch.objects.get_or_create(
        programme=application.programme, admission_year=application.academic_year
    )
    if section.batch_id != batch.pk:
        raise ValidationError(f"Section {section} is not in the {batch} batch.")
    term = term or Semester.objects.filter(is_current=True).first()
    if term is None:
        raise ValidationError("Set the current term under Academics first.")
    if (
        application.aadhaar_hash
        and Student.objects.filter(aadhaar_hash=application.aadhaar_hash).exists()
    ):
        raise ValidationError("A student with this Aadhaar number is already enrolled.")
    lateral = application.admission_type == AdmissionType.LATERAL
    semester_number = 3 if lateral else 1

    student = Student(
        batch=batch,
        roll_number=numbering.roll_number(batch),
        admission_number=numbering.admission_number(application.college, application.academic_year),
        admission_date=timezone.localdate(),
        entry_semester=semester_number,
        **{name: getattr(application, name) for name in PERSON_FIELDS},
    )
    student.save()
    login = User.objects.create_user(
        student.roll_number,
        None,
        college=application.college,
        full_name=student.display_name,
        email=student.email,
        phone=student.mobile,
    )
    RoleAssignment.objects.create(user=login, role=Role.STUDENT)
    student.user = login
    student.save()

    father = None
    if application.father_name:
        father = Guardian(
            student=student,
            relation=Guardian.Relation.FATHER,
            name=application.father_name,
            mobile=application.guardian_mobile,
            is_primary=True,
        )
        # Copy the ciphertext as it is: no need to decrypt (D18).
        father.annual_income_ciphertext = application.annual_income_ciphertext
        father.save()
    if application.mother_name:
        Guardian.objects.create(
            student=student,
            relation=Guardian.Relation.MOTHER,
            name=application.mother_name,
            mobile="" if father else application.guardian_mobile,
            is_primary=father is None,
        )
    primary = student.guardians.filter(is_primary=True).first()
    if consent_by == Consent.GivenBy.GUARDIAN and primary is None:
        raise ValidationError("Guardian consent needs a guardian. Add the father or mother.")
    Consent.objects.create(
        student=student,
        notice_version=config.setting(application.college, "consent_notice_version"),
        given_by=consent_by,
        guardian=primary if consent_by == Consent.GivenBy.GUARDIAN else None,
    )
    place(student, term, section, semester_number)

    application.student = student
    application.status = S.ENROLLED
    application.status_changed_at = timezone.now()
    application.save()
    return student


def merit_list(academic_year, programme, community: str = ""):
    """Submitted and later applications ranked by merit score, then marks, then age.

    The older applicant ranks first on a tie, as in Tamil Nadu rank lists.
    """
    rows = Application.objects.filter(
        academic_year=academic_year,
        programme=programme,
        status__in=[S.SUBMITTED, S.OFFERED, S.CONFIRMED, S.ENROLLED],
    )
    if community:
        rows = rows.filter(community=community)
    return rows.order_by(
        F("merit_score").desc(nulls_last=True),
        F("qualifying_percent").desc(nulls_last=True),
        F("date_of_birth").asc(nulls_last=True),
        "application_number",
    )
