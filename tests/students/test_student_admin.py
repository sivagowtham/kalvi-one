"""The student admin: sensitive fields, reveal, and who may edit what."""

import pytest

from apps.accounts.roles import Role
from apps.audit.models import AuditEvent
from apps.students.fakes import fake_aadhaar
from apps.students.models import Guardian, Student
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
ADD = "/admin/students/student/add/"


def inline_management(prefix_counts):
    data = {}
    for prefix, total in prefix_counts.items():
        data |= {
            f"{prefix}-TOTAL_FORMS": str(total),
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }
    return data


def student_post(batch, **overrides):
    data = {
        "roll_number": "26CSE101",
        "admission_number": "A101",
        "register_number": "",
        "initials": "",
        "name": "Fake Student",
        "name_tamil": "",
        "gender": "male",
        "batch": batch.pk,
        "entry_semester": "1",
        "admission_type": "regular",
        "residence": "day_scholar",
        "community": "MBC",
        "quota": "MGMT",
        "nationality": "Indian",
        "qualifying_exam": "hsc",
        "status": "studying",
        "aadhaar_number": "",
        "community_cert_no": "",
        **inline_management({"guardians": 0, "consents": 0}),
    }
    return data | overrides


@pytest.fixture
def office(college_a, make_user):
    return make_user(college_a, "office", roles=[Role.OFFICE])


@pytest.fixture
def student(core_a, make_student):
    s = make_student(core_a, "26CSE001")
    with college_context(s.college):
        s.set_secret("aadhaar", fake_aadhaar(11))
        s.save()
    return s


def test_office_adds_a_student_with_aadhaar_and_a_guardian(client, college_a, core_a, office):
    client.force_login(office)
    number = fake_aadhaar(10)
    data = student_post(
        core_a["be_cse_batch"],
        aadhaar_number=f"{number[:4]} {number[4:8]} {number[8:]}",
        community_cert_no="TN-CC-1",
        **inline_management({"guardians": 1, "consents": 0}),
        **{
            "guardians-0-relation": "father",
            "guardians-0-name": "Fake Father",
            "guardians-0-is_primary": "on",
            "guardians-0-annual_income": "150000",
        },
    )
    response = client.post(ADD, data, HTTP_HOST=ALPHA)
    assert response.status_code == 302, response.content.decode()[:2000]
    with college_context(college_a):
        saved = Student.objects.get(roll_number="26CSE101")
        guardian = Guardian.objects.get(student=saved)
        assert saved.reveal("aadhaar", office) == number
        assert saved.reveal("community_cert_no", office) == "TN-CC-1"
        assert guardian.reveal("annual_income", office) == "150000"


def test_form_rejects_bad_codes_and_aadhaar(client, core_a, office, student):
    client.force_login(office)
    response = client.post(
        ADD,
        student_post(core_a["be_cse_batch"], community="XYZ", aadhaar_number="123412341234"),
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 200
    errors = response.context["adminform"].form.errors
    assert {"community", "aadhaar_number"} <= set(errors)
    duplicate = client.post(
        ADD, student_post(core_a["be_cse_batch"], aadhaar_number=fake_aadhaar(11)), HTTP_HOST=ALPHA
    )
    assert "Another student has this Aadhaar." in duplicate.content.decode()


def test_editing_keeps_aadhaar_when_left_blank(client, college_a, core_a, office, student):
    client.force_login(office)
    data = student_post(core_a["be_cse_batch"], roll_number="26CSE001", admission_number="ADM1")
    response = client.post(f"/admin/students/student/{student.pk}/change/", data, HTTP_HOST=ALPHA)
    assert response.status_code == 302
    student.refresh_from_db()
    assert student.admission_number == "ADM1"
    assert student.aadhaar_last4 == fake_aadhaar(11)[-4:]


def test_office_sees_masked_aadhaar_and_reveals_it(client, college_a, office, student):
    client.force_login(office)
    page = client.get(f"/admin/students/student/{student.pk}/change/", HTTP_HOST=ALPHA)
    body = page.content.decode()
    assert f"XXXX XXXX {fake_aadhaar(11)[-4:]}" in body
    assert fake_aadhaar(11) not in body
    assert "Category (sensitive)" in body
    reveal = client.get(f"/admin/students/student/{student.pk}/reveal/aadhaar/", HTTP_HOST=ALPHA)
    assert fake_aadhaar(11) in reveal.content.decode()
    with college_context(college_a):
        assert AuditEvent.objects.filter(action="view_sensitive", actor=office).count() == 1


def test_faculty_sees_no_sensitive_fields_and_cannot_reveal(client, college_a, student, make_user):
    client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
    page = client.get(f"/admin/students/student/{student.pk}/change/", HTTP_HOST=ALPHA)
    assert page.status_code == 200
    body = page.content.decode()
    assert "Category (sensitive)" not in body
    assert "Aadhaar" not in body
    assert "Alpha Father" not in body
    reveal = client.get(f"/admin/students/student/{student.pk}/reveal/aadhaar/", HTTP_HOST=ALPHA)
    assert reveal.status_code == 403
    assert client.get(ADD, HTTP_HOST=ALPHA).status_code == 403


def test_unknown_reveal_field_is_refused(client, office, student):
    client.force_login(office)
    url = f"/admin/students/student/{student.pk}/reveal/name/"
    assert client.get(url, HTTP_HOST=ALPHA).status_code == 403


def test_exam_cell_edits_only_the_register_number(client, college_a, core_a, student, make_user):
    client.force_login(make_user(college_a, "exams", roles=[Role.EXAM_CELL]))
    url = f"/admin/students/student/{student.pk}/change/"
    response = client.post(
        url, {"register_number": "712226104001", "name": "Changed"}, HTTP_HOST=ALPHA
    )
    assert response.status_code == 302
    student.refresh_from_db()
    assert student.register_number == "712226104001"
    assert student.name == "Student 26CSE001"


def test_students_cannot_be_deleted(client, office, student, college_a, make_user):
    client.force_login(make_user(college_a, "boss", roles=[Role.PRINCIPAL]))
    url = f"/admin/students/student/{student.pk}/delete/"
    assert client.get(url, HTTP_HOST=ALPHA).status_code == 403


def test_list_shows_only_own_college(client, core_b, make_student, office, student):
    make_student(core_b, "26ZZZ999")
    client.force_login(office)
    page = client.get("/admin/students/student/", HTTP_HOST=ALPHA)
    assert b"26CSE001" in page.content
    assert b"26ZZZ999" not in page.content


def test_consent_admin_lists(client, office, student):
    client.force_login(office)
    assert client.get("/admin/students/consent/", HTTP_HOST=ALPHA).status_code == 200
