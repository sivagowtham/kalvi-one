"""Concessions and dues in the admin: who enters, who decides, and read-only dues."""

from decimal import Decimal

import pytest

from apps.fees.models import Concession, StudentDue
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
CONCESSIONS = "/admin/fees/concession/"


def raise_via_admin(client, core):
    return client.post(
        "/admin/fees/feestructure/",
        {"action": "raise_dues", "_selected_action": [core["structure"].pk]},
        HTTP_HOST=ALPHA,
        follow=True,
    )


def test_accountant_raises_dues_from_the_structure_list(
    client, college_a, core_a, accountant, make_student
):
    make_student(core_a, "26CSE001")
    make_student(core_a, "26CSE002")
    client.force_login(accountant)
    body = raise_via_admin(client, core_a).content.decode()
    assert "6 dues raised for 2 student(s)." in body
    with college_context(college_a):
        assert StudentDue.objects.count() == 6
    listing = client.get("/admin/fees/studentdue/", HTTP_HOST=ALPHA)
    assert listing.status_code == 200 and "26CSE001" in listing.content.decode()
    assert client.get("/admin/fees/studentdue/add/", HTTP_HOST=ALPHA).status_code == 403


def test_office_cannot_raise_dues(client, college_a, core_a, office, make_student):
    make_student(core_a, "26CSE001")
    client.force_login(office)
    raise_via_admin(client, core_a)
    with college_context(college_a):
        assert not StudentDue.objects.exists()


def test_office_enters_and_principal_approves(
    client, college_a, core_a, office, principal, make_student
):
    student = make_student(core_a, "26CSE001")
    with college_context(college_a):
        from apps.fees import dues

        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
    client.force_login(office)
    page = client.get(f"{CONCESSIONS}add/", HTTP_HOST=ALPHA).content.decode()
    assert "Staff ward concession (college)" in page
    response = client.post(
        f"{CONCESSIONS}add/",
        {
            "student": student.pk,
            "academic_year": core_a["year"].pk,
            "kind": "STAFF_WARD",
            "head": core_a["tuition"].pk,
            "percent": "50",
            "amount": "",
            "reason": "Fake staff ward letter",
        },
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 302, response.content.decode()[:3000]
    with college_context(college_a):
        item = Concession.objects.get()
    # The office cannot decide: the approve action is not offered and does nothing.
    client.post(CONCESSIONS, {"action": "approve", "_selected_action": [item.pk]}, HTTP_HOST=ALPHA)
    item.refresh_from_db()
    assert item.status == "pending"

    client.force_login(principal)
    body = client.post(
        CONCESSIONS,
        {"action": "approve", "_selected_action": [item.pk]},
        HTTP_HOST=ALPHA,
        follow=True,
    ).content.decode()
    assert "Approved: 1 concession(s)." in body
    with college_context(college_a):
        waived = sum(d.waived for d in StudentDue.objects.filter(student=student))
    assert waived == Decimal("25000")
    item.refresh_from_db()
    assert item.status == "approved"
    change = client.get(f"{CONCESSIONS}{item.pk}/change/", HTTP_HOST=ALPHA).content.decode()
    assert 'name="percent"' not in change  # decided concessions are read-only
