"""Fee set-up in the admin: who can do what, and the structure page with two inlines."""

from decimal import Decimal

import pytest

from apps.accounts.roles import Role
from apps.fees.models import FeeStructure
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
BASE = "/admin/fees/feestructure/"


def structure_post(core, lines, instalments=((1, "Semester 1", "2027-06-15"),), **fields):
    data = {
        "batch": core["be_ece_batch"].pk,
        "academic_year": core["year"].pk,
        "quota": "",
        "residence": "",
        "notes": "",
        "is_active": "on",
        "instalments-TOTAL_FORMS": str(len(instalments)),
        "instalments-INITIAL_FORMS": "0",
        "instalments-MIN_NUM_FORMS": "1",
        "instalments-MAX_NUM_FORMS": "1000",
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "1",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, (number, label, due) in enumerate(instalments):
        data |= {
            f"instalments-{index}-number": str(number),
            f"instalments-{index}-label": label,
            f"instalments-{index}-due_date": due,
        }
    for index, (number, head, amount) in enumerate(lines):
        data |= {
            f"lines-{index}-instalment_number": str(number),
            f"lines-{index}-head": str(core[head].pk),
            f"lines-{index}-amount": amount,
        }
    return data | fields


def test_accountant_sets_up_a_structure(client, college_a, core_a, accountant):
    client.force_login(accountant)
    data = structure_post(core_a, [(1, "tuition", "30000"), (1, "exam", "1200")], quota="MGMT")
    response = client.post(f"{BASE}add/", data, HTTP_HOST=ALPHA)
    assert response.status_code == 302, response.content.decode()[:3000]
    with college_context(college_a):
        structure = FeeStructure.objects.get(batch=core_a["be_ece_batch"])
        assert structure.quota == "MGMT"
        assert structure.total() == Decimal("31200")
        assert structure.instalments.get().label == "Semester 1"
    listing = client.get(BASE, HTTP_HOST=ALPHA)
    assert "31,200.00" in listing.content.decode()


def test_amount_for_a_missing_instalment_is_refused(client, college_a, core_a, accountant):
    client.force_login(accountant)
    data = structure_post(core_a, [(1, "tuition", "30000"), (2, "exam", "1200")])
    response = client.post(f"{BASE}add/", data, HTTP_HOST=ALPHA)
    assert response.status_code == 200
    assert "Instalment 2 is not set up above." in response.content.decode()
    with college_context(college_a):
        assert not FeeStructure.objects.filter(batch=core_a["be_ece_batch"]).exists()


def test_quota_list_comes_from_the_college(client, core_a, accountant):
    client.force_login(accountant)
    page = client.get(f"{BASE}add/", HTTP_HOST=ALPHA).content.decode()
    assert "Every quota" in page and "Management" in page


def test_office_can_see_but_not_change(client, core_a, office):
    client.force_login(office)
    assert client.get(BASE, HTTP_HOST=ALPHA).status_code == 200
    assert client.get(f"{BASE}add/", HTTP_HOST=ALPHA).status_code == 403
    response = client.post(
        f"{BASE}add/", structure_post(core_a, [(1, "tuition", "1")]), HTTP_HOST=ALPHA
    )
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["feehead", "paymentaccount", "feestructure"])
def test_faculty_cannot_see_fee_setup(client, college_a, core_a, make_user, path):
    teacher = make_user(college_a, "teacher", roles=[Role.FACULTY])
    client.force_login(teacher)
    assert client.get(f"/admin/fees/{path}/", HTTP_HOST=ALPHA).status_code == 403


def test_fee_heads_list_shows_ledgers(client, core_a, accountant):
    client.force_login(accountant)
    page = client.get("/admin/fees/feehead/", HTTP_HOST=ALPHA).content.decode()
    assert "Tuition Fees" in page and "Exam Fees" in page


def test_another_colleges_structures_are_not_reachable(client, core_a, core_b, accountant):
    client.force_login(accountant)
    other = core_b["structure"].pk
    response = client.get(f"{BASE}{other}/change/", HTTP_HOST=ALPHA)
    assert response.status_code == 302  # admin redirects a missing object to the list
