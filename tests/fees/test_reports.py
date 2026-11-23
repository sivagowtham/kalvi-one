"""Dues and collection reports (D30)."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.utils import timezone

from apps.fees import dues, receipts, reports
from apps.fees.models import Concession
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"


@pytest.fixture
def setup(college_a, core_a, make_student, accountant, principal):
    """Two students: one paid 26,000 by cash, one with a 50% government scholarship."""
    paying = make_student(core_a, "26CSE001")
    scholar = make_student(core_a, "26CSE002")
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        scholarship = Concession.objects.create(
            student=scholar,
            academic_year=core_a["year"],
            kind="PMS",
            percent=Decimal("50"),
            reason="Fake",
        )
        dues.approve(scholarship, principal)
        receipts.collect(
            paying, Decimal("26000"), mode="cash", account=core_a["cash"], user=accountant
        )
        cancelled = receipts.collect(
            paying, Decimal("100"), mode="cash", account=core_a["cash"], user=accountant
        )
        receipts.cancel(cancelled, principal, "Test")
    return {"paying": paying, "scholar": scholar}


def test_dues_by_batch_and_students_owing(college_a, core_a, setup):
    with college_context(college_a):
        rows, totals = reports.dues_by_batch(reports.DuesFilter(academic_year=core_a["year"]))
        owing = reports.students_owing(reports.DuesFilter(batch=core_a["be_cse_batch"]))
        exam_only = reports.dues_by_batch(reports.DuesFilter(head=core_a["exam"]))[1]
    assert len(rows) == 1 and rows[0]["students"] == 2 and rows[0]["owing"] == 2
    assert totals["amount"] == Decimal("103000")
    assert totals["govt_share"] == Decimal("25750")
    assert totals["paid"] == Decimal("26000")
    assert totals["balance"] == Decimal("51250")
    assert [(r["roll_number"], r["balance"]) for r in owing] == [
        ("26CSE001", Decimal("25500")),
        ("26CSE002", Decimal("25750")),
    ][::-1]
    assert exam_only["balance"] == Decimal("1250")


def test_overdue_filter_uses_due_dates(college_a, core_a, setup):
    import datetime as dt

    with college_context(college_a):
        july = reports.dues_by_batch(reports.DuesFilter(overdue_on=dt.date(2026, 8, 1)))[1]
        before = reports.dues_by_batch(reports.DuesFilter(overdue_on=dt.date(2026, 7, 1)))[1]
    assert july["amount"] == Decimal("53000")
    assert before["amount"] == 0


def test_collections_leave_out_cancelled_receipts(college_a, setup):
    today = timezone.localdate()
    with college_context(college_a):
        result = reports.collections(today, today)
    assert (result["total"], result["count"], result["cancelled"]) == (Decimal("26000"), 1, 1)
    assert [(r["head__name"], r["amount"]) for r in result["by_head"]] == [
        ("Tuition fee", Decimal("25000")),
        ("Exam fee", Decimal("1000")),
    ]


def test_dues_page_and_excel(client, core_a, setup, office):
    from openpyxl import load_workbook

    client.force_login(office)
    page = client.get("/fees/reports/dues/", HTTP_HOST=ALPHA).content.decode()
    assert "51,250.00" in page and "25,750.00" in page
    batch = core_a["be_cse_batch"].pk
    drill = client.get("/fees/reports/dues/", {"batch": batch}, HTTP_HOST=ALPHA).content.decode()
    assert "26CSE002" in drill and "/fees/collect/" not in drill  # office cannot collect
    download = client.get("/fees/reports/dues/", {"format": "xlsx"}, HTTP_HOST=ALPHA)
    assert download["Content-Type"].startswith("application/vnd.openxmlformats")
    book = load_workbook(BytesIO(download.content))
    assert book.sheetnames == ["By batch", "Students owing"]
    assert book["Students owing"]["A2"].value == "26CSE002"
    assert book["By batch"]["I2"].value == 51250


def test_collections_page_and_excel(client, setup, accountant):
    client.force_login(accountant)
    page = client.get("/fees/reports/collections/", HTTP_HOST=ALPHA).content.decode()
    assert "26,000.00" in page and "1 cancelled, not counted" in page
    today = timezone.localdate().isoformat()
    download = client.get(
        "/fees/reports/collections/",
        {"start": today, "end": today, "format": "xlsx"},
        HTTP_HOST=ALPHA,
    )
    assert download.status_code == 200
    bad = client.get(
        "/fees/reports/collections/", {"start": today, "end": "2000-01-01"}, HTTP_HOST=ALPHA
    )
    assert "The start date is after the end date." in bad.content.decode()


def test_faculty_cannot_see_reports(client, college_a, setup, make_user):
    from apps.accounts.roles import Role

    client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
    assert client.get("/fees/reports/dues/", HTTP_HOST=ALPHA).status_code == 403
    assert client.get("/fees/reports/collections/", HTTP_HOST=ALPHA).status_code == 403
