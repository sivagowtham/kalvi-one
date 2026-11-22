"""Admissions admin: data entry, status actions, enrolment page and rank list."""

from io import BytesIO

import pytest

from apps.accounts.roles import Role
from apps.admissions.models import Application
from apps.students.fakes import fake_aadhaar
from apps.students.models import Student
from apps.tenancy.context import college_context
from tests.admissions.conftest import ALL_DOCUMENTS

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
BASE = "/admin/admissions/application/"


def add_post(core, **overrides):
    data = {
        "academic_year": core["year"].pk,
        "programme": core["be_cse"].pk,
        "quota": "GOVT",
        "admission_type": "regular",
        "initials": "",
        "name": "NEW APPLICANT",
        "gender": "female",
        "community": "SC",
        "nationality": "Indian",
        "qualifying_exam": "hsc",
        "qualifying_percent": "88.5",
        "father_name": "FATHER",
        "aadhaar_number": fake_aadhaar(77),
        "annual_income": "50000",
        "document_list": ["TC", "SSLC"],
    }
    return data | overrides


def test_office_enters_an_application(client, college_a, core_a, office):
    client.force_login(office)
    response = client.post(f"{BASE}add/", add_post(core_a), HTTP_HOST=ALPHA)
    assert response.status_code == 302, response.content.decode()[:3000]
    with college_context(college_a):
        application = Application.objects.get()
        assert application.reveal("annual_income", office) == "50000"
    assert application.application_number == "APP260001"
    assert application.documents == {"TC": True, "SSLC": True, "HSC": False, "COMMUNITY": False}
    assert application.aadhaar_last4 == fake_aadhaar(77)[-4:]
    page = client.get(f"{BASE}{application.pk}/change/", HTTP_HOST=ALPHA)
    assert b"Confirm the application first." in page.content
    reveal = client.get(f"{BASE}{application.pk}/reveal/aadhaar/", HTTP_HOST=ALPHA)
    assert fake_aadhaar(77) in reveal.content.decode()


def test_duplicate_open_aadhaar_is_caught_in_the_form(client, core_a, office, make_application):
    make_application(core_a, 1)
    client.force_login(office)
    response = client.post(
        f"{BASE}add/", add_post(core_a, aadhaar_number=fake_aadhaar(9001)), HTTP_HOST=ALPHA
    )
    assert "already has an open application" in response.content.decode()


def test_status_actions(client, college_a, core_a, office, make_application, intake):
    applications = [make_application(core_a, n) for n in (1, 2, 3)]
    client.force_login(office)
    ids = [a.pk for a in applications]
    client.post(BASE, {"action": "mark_submitted", "_selected_action": ids}, HTTP_HOST=ALPHA)
    response = client.post(
        BASE, {"action": "mark_offered", "_selected_action": ids}, HTTP_HOST=ALPHA, follow=True
    )
    body = response.content.decode()
    assert "no GOVT seats left" in body
    assert "Offer a seat to: 2 application(s)." in body
    with college_context(college_a):
        statuses = sorted(Application.objects.values_list("status", flat=True))
    assert statuses == ["offered", "offered", "submitted"]


def test_enrol_page(client, college_a, core_a, office, make_application):
    application = make_application(core_a)
    with college_context(college_a):
        application.status = "confirmed"
        application.fee_paid = True
        application.documents = ALL_DOCUMENTS
        application.save()
    client.force_login(office)
    url = f"{BASE}{application.pk}/enrol/"
    page = client.get(url, HTTP_HOST=ALPHA)
    assert page.status_code == 200
    assert b"BE-CSE 2026-2030 A" in page.content
    response = client.post(
        url, {"section": core_a["be_cse_a"].pk, "consent_by": "guardian"}, HTTP_HOST=ALPHA
    )
    assert response.status_code == 302
    with college_context(college_a):
        student = Student.objects.get()
    assert response["Location"].endswith(f"/admin/students/student/{student.pk}/change/")
    after = client.get(f"{BASE}{application.pk}/change/", HTTP_HOST=ALPHA)
    assert b"Enrolled as" in after.content
    # Enrolled applications are read-only
    assert b'name="_save"' not in after.content
    again = client.post(
        url,
        {"section": core_a["be_cse_a"].pk, "consent_by": "guardian"},
        HTTP_HOST=ALPHA,
        follow=True,
    )
    assert "only a confirmed application" in again.content.decode()


def test_enrol_page_needs_batch_sections(client, college_a, core_a, office, make_application):
    application = make_application(core_a, programme="be_ece")
    with college_context(college_a):
        core_a["be_ece_a"].delete()
        core_a["be_ece_b"].delete()
    client.force_login(office)
    response = client.get(f"{BASE}{application.pk}/enrol/", HTTP_HOST=ALPHA, follow=True)
    assert "and its sections first" in response.content.decode()


def test_hod_sees_applications_without_sensitive_fields(
    client, college_a, core_a, make_application, make_user
):
    application = make_application(core_a)
    client.force_login(make_user(college_a, "hod", roles=[(Role.HOD, core_a["cse"])]))
    page = client.get(f"{BASE}{application.pk}/change/", HTTP_HOST=ALPHA)
    body = page.content.decode()
    assert page.status_code == 200
    assert "Family (sensitive)" not in body and "FATHER 1" not in body
    assert client.get(f"{BASE}{application.pk}/enrol/", HTTP_HOST=ALPHA).status_code == 403
    assert client.get(f"{BASE}add/", HTTP_HOST=ALPHA).status_code == 403


def test_merit_list_page_and_excel(client, college_a, core_a, office, make_application):
    for n, marks in [(1, 70), (2, 95)]:
        application = make_application(core_a, n, qualifying_percent=marks)
        with college_context(college_a):
            application.status = "submitted"
            application.save()
    client.force_login(office)
    url = f"{BASE}merit-list/?year={core_a['year'].pk}&programme={core_a['be_cse'].pk}"
    page = client.get(url, HTTP_HOST=ALPHA)
    body = page.content.decode()
    assert body.index("APPLICANT 2") < body.index("APPLICANT 1")
    download = client.get(url + "&format=xlsx", HTTP_HOST=ALPHA)
    assert download["Content-Disposition"].endswith('rank-list-BE-CSE-2026-27.xlsx"')
    from openpyxl import load_workbook

    sheet = load_workbook(BytesIO(download.content)).active
    rows = list(sheet.values)
    assert rows[0][:5] == ("Rank", "Application", "Name", "Date of birth", "Community")
    assert rows[1][2] == "APPLICANT 2"
    empty = client.get(f"{BASE}merit-list/", HTTP_HOST=ALPHA)
    assert empty.status_code == 200


def test_merit_list_hides_community_without_permission(
    client, college_a, core_a, make_application, make_user
):
    application = make_application(core_a)
    with college_context(college_a):
        application.status = "submitted"
        application.save()
    client.force_login(make_user(college_a, "hod", roles=[(Role.HOD, core_a["cse"])]))
    url = f"{BASE}merit-list/?year={core_a['year'].pk}&programme={core_a['be_cse'].pk}"
    from openpyxl import load_workbook

    sheet = load_workbook(BytesIO(client.get(url + "&format=xlsx", HTTP_HOST=ALPHA).content))
    assert "Community" not in next(sheet.active.values)


def test_faculty_cannot_see_rank_lists(client, college_a, core_a, make_user):
    client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
    assert client.get(f"{BASE}merit-list/", HTTP_HOST=ALPHA).status_code == 403


def test_intake_register(client, college_a, core_a, office, intake, make_application, make_user):
    application = make_application(core_a)
    with college_context(college_a):
        application.status = "offered"
        application.save()
    client.force_login(make_user(college_a, "boss", roles=[Role.PRINCIPAL]))
    page = client.get("/admin/admissions/intake/", HTTP_HOST=ALPHA)
    body = page.content.decode()
    assert page.status_code == 200
    assert '<td class="field-filled">1</td>' in body
    assert '<td class="field-left">1</td>' in body
    add = client.get("/admin/admissions/intake/add/", HTTP_HOST=ALPHA)
    assert b"Management" in add.content
    response = client.post(
        "/admin/admissions/intake/add/",
        {
            "academic_year": core_a["year"].pk,
            "programme": core_a["be_cse"].pk,
            "quota": "MGMT",
            "sanctioned_seats": 30,
        },
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 302
