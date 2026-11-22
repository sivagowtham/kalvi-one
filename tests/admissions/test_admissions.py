"""Admissions: intake, status flow, enrolment and rank lists (D21)."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.roles import Role
from apps.admissions import services
from apps.admissions.models import Application, Intake
from apps.students import crypto
from apps.students.fakes import fake_aadhaar
from apps.students.models import Consent, Student, StudentSemester
from apps.tenancy.context import CrossCollegeError, NoCollegeSelected, college_context
from tests.admissions.conftest import ALL_DOCUMENTS

pytestmark = pytest.mark.django_db
S = Application.Status


def advance(application, user, *steps):
    for step in steps:
        application = services.move(application, step, user)
    return application


def confirmed(application, office):
    with college_context(office.college):
        application.fee_paid = True
        application.documents = ALL_DOCUMENTS
        application.save()
        return advance(application, office, S.SUBMITTED, S.OFFERED, S.CONFIRMED)


@pytest.mark.parametrize("model", [Intake, Application])
def test_models_are_isolated(model, college_a, college_b, core_a, core_b, make_application):
    with college_context(college_a):
        Intake.objects.create(
            academic_year=core_a["year"],
            programme=core_a["be_cse"],
            quota="GOVT",
            sanctioned_seats=1,
        )
    with college_context(college_b):
        Intake.objects.create(
            academic_year=core_b["year"],
            programme=core_b["be_cse"],
            quota="GOVT",
            sanctioned_seats=1,
        )
    make_application(core_a)
    make_application(core_b)
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_application_numbers_and_cross_college(college_a, core_a, core_b, make_application):
    first = make_application(core_a, 1)
    second = make_application(core_a, 2)
    assert (first.application_number, second.application_number) == ("APP260001", "APP260002")
    assert str(first) == "APP260001 APPLICANT 1"
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Application.objects.create(
            academic_year=core_a["year"], programme=core_b["be_cse"], name="X", gender="male"
        )


def test_intake_quota_must_be_configured(college_a, core_a):
    with college_context(college_a), pytest.raises(ValidationError):
        Intake.objects.create(
            academic_year=core_a["year"],
            programme=core_a["be_cse"],
            quota="NRI",
            sanctioned_seats=1,
        )


def test_one_open_application_per_aadhaar_per_year(college_a, core_a, make_application, office):
    first = make_application(core_a, 1)
    with transaction.atomic(), pytest.raises(IntegrityError):
        make_application(core_a, 1, name="AGAIN")
    with college_context(college_a):
        services.move(first, S.WITHDRAWN, office)
    make_application(core_a, 1, name="AGAIN")  # allowed once the first is withdrawn


def test_status_flow(college_a, core_a, make_application, office):
    application = make_application(core_a)
    with college_context(college_a):
        with pytest.raises(ValidationError, match="cannot go from draft to confirmed"):
            services.move(application, S.CONFIRMED, office)
        application = advance(application, office, S.SUBMITTED, S.OFFERED)
        with pytest.raises(ValidationError, match="fee is not marked paid; missing"):
            services.move(application, S.CONFIRMED, office)
        application.fee_paid = True
        application.documents = {"TC": True}
        application.save()
        with pytest.raises(ValidationError, match="missing 10th mark sheet"):
            services.move(application, S.CONFIRMED, office)
        application.documents = ALL_DOCUMENTS
        application.save()
        application = services.move(application, S.CONFIRMED, office)
    assert application.status == S.CONFIRMED
    assert application.missing_documents() == []


def test_offers_stop_when_seats_run_out(college_a, core_a, make_application, office, intake):
    apps = [make_application(core_a, n) for n in range(1, 4)]
    with college_context(college_a):
        for application in apps[:2]:
            advance(application, office, S.SUBMITTED, S.OFFERED)
        assert services.seats_left(apps[0]) == 0
        assert intake.filled() == 2
        services.move(apps[2], S.SUBMITTED, office)
        with pytest.raises(ValidationError, match="no GOVT seats left"):
            services.move(apps[2], S.OFFERED, office)
        no_quota = make_application(core_a, 4, quota="")
        services.move(no_quota, S.SUBMITTED, office)
        with pytest.raises(ValidationError, match="choose a quota"):
            services.move(no_quota, S.OFFERED, office)
        # No intake for MGMT: offers are not limited
        mgmt = make_application(core_a, 5, quota="MGMT")
        assert services.seats_left(mgmt) is None
        advance(mgmt, office, S.SUBMITTED, S.OFFERED)


def test_only_clerks_move_applications(college_a, core_a, make_application, make_user):
    application = make_application(core_a)
    hod = make_user(college_a, "hod", roles=[(Role.HOD, core_a["cse"])])
    with college_context(college_a), pytest.raises(PermissionDenied):
        services.move(application, S.SUBMITTED, hod)


class TestEnrol:
    def test_enrol_creates_everything(self, college_a, core_a, make_application, office):
        application = confirmed(make_application(core_a, date_of_birth=dt.date(2008, 5, 1)), office)
        with college_context(college_a):
            student = services.enrol(application, office, section=core_a["be_cse_b"])
            application.refresh_from_db()
            guardians = list(student.guardians.order_by("relation"))
            consent = Consent.objects.get(student=student)
            placement = StudentSemester.objects.get(student=student)
            assert student.reveal("aadhaar", office) == fake_aadhaar(9001)
            assert guardians[0].reveal("annual_income", office) == "90000"
        assert application.status == S.ENROLLED and application.student == student
        assert student.roll_number == "26CSE001"
        assert student.admission_number == "A260001"
        assert student.name == "APPLICANT 1" and student.community == "MBC"
        assert student.aadhaar_hash == crypto.keyed_hash(fake_aadhaar(9001))
        assert student.user.username == "26CSE001"
        assert not student.user.has_usable_password()
        assert student.user.roles() == {Role.STUDENT}
        assert [g.relation for g in guardians] == ["father", "mother"]
        assert guardians[0].is_primary and guardians[0].mobile == "9876500000"
        assert consent.given_by == "guardian" and consent.guardian == guardians[0]
        assert consent.notice_version == "v1"
        assert (placement.semester_number, placement.section) == (1, core_a["be_cse_b"])

    def test_roll_numbers_skip_taken_ones(self, college_a, core_a, make_application, office):
        with college_context(college_a):
            Student.objects.create(
                batch=core_a["be_cse_batch"],
                roll_number="26CSE001",
                admission_number="OLD1",
                name="IMPORTED",
                gender="female",
            )
        application = confirmed(make_application(core_a), office)
        with college_context(college_a):
            student = services.enrol(application, office, section=core_a["be_cse_a"])
        assert student.roll_number == "26CSE002"

    def test_lateral_entry_starts_in_semester_3(self, college_a, core_a, make_application, office):
        application = confirmed(
            make_application(core_a, admission_type="lateral", mother_name=""), office
        )
        with college_context(college_a):
            student = services.enrol(
                application, office, section=core_a["be_cse_a"], consent_by="student"
            )
            placement = StudentSemester.objects.get(student=student)
        assert student.entry_semester == 3 and placement.semester_number == 3

    def test_mother_only_becomes_primary(self, college_a, core_a, make_application, office):
        application = confirmed(make_application(core_a, father_name=""), office)
        with college_context(college_a):
            student = services.enrol(application, office, section=core_a["be_cse_a"])
            mother = student.guardians.get()
        assert mother.is_primary and mother.mobile == "9876500000"

    def test_guardian_consent_needs_a_guardian(self, college_a, core_a, make_application, office):
        application = confirmed(make_application(core_a, father_name="", mother_name=""), office)
        with college_context(college_a), pytest.raises(ValidationError, match="needs a guardian"):
            services.enrol(application, office, section=core_a["be_cse_a"])
        with college_context(college_a):
            assert not Student.objects.exists()  # rolled back

    def test_refusals(self, college_a, core_a, make_application, office, make_user):
        application = make_application(core_a)
        with college_context(college_a), pytest.raises(ValidationError, match="only a confirmed"):
            services.enrol(application, office, section=core_a["be_cse_a"])
        application = confirmed(application, office)
        with college_context(college_a):
            with pytest.raises(ValidationError, match="not in the"):
                services.enrol(application, office, section=core_a["be_ece_a"])
            faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
            with pytest.raises(PermissionDenied):
                services.enrol(application, faculty, section=core_a["be_cse_a"])
            core_a["odd"].is_current = False
            core_a["odd"].save()
            with pytest.raises(ValidationError, match="current term"):
                services.enrol(application, office, section=core_a["be_cse_a"])

    def test_already_enrolled_aadhaar_is_refused(self, college_a, core_a, make_application, office):
        with college_context(college_a):
            existing = Student(
                batch=core_a["be_cse_batch"],
                roll_number="25CSE001",
                admission_number="OLD",
                name="SAME PERSON",
                gender="male",
            )
            existing.set_secret("aadhaar", fake_aadhaar(9001))
            existing.save()
        application = confirmed(make_application(core_a), office)
        with college_context(college_a), pytest.raises(ValidationError, match="already enrolled"):
            services.enrol(application, office, section=core_a["be_cse_a"])

    def test_status_constraint(self, college_a, core_a, make_application):
        application = make_application(core_a)
        with college_context(college_a), pytest.raises(IntegrityError):
            application.status = S.ENROLLED
            application.save()


def test_merit_list_order(college_a, core_a, make_application):
    make_application(core_a, 1, qualifying_percent=90, date_of_birth=dt.date(2008, 3, 1))
    make_application(core_a, 2, qualifying_percent=90, date_of_birth=dt.date(2007, 3, 1))
    make_application(core_a, 3, qualifying_percent=95, community="BC")
    make_application(core_a, 4, merit_score=199)
    for application in Application.all_colleges.all():
        if application.status == S.DRAFT:
            with college_context(college_a):
                application.status = S.SUBMITTED
                application.save()
    make_application(core_a, 5, qualifying_percent=99)  # still a draft: left out
    with college_context(college_a):
        ranked = [a.name for a in services.merit_list(core_a["year"], core_a["be_cse"])]
        bc = [a.name for a in services.merit_list(core_a["year"], core_a["be_cse"], "BC")]
    assert ranked == ["APPLICANT 4", "APPLICANT 3", "APPLICANT 2", "APPLICANT 1"]
    assert bc == ["APPLICANT 3"]
