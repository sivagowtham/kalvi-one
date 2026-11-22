"""Per-term placement and batch promotion (D17)."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError

from apps.academics.models import AcademicYear, Semester
from apps.accounts.roles import Role
from apps.audit.models import AuditEvent
from apps.students import promotion
from apps.students.models import Student, StudentSemester
from apps.tenancy.context import NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"


@pytest.fixture
def placed(college_a, core_a, make_student):
    """Three CSE students in semester 1, odd term: two in A, one in B."""
    rows = []
    for roll, section in [("26CSE001", "a"), ("26CSE002", "a"), ("26CSE003", "b")]:
        student = make_student(core_a, roll)
        with college_context(college_a):
            rows.append(promotion.place(student, core_a["odd"], core_a[f"be_cse_{section}"], 1))
    return rows


@pytest.fixture
def principal(college_a, make_user):
    return make_user(college_a, "boss", roles=[Role.PRINCIPAL])


def test_rows_are_isolated(college_a, college_b, core_b, make_student, placed):
    other = make_student(core_b, "26CSE001")
    with college_context(college_b):
        promotion.place(other, core_b["odd"], core_b["be_cse_a"], 1)
        assert StudentSemester.objects.count() == 1
    with college_context(college_a):
        assert StudentSemester.objects.count() == 3
    with pytest.raises(NoCollegeSelected):
        StudentSemester.objects.count()


def test_placement_rules(college_a, core_a, placed, even_term):
    student = placed[0].student
    with college_context(college_a):
        with pytest.raises(ValidationError, match="batch"):
            promotion.place(student, even_term, core_a["be_ece_a"], 2)
        with pytest.raises(ValidationError, match="even term"):
            promotion.place(student, even_term, core_a["be_cse_a"], 3)
        with pytest.raises(ValidationError, match="only 8"):
            promotion.place(student, even_term, core_a["be_cse_a"], 10)
        with pytest.raises(IntegrityError):
            promotion.place(student, core_a["odd"], core_a["be_cse_a"], 1)
    assert str(placed[0]).startswith("26CSE001 semester 1")
    assert placed[0].scope_department_id == core_a["cse"].pk
    assert StudentSemester().scope_department_id is None


def test_next_term(college_a, core_a, even_term):
    with college_context(college_a):
        assert promotion.next_term(core_a["odd"]) == even_term
        assert promotion.next_term(even_term) is None
        year = AcademicYear.objects.create(
            label="2027-28", start_date=dt.date(2027, 6, 1), end_date=dt.date(2028, 5, 31)
        )
        assert promotion.next_term(even_term) is None
        odd = Semester.objects.create(
            academic_year=year,
            term="odd",
            start_date=dt.date(2027, 6, 15),
            end_date=dt.date(2027, 11, 30),
        )
        assert promotion.next_term(even_term) == odd


def test_promote_with_hold_back_and_section_change(college_a, core_a, placed, even_term, principal):
    first, second, third = placed
    with college_context(college_a):
        counts = promotion.promote(
            principal,
            core_a["be_cse_batch"],
            core_a["odd"],
            hold_back={second.pk},
            sections={third.pk: core_a["be_cse_a"].pk},
        )
        assert counts == {"promoted": 2, "detained": 1, "completed": 0}
        next_rows = {
            r.student.roll_number: r for r in StudentSemester.objects.filter(semester=even_term)
        }
        second.refresh_from_db()
        first.refresh_from_db()
        creates = AuditEvent.objects.filter(action="create", object_repr__contains="semester 2")
        assert creates.count() == 2
    assert set(next_rows) == {"26CSE001", "26CSE003"}
    assert next_rows["26CSE001"].semester_number == 2
    assert next_rows["26CSE003"].section == core_a["be_cse_a"]
    assert second.status == "detained"
    assert first.status == "completed"


def test_promote_twice_does_nothing_more(college_a, core_a, placed, even_term, principal):
    with college_context(college_a):
        promotion.promote(principal, core_a["be_cse_batch"], core_a["odd"])
        assert promotion.promote(principal, core_a["be_cse_batch"], core_a["odd"]) == {
            "promoted": 0,
            "detained": 0,
            "completed": 0,
        }
        plan = promotion.preview(core_a["be_cse_batch"], core_a["odd"])
    assert plan.rows == []


def test_students_who_left_are_not_promoted(college_a, core_a, placed, even_term, principal):
    student = placed[0].student
    with college_context(college_a):
        student.status = Student.Status.DISCONTINUED
        student.save()
        counts = promotion.promote(principal, core_a["be_cse_batch"], core_a["odd"])
    assert counts["promoted"] == 2


def test_last_semester_finishes_the_course(college_a, core_a, make_student, principal):
    student = make_student(core_a, "22CSE001")
    with college_context(college_a):
        even = Semester.objects.create(
            academic_year=core_a["year"],
            term="even",
            start_date=dt.date(2026, 12, 1),
            end_date=dt.date(2027, 4, 30),
        )
        row = promotion.place(student, even, core_a["be_cse_a"], 8)
        plan = promotion.preview(core_a["be_cse_batch"], even)
        assert plan.to_term is None and len(plan.finishing) == 1
        with pytest.raises(ValidationError, match="next term"):
            promotion.promote(principal, core_a["be_cse_batch"], even)
        next_year = AcademicYear.objects.create(
            label="2027-28", start_date=dt.date(2027, 6, 1), end_date=dt.date(2028, 5, 31)
        )
        Semester.objects.create(
            academic_year=next_year,
            term="odd",
            start_date=dt.date(2027, 6, 15),
            end_date=dt.date(2027, 11, 30),
        )
        counts = promotion.promote(principal, core_a["be_cse_batch"], even)
        row.refresh_from_db()
    assert counts == {"promoted": 0, "detained": 0, "completed": 1}
    assert row.status == "completed"


def test_promotion_needs_permission_and_hod_scope(college_a, core_a, placed, even_term, make_user):
    faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
    hod_ece = make_user(college_a, "hod.ece", roles=[(Role.HOD, core_a["ece"])])
    hod_cse = make_user(college_a, "hod.cse", roles=[(Role.HOD, core_a["cse"])])
    with college_context(college_a):
        for user in [faculty, hod_ece]:
            with pytest.raises(PermissionDenied):
                promotion.promote(user, core_a["be_cse_batch"], core_a["odd"])
        assert promotion.promote(hod_cse, core_a["be_cse_batch"], core_a["odd"])["promoted"] == 3


def test_section_outside_the_batch_is_refused(college_a, core_a, placed, even_term, principal):
    with college_context(college_a), pytest.raises(ValidationError, match="not in this batch"):
        promotion.promote(
            principal,
            core_a["be_cse_batch"],
            core_a["odd"],
            sections={placed[0].pk: core_a["be_ece_a"].pk},
        )


class TestPromoteAdmin:
    def url(self, core):
        return f"/admin/students/batch/{core['be_cse_batch'].pk}/promote/"

    def test_page_lists_students_and_warns_about_capacity(
        self, client, college_a, core_a, placed, even_term, principal
    ):
        section = core_a["be_cse_a"]
        with college_context(college_a):
            section.capacity = 1
            section.save()
        client.force_login(principal)
        page = client.get(self.url(core_a), HTTP_HOST=ALPHA)
        body = page.content.decode()
        assert page.status_code == 200
        assert "26CSE003" in body
        assert "above its capacity of 1" in body
        change = client.get(
            f"/admin/students/batch/{core_a['be_cse_batch'].pk}/change/", HTTP_HOST=ALPHA
        )
        assert b"Promote this batch" in change.content

    def test_post_promotes(self, client, college_a, core_a, placed, even_term, principal):
        client.force_login(principal)
        response = client.post(
            self.url(core_a),
            {
                "term": core_a["odd"].pk,
                f"hold_{placed[1].pk}": "on",
                f"section_{placed[2].pk}": core_a["be_cse_a"].pk,
            },
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 302
        with college_context(college_a):
            assert StudentSemester.objects.filter(semester=even_term).count() == 2

    def test_post_without_next_term_shows_the_error(
        self, client, college_a, core_a, placed, principal
    ):
        client.force_login(principal)
        response = client.post(self.url(core_a), {"term": core_a["odd"].pk}, HTTP_HOST=ALPHA)
        assert response.status_code == 200
        assert "does not exist yet" in response.content.decode()

    def test_batch_with_no_placements_redirects(self, client, core_a, principal):
        client.force_login(principal)
        url = f"/admin/students/batch/{core_a['be_ece_batch'].pk}/promote/"
        response = client.get(url, HTTP_HOST=ALPHA)
        assert response.status_code == 302

    def test_faculty_is_refused(self, client, college_a, core_a, placed, make_user):
        client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
        assert client.get(self.url(core_a), HTTP_HOST=ALPHA).status_code == 403

    def test_student_semester_admin_lists(self, client, core_a, placed, principal):
        client.force_login(principal)
        page = client.get("/admin/students/studentsemester/", HTTP_HOST=ALPHA)
        assert b"26CSE001" in page.content
