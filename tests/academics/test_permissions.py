"""Who can see and change the academic core; HOD scope stops at their department (D14)."""

import pytest
from django.db import IntegrityError

from apps.academics.models import Course
from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import has_perm
from apps.accounts.roles import Role
from apps.tenancy.context import CrossCollegeError, college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"


@pytest.fixture
def hod_cse(college_a, core_a, make_user):
    return make_user(college_a, "hod.cse", roles=[(Role.HOD, core_a["cse"])])


def test_every_reader_role_can_view(college_a, core_a, make_user):
    for role in [Role.PRINCIPAL, Role.FACULTY, Role.OFFICE, Role.EXAM_CELL]:
        user = make_user(college_a, f"user-{role}", roles=[role])
        with college_context(college_a):
            assert has_perm(user, "academics.view_course")


def test_students_parents_and_accounts_cannot_view(college_a, core_a, make_user):
    for role in [Role.STUDENT, Role.PARENT, Role.ACCOUNTS]:
        user = make_user(college_a, f"user-{role}", roles=[role])
        with college_context(college_a):
            assert not has_perm(user, "academics.view_course")


def test_hod_changes_courses_only_in_own_department(college_a, core_a, hod_cse):
    with college_context(college_a):
        cse_course = core_a["course"]
        ece_course = Course.objects.create(
            programme=core_a["be_ece"],
            semester_number=3,
            code="EC3301",
            title="Circuits",
            credits=3,
            course_type="theory",
        )
        assert has_perm(hod_cse, "academics.change_course", cse_course)
        assert not has_perm(hod_cse, "academics.change_course", ece_course)
        assert has_perm(hod_cse, "academics.change_department", core_a["cse"])
        assert not has_perm(hod_cse, "academics.change_department", core_a["ece"])
        assert not has_perm(hod_cse, "academics.add_department")
        assert not has_perm(hod_cse, "academics.change_academicyear")


def test_principal_is_not_limited_by_department(college_a, core_a, make_user):
    principal = make_user(college_a, "boss", roles=[Role.PRINCIPAL, (Role.HOD, core_a["cse"])])
    with college_context(college_a):
        assert has_perm(principal, "academics.change_department", core_a["ece"])


def test_hod_role_needs_a_department_in_the_same_college(college_a, college_b, core_b, make_user):
    user = make_user(college_a, "nohod")
    with pytest.raises(IntegrityError):
        RoleAssignment.all_colleges.create(user=user, role=Role.HOD)


def test_hod_department_must_be_in_own_college(college_a, core_b, make_user):
    user = make_user(college_a, "wrong")
    with pytest.raises(CrossCollegeError):
        RoleAssignment.all_colleges.create(user=user, role=Role.HOD, department=core_b["cse"])


def test_one_person_can_head_two_departments(college_a, core_a, make_user):
    user = make_user(
        college_a, "twohats", roles=[(Role.HOD, core_a["cse"]), (Role.HOD, core_a["ece"])]
    )
    with college_context(college_a):
        assert has_perm(user, "academics.change_department", core_a["ece"])


class TestAdmin:
    def test_hod_course_form_offers_only_own_programmes(self, client, college_a, core_a, hod_cse):
        client.force_login(hod_cse)
        page = client.get("/admin/academics/course/add/", HTTP_HOST=ALPHA)
        assert page.status_code == 200
        assert b"Alpha B.E. CSE" in page.content
        assert b"Alpha B.E. ECE" not in page.content

    def test_hod_cannot_save_course_into_other_department(self, client, college_a, core_a, hod_cse):
        client.force_login(hod_cse)
        response = client.post(
            "/admin/academics/course/add/",
            {
                "programme": core_a["be_ece"].pk,
                "semester_number": 1,
                "code": "EC1",
                "title": "Sneaky",
                "credits": "3",
                "course_type": "theory",
            },
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 200  # form error: not a valid choice
        assert not Course.all_colleges.filter(code="EC1").exists()

    def test_hod_saves_course_in_own_department(self, client, college_a, core_a, hod_cse):
        client.force_login(hod_cse)
        response = client.post(
            "/admin/academics/course/add/",
            {
                "programme": core_a["be_cse"].pk,
                "semester_number": 1,
                "code": "CS1",
                "title": "Intro",
                "credits": "3",
                "course_type": "theory",
            },
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 302
        assert Course.all_colleges.get(code="CS1").college == college_a

    def test_hod_cannot_edit_other_department(self, client, college_a, core_a, hod_cse):
        client.force_login(hod_cse)
        ece = core_a["ece"]
        response = client.post(
            f"/admin/academics/department/{ece.pk}/change/",
            {"code": "ECE", "name": "Renamed", "is_active": "on"},
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 403
        ece.refresh_from_db()
        assert ece.name == "Alpha Electronics"

    def test_principal_sees_all_admin_pages(self, client, college_a, core_a, make_user):
        client.force_login(make_user(college_a, "boss", roles=[Role.PRINCIPAL]))
        for model in ["department", "programme", "course", "academicyear", "semester"]:
            assert client.get(f"/admin/academics/{model}/", HTTP_HOST=ALPHA).status_code == 200
        year = core_a["year"]
        page = client.get(f"/admin/academics/academicyear/{year.pk}/change/", HTTP_HOST=ALPHA)
        assert page.status_code == 200

    def test_admin_lists_only_own_college(self, client, college_a, core_a, core_b, make_user):
        client.force_login(make_user(college_a, "boss", roles=[Role.PRINCIPAL]))
        page = client.get("/admin/academics/department/", HTTP_HOST=ALPHA)
        assert b"Alpha Computer Science" in page.content
        assert b"Beta Computer Science" not in page.content

    def test_faculty_can_view_but_not_add(self, client, college_a, core_a, make_user):
        client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
        assert client.get("/admin/academics/course/", HTTP_HOST=ALPHA).status_code == 200
        assert client.get("/admin/academics/course/add/", HTTP_HOST=ALPHA).status_code == 403
