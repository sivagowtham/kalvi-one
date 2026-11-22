"""Who can see and change batches and sections; HOD scope stops at their department (D14)."""

import datetime as dt

import pytest

from apps.academics.models import AcademicYear
from apps.accounts.permissions import has_perm
from apps.accounts.roles import Role
from apps.students.models import Batch, Section
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"


@pytest.fixture
def hod_cse(college_a, core_a, make_user):
    return make_user(college_a, "hod.cse", roles=[(Role.HOD, core_a["cse"])])


def test_staff_roles_can_view(college_a, core_a, make_user):
    for role in [Role.PRINCIPAL, Role.FACULTY, Role.OFFICE, Role.EXAM_CELL, Role.ACCOUNTS]:
        user = make_user(college_a, f"user-{role}", roles=[role])
        with college_context(college_a):
            assert has_perm(user, "students.view_batch")
            assert has_perm(user, "students.view_section")


def test_students_and_parents_cannot_view(college_a, core_a, make_user):
    for role in [Role.STUDENT, Role.PARENT]:
        user = make_user(college_a, f"user-{role}", roles=[role])
        with college_context(college_a):
            assert not has_perm(user, "students.view_batch")


def test_hod_manages_only_own_department(college_a, core_a, hod_cse):
    with college_context(college_a):
        assert has_perm(hod_cse, "students.change_batch", core_a["be_cse_batch"])
        assert not has_perm(hod_cse, "students.change_batch", core_a["be_ece_batch"])
        assert has_perm(hod_cse, "students.change_section", core_a["be_cse_a"])
        assert not has_perm(hod_cse, "students.change_section", core_a["be_ece_a"])
        assert not has_perm(hod_cse, "students.delete_section", core_a["be_cse_a"])


def test_office_manages_college_wide_but_cannot_delete(college_a, core_a, make_user):
    office = make_user(college_a, "office", roles=[Role.OFFICE])
    with college_context(college_a):
        assert has_perm(office, "students.change_section", core_a["be_ece_a"])
        assert has_perm(office, "students.add_batch")
        assert not has_perm(office, "students.delete_batch")


class TestAdmin:
    def test_hod_section_form_offers_only_own_batches(self, client, core_a, hod_cse):
        client.force_login(hod_cse)
        page = client.get("/admin/students/section/add/", HTTP_HOST=ALPHA)
        assert page.status_code == 200
        assert b"BE-CSE 2026-2030" in page.content
        assert b"BE-ECE 2026-2030" not in page.content

    def test_hod_batch_form_offers_only_own_programmes(self, client, core_a, hod_cse):
        client.force_login(hod_cse)
        page = client.get("/admin/students/batch/add/", HTTP_HOST=ALPHA)
        assert b"Alpha B.E. CSE" in page.content
        assert b"Alpha B.E. ECE" not in page.content

    def test_hod_cannot_edit_other_departments_section(self, client, core_a, hod_cse):
        client.force_login(hod_cse)
        section = core_a["be_ece_a"]
        response = client.post(
            f"/admin/students/section/{section.pk}/change/",
            {"batch": section.batch_id, "name": "Z", "capacity": 10},
            HTTP_HOST=ALPHA,
        )
        # The other department's batch is not a valid choice for this HOD, so the form fails.
        assert response.status_code == 200
        assert b"Select a valid choice" in response.content
        section.refresh_from_db()
        assert section.name == "A"

    def test_office_adds_a_section(self, client, college_a, core_a, make_user):
        client.force_login(make_user(college_a, "office", roles=[Role.OFFICE]))
        response = client.post(
            "/admin/students/section/add/",
            {"batch": core_a["be_ece_batch"].pk, "name": "C", "capacity": 60},
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 302
        assert Section.all_colleges.get(name="C").college == college_a

    def test_principal_adds_a_batch_with_defaults(self, client, college_a, core_a, make_user):
        client.force_login(make_user(college_a, "boss", roles=[Role.PRINCIPAL]))
        with college_context(college_a):
            year = AcademicYear.objects.create(
                label="2027-28", start_date=dt.date(2027, 6, 1), end_date=dt.date(2028, 5, 31)
            )
        response = client.post(
            "/admin/students/batch/add/",
            {
                "programme": core_a["be_ece"].pk,
                "admission_year": year.pk,
                "label": "",
                "regulation": "",
                "is_active": "on",
            },
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 302
        with college_context(college_a):
            batch = Batch.objects.get(programme=core_a["be_ece"], admission_year=year)
        assert (batch.label, batch.regulation) == ("2027-2031", "R2021")

    def test_admin_lists_only_own_college(self, client, college_a, core_a, core_b, make_user):
        client.force_login(make_user(college_a, "boss", roles=[Role.PRINCIPAL]))
        page = client.get("/admin/students/batch/", HTTP_HOST=ALPHA)
        assert b"Alpha B.E. CSE" in page.content
        assert b"Beta B.E. CSE" not in page.content

    def test_faculty_can_view_but_not_add(self, client, college_a, core_a, make_user):
        client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
        assert client.get("/admin/students/section/", HTTP_HOST=ALPHA).status_code == 200
        assert client.get("/admin/students/section/add/", HTTP_HOST=ALPHA).status_code == 403
