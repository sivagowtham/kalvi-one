"""Scheme set-up in the admin: who can do what, the add-up check and locked schemes."""

import pytest

from apps.accounts.roles import Role
from apps.exams import presets
from apps.exams.models import AssessmentScheme
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
BASE = "/admin/exams/assessmentscheme/"


@pytest.fixture
def loaded(college_a):
    with college_context(college_a):
        presets.load("anna-r2021")
        return AssessmentScheme.objects.get(code="AU-R2021-THEORY")


@pytest.fixture
def exam_cell(college_a, make_user):
    return make_user(college_a, "examcell", roles=[Role.EXAM_CELL])


def scheme_post(scale, components, **fields):
    data = {
        "code": "AU-R2021-ELECTIVE",
        "name": "Elective",
        "regulation": "R2021",
        "course_type": "elective",
        "is_active": "on",
        "internal_max": "40",
        "external_max": "60",
        "grade_scale": str(scale.pk),
        "min_external_percent": "45",
        "min_total_percent": "50",
        "min_internal_percent": "0",
        "components-TOTAL_FORMS": str(len(components)),
        "components-INITIAL_FORMS": "0",
        "components-MIN_NUM_FORMS": "0",
        "components-MAX_NUM_FORMS": "1000",
    }
    for index, (code, weight) in enumerate(components):
        data |= {
            f"components-{index}-sort_order": str(index),
            f"components-{index}-code": code,
            f"components-{index}-name": code.title(),
            f"components-{index}-kind": "test",
            f"components-{index}-count": "2",
            f"components-{index}-max_marks": "50",
            f"components-{index}-rule": "average",
            f"components-{index}-best_of": "",
            f"components-{index}-weight": weight,
        }
    return data | fields


def test_exam_cell_adds_a_scheme_that_adds_up(client, college_a, loaded, exam_cell):
    client.force_login(exam_cell)
    data = scheme_post(loaded.grade_scale, [("TEST", "30"), ("QUIZ", "10")])
    response = client.post(f"{BASE}add/", data, HTTP_HOST=ALPHA)
    assert response.status_code == 302, response.content
    with college_context(college_a):
        added = AssessmentScheme.objects.get(code="AU-R2021-ELECTIVE")
        assert added.problems() == []


def test_components_that_do_not_add_up_are_refused(client, college_a, loaded, exam_cell):
    client.force_login(exam_cell)
    data = scheme_post(loaded.grade_scale, [("TEST", "30"), ("QUIZ", "5")])
    response = client.post(f"{BASE}add/", data, HTTP_HOST=ALPHA)
    assert response.status_code == 200
    assert b"Make them add up" in response.content
    with college_context(college_a):
        assert not AssessmentScheme.objects.filter(code="AU-R2021-ELECTIVE").exists()


def test_faculty_can_read_but_not_change(client, college_a, loaded, make_user):
    teacher = make_user(college_a, "teacher", roles=[Role.FACULTY])
    client.force_login(teacher)
    assert client.get(BASE, HTTP_HOST=ALPHA).status_code == 200
    assert client.get(f"{BASE}add/", HTTP_HOST=ALPHA).status_code == 403
    page = client.get(f"{BASE}{loaded.pk}/change/", HTTP_HOST=ALPHA)
    assert page.status_code == 200 and b"Save" not in page.content


def test_accounts_staff_cannot_see_schemes(client, college_a, loaded, make_user):
    client.force_login(make_user(college_a, "accounts", roles=[Role.ACCOUNTS]))
    assert client.get(BASE, HTTP_HOST=ALPHA).status_code == 403


def test_locked_scheme_opens_read_only_and_can_be_copied(client, college_a, loaded, exam_cell):
    with college_context(college_a):
        loaded.lock()
    client.force_login(exam_cell)
    page = client.get(f"{BASE}{loaded.pk}/change/", HTTP_HOST=ALPHA)
    assert page.status_code == 200 and b"Save" not in page.content
    response = client.post(
        BASE,
        {"action": "make_copy", "_selected_action": [str(loaded.pk)]},
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 302
    with college_context(college_a):
        copy = AssessmentScheme.objects.get(code="AU-R2021-THEORY-COPY")
        assert not copy.is_locked and not copy.is_active
        assert copy.problems() == []


def test_another_colleges_scheme_is_not_found(client, college_a, college_b, loaded, make_user):
    with college_context(college_b):
        presets.load("bharathiar-cbcs")
        other = AssessmentScheme.objects.get(code="BU-CBCS-THEORY")
    client.force_login(make_user(college_a, "examcell", roles=[Role.EXAM_CELL]))
    response = client.get(f"{BASE}{other.pk}/change/", HTTP_HOST=ALPHA)
    assert response.status_code == 302  # Django admin redirects a missing object


def test_grade_scale_copy_from_the_admin(client, college_a, loaded, exam_cell):
    scale = loaded.grade_scale
    client.force_login(exam_cell)
    page = client.get(f"/admin/exams/gradescale/{scale.pk}/change/", HTTP_HOST=ALPHA)
    assert b"Ready to use." in page.content
    for _ in range(2):
        response = client.post(
            "/admin/exams/gradescale/",
            {"action": "make_copy", "_selected_action": [str(scale.pk)]},
            HTTP_HOST=ALPHA,
            follow=True,
        )
    assert b"already exists" in response.content
    with college_context(college_a):
        from apps.exams.models import GradeScale

        assert GradeScale.objects.get(code="AU-R2021-COPY").bands.count() == 6
