"""The student master record: isolation, constraints, config codes and sensitive fields."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.roles import Role
from apps.audit.models import AuditEvent
from apps.students import crypto
from apps.students.fakes import fake_aadhaar
from apps.students.models import Consent, Guardian, Student
from apps.tenancy.context import CrossCollegeError, NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def students(core_a, core_b, make_student):
    a = make_student(core_a, "26CSE001")
    b = make_student(core_b, "26CSE001")  # same roll number in another college is fine
    with college_context(a.college):
        Guardian.objects.create(student=a, relation="father", name="Alpha Father")
        Consent.objects.create(student=a, notice_version="v1", given_by="student")
    with college_context(b.college):
        Guardian.objects.create(student=b, relation="mother", name="Beta Mother")
        Consent.objects.create(student=b, notice_version="v1", given_by="student")
    return a, b


@pytest.mark.parametrize("model", [Student, Guardian, Consent])
def test_each_model_is_isolated_per_college(model, college_a, college_b, students):
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids
    assert a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_numbers_are_unique_within_a_college(college_a, core_a, make_student, students):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            make_student(core_a, "26CSE001", admission_number="NEW")
        with transaction.atomic(), pytest.raises(IntegrityError):
            make_student(core_a, "26CSE002", admission_number="ADM26CSE001")
        make_student(core_a, "26CSE003", register_number="")
        make_student(core_a, "26CSE004", register_number="")  # blank twice is fine
        make_student(core_a, "26CSE005", register_number="712226104005")
        with transaction.atomic(), pytest.raises(IntegrityError):
            make_student(core_a, "26CSE006", register_number="712226104005")


def test_mobile_and_pincode_formats_are_enforced(college_a, core_a, make_student):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            make_student(core_a, "26CSE010", mobile="12345")
        with transaction.atomic(), pytest.raises(IntegrityError):
            make_student(core_a, "26CSE011", pincode="012345")
        student = make_student(core_a, "26CSE012", mobile="9876543210", pincode="642001")
    assert student.mobile == "9876543210"


def test_community_and_quota_must_be_configured(college_a, core_a, make_student):
    with college_context(college_a), pytest.raises(ValidationError) as error:
        make_student(core_a, "26CSE020", community="XYZ", quota="NRI")
    assert set(error.value.message_dict) == {"community", "quota"}


def test_a_college_can_configure_its_own_lists(college_a, core_a, make_student):
    college_a.config = {"students": {"quotas": [["NRI", "NRI"]]}}
    college_a.save()
    core_a["be_cse_batch"].college.refresh_from_db()
    student = make_student(core_a, "26CSE021", quota="NRI")
    assert student.quota == "NRI"
    with pytest.raises(ValidationError):
        make_student(core_a, "26CSE022", quota="GOVT")


def test_batch_and_user_must_be_in_the_same_college(college_a, core_b, make_user, students):
    a, _ = students
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Student.objects.create(
            batch=core_b["be_cse_batch"], roll_number="X", admission_number="X", name="X"
        )
    outsider = make_user(core_b["cse"].college, "outsider")
    a.user = outsider
    with college_context(college_a), pytest.raises(CrossCollegeError):
        a.save()


def test_display_name_and_scope(college_a, students, core_a):
    a, _ = students
    a.initials = "K."
    assert a.display_name == "K. Student 26CSE001"
    assert str(a) == "26CSE001 K. Student 26CSE001"
    assert a.programme == core_a["be_cse"]
    assert a.scope_department_id == core_a["cse"].pk
    assert Student().scope_department_id is None
    with college_context(college_a):
        guardian = a.guardians.first()
        consent = a.consents.first()
    assert guardian.scope_department_id == core_a["cse"].pk
    assert str(guardian) == "Alpha Father (Father)"
    assert consent.scope_department_id == core_a["cse"].pk
    assert str(consent).startswith("Consent v1 for 26CSE001")


def test_one_primary_guardian(college_a, students):
    a, _ = students
    with college_context(college_a):
        Guardian.objects.create(student=a, relation="mother", name="M", is_primary=True)
        with pytest.raises(IntegrityError):
            Guardian.objects.create(student=a, relation="guardian", name="G", is_primary=True)


def test_guardian_consent_needs_the_students_own_guardian(
    college_a, core_a, make_student, students
):
    a, _ = students
    other = make_student(core_a, "26CSE030")
    with college_context(college_a):
        stranger = Guardian.objects.create(student=other, relation="father", name="F")
        with pytest.raises(ValidationError):
            Consent.objects.create(
                student=a, notice_version="v1", given_by="guardian", guardian=stranger
            )
        with transaction.atomic(), pytest.raises(IntegrityError):
            Consent.objects.create(student=a, notice_version="v1", given_by="guardian")
        own = a.guardians.first()
        Consent.objects.create(student=a, notice_version="v1", given_by="guardian", guardian=own)


class TestSensitiveFields:
    def test_aadhaar_is_stored_encrypted_with_last4_and_hash(self, college_a, students):
        a, _ = students
        number = fake_aadhaar(1)
        with college_context(college_a):
            a.set_secret("aadhaar", number)
            a.save()
            stored = Student.objects.values().get(pk=a.pk)
        assert number not in str(stored)
        assert stored["aadhaar_last4"] == number[-4:]
        assert stored["aadhaar_hash"] == crypto.keyed_hash(number)
        assert crypto.decrypt(stored["aadhaar_ciphertext"]) == number
        assert a.masked("aadhaar") == f"XXXX XXXX {number[-4:]}"
        assert a.has_secret("aadhaar")

    def test_masked_without_last4_and_unknown_names(self, college_a, students):
        a, _ = students
        assert a.masked("community_cert_no") == ""
        a.set_secret("community_cert_no", "TN-123")
        assert a.masked("community_cert_no") == "(hidden)"
        with pytest.raises(KeyError):
            a.set_secret("name", "x")

    def test_same_aadhaar_twice_in_a_college_is_refused(self, college_a, core_a, make_student):
        first = make_student(core_a, "26CSE040")
        second = make_student(core_a, "26CSE041")
        with college_context(college_a):
            first.set_secret("aadhaar", fake_aadhaar(2))
            first.save()
            second.set_secret("aadhaar", fake_aadhaar(2))
            with pytest.raises(IntegrityError):
                second.save()

    def test_reveal_needs_permission_and_is_audited(self, college_a, students, make_user):
        a, _ = students
        office = make_user(college_a, "office", roles=[Role.OFFICE])
        faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
        with college_context(college_a):
            a.set_secret("aadhaar", fake_aadhaar(3))
            a.save()
            assert a.reveal("aadhaar", office) == fake_aadhaar(3)
            with pytest.raises(PermissionDenied):
                a.reveal("aadhaar", faculty)
            with pytest.raises(KeyError):
                a.reveal("name", office)
            events = AuditEvent.objects.filter(action="view_sensitive")
            assert events.count() == 1
            event = events.get()
        assert event.actor == office
        assert event.extra == {"field": "aadhaar"}
        assert event.object_id == str(a.pk)

    def test_audit_log_never_holds_the_value(self, college_a, students):
        a, _ = students
        with college_context(college_a):
            a.set_secret("aadhaar", fake_aadhaar(4))
            a.save()
            guardian = a.guardians.first()
            guardian.set_secret("annual_income", "120000")
            guardian.save()
            events = AuditEvent.objects.filter(
                content_type__in=ContentType.objects.get_for_models(Student, Guardian).values()
            )
            text = str(list(events.values_list("changes", flat=True)))
        assert fake_aadhaar(4) not in text
        assert "120000" not in text
        assert "***" in text
