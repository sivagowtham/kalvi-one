"""Taking payments, receipt numbers, GST split, cancelling, and the counter pages (D29)."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.fees import dues, receipts
from apps.fees.models import Receipt, ReceiptLine, StudentDue
from apps.fees.words import rupees_in_words
from apps.tenancy.context import NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"


@pytest.fixture
def student(college_a, core_a, make_student):
    student = make_student(core_a, "26CSE001")
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
    return student


def pay(core, student, amount, user, mode="cash", account="cash", reference=""):
    with college_context(student.college):
        return receipts.collect(
            student,
            Decimal(amount),
            mode=mode,
            account=core[account],
            reference=reference,
            user=user,
        )


def balances(student):
    with college_context(student.college):
        return [
            (d.head.code, d.instalment_number, d.paid)
            for d in StudentDue.objects.filter(student=student).order_by(
                "due_date", "head__sort_order"
            )
        ]


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        ("0", "Rupees zero only"),
        ("26500", "Rupees twenty-six thousand five hundred only"),
        ("101.05", "Rupees one hundred one and five paise only"),
        ("1250000", "Rupees twelve lakh fifty thousand only"),
        (
            "123456789",
            "Rupees twelve crore thirty-four lakh fifty-six thousand "
            "seven hundred eighty-nine only",
        ),
    ],
)
def test_amounts_in_words(amount, words):
    assert rupees_in_words(Decimal(amount)) == words


def test_financial_year_starts_in_april(college_a):
    assert receipts.financial_year(college_a, dt.date(2027, 3, 31)) == "2026-27"
    assert receipts.financial_year(college_a, dt.date(2027, 4, 1)) == "2027-28"


def test_gst_split_is_inclusive_and_adds_up():
    assert receipts.gst_split(Decimal("1050"), Decimal("5")) == (
        Decimal("1000.00"),
        Decimal("25.00"),
        Decimal("25.00"),
    )
    taxable, cgst, sgst = receipts.gst_split(Decimal("99.99"), Decimal("18"))
    assert taxable + cgst + sgst == Decimal("99.99")
    assert receipts.gst_split(Decimal("10"), Decimal("0")) == (Decimal("10"), 0, 0)


@pytest.mark.parametrize("model", [Receipt, ReceiptLine])
def test_receipts_are_isolated_per_college(
    model, college_a, college_b, core_a, core_b, make_student, accountant, make_user
):
    from apps.accounts.roles import Role

    other = make_user(college_b, "accounts-b", roles=[Role.ACCOUNTS])
    for core, user in ((core_a, accountant), (core_b, other)):
        student = make_student(core, "26CSE001")
        with college_context(student.college):
            dues.raise_dues(core["be_cse_batch"], core["year"])
        pay(core, student, "100", user)
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_oldest_dues_are_paid_first_and_numbers_run_on(core_a, student, accountant):
    first = pay(core_a, student, "26000", accountant)
    second = pay(core_a, student, "1000", accountant, "upi", "bank", "UPI123")
    year = receipts.financial_year(student.college, timezone.localdate())
    assert first.number == f"ACE/{year}/000001"
    assert second.number == f"ACE/{year}/000002"
    assert balances(student) == [
        ("TUITION", 1, Decimal("25000")),
        ("EXAM", 1, Decimal("1500")),
        ("TUITION", 2, Decimal("500")),
    ]
    with college_context(student.college):
        assert [line.amount for line in first.lines.all()] == [Decimal("25000"), Decimal("1000")]


def test_more_than_is_owed_is_refused(core_a, student, accountant):
    with pytest.raises(ValidationError) as error:
        pay(core_a, student, "51500.01", accountant)
    assert "owes ₹51,500.00" in str(error.value)
    pay(core_a, student, "51500", accountant)
    with pytest.raises(ValidationError):
        pay(core_a, student, "1", accountant)


@pytest.mark.parametrize(
    ("mode", "account", "reference", "field"),
    [
        ("cash", "bank", "", "account"),
        ("upi", "cash", "X1", "account"),
        ("cheque", "bank", " ", "reference"),
        ("barter", "cash", "", "mode"),
    ],
)
def test_payment_details_are_checked(core_a, student, accountant, mode, account, reference, field):
    with pytest.raises(ValidationError) as error:
        pay(core_a, student, "10", accountant, mode, account, reference)
    assert field in error.value.message_dict


def test_taxable_heads_split_gst_on_the_receipt(college_a, core_a, student, accountant):
    with college_context(college_a):
        exam = core_a["exam"]
        exam.gst_rate, exam.hsn_sac = Decimal("18"), "999293"
        exam.save()
    receipt = pay(core_a, student, "26500", accountant)
    with college_context(college_a):
        line = receipt.lines.get(head=core_a["exam"])
    assert (line.amount, line.taxable_value, line.cgst, line.sgst) == (
        Decimal("1500"),
        Decimal("1271.19"),
        Decimal("114.41"),
        Decimal("114.40"),
    )


def test_cancelling_puts_the_money_back(college_a, core_a, student, accountant, principal):
    receipt = pay(core_a, student, "26000", accountant)
    with college_context(college_a):
        with pytest.raises(ValidationError):
            receipts.cancel(receipt, principal, " ")
        receipts.cancel(receipt, principal, "Wrong student")
        with pytest.raises(ValidationError):
            receipts.cancel(receipt, principal, "Again")
        receipt.refresh_from_db()
    assert receipt.is_cancelled and receipt.cancelled_by == principal
    assert all(paid == 0 for _, _, paid in balances(student))


class TestCounterPages:
    def test_search_goes_straight_to_a_single_match(self, client, student, accountant):
        client.force_login(accountant)
        response = client.get("/fees/collect/", {"q": "26cse001"}, HTTP_HOST=ALPHA)
        assert response.status_code == 302
        assert response.url == f"/fees/collect/{student.pk}/"
        page = client.get(response.url, HTTP_HOST=ALPHA).content.decode()
        assert "Semester 1" in page and "51,500.00" in page

    def test_take_a_payment_and_print(self, client, core_a, student, accountant):
        client.force_login(accountant)
        response = client.post(
            f"/fees/collect/{student.pk}/",
            {
                "amount": "26500",
                "mode": "upi",
                "account": core_a["bank"].pk,
                "reference": "UPI98765",
                "notes": "",
            },
            HTTP_HOST=ALPHA,
            follow=True,
        )
        body = response.content.decode()
        assert "Rupees twenty-six thousand five hundred only" in body
        assert "UPI98765" in body and "Cancel receipt" not in body
        assert balances(student)[1] == ("EXAM", 1, Decimal("1500"))

    def test_wrong_details_show_on_the_form(self, client, core_a, student, accountant):
        client.force_login(accountant)
        response = client.post(
            f"/fees/collect/{student.pk}/",
            {"amount": "100", "mode": "upi", "account": core_a["bank"].pk, "reference": ""},
            HTTP_HOST=ALPHA,
        )
        assert "Enter the UPI reference number." in response.content.decode()
        with college_context(student.college):
            assert not Receipt.objects.exists()

    def test_office_can_print_but_not_collect_or_cancel(
        self, client, core_a, student, accountant, office
    ):
        receipt = pay(core_a, student, "100", accountant)
        client.force_login(office)
        assert client.get("/fees/collect/", HTTP_HOST=ALPHA).status_code == 403
        assert client.get(f"/fees/receipts/{receipt.pk}/", HTTP_HOST=ALPHA).status_code == 200
        cancel = f"/fees/receipts/{receipt.pk}/cancel/"
        assert client.post(cancel, {"reason": "x"}, HTTP_HOST=ALPHA).status_code == 403

    def test_principal_cancels(self, client, core_a, student, accountant, principal):
        receipt = pay(core_a, student, "100", accountant)
        client.force_login(accountant)
        cancel = f"/fees/receipts/{receipt.pk}/cancel/"
        assert client.get(cancel, HTTP_HOST=ALPHA).status_code == 403
        client.force_login(principal)
        page = client.get(f"/fees/receipts/{receipt.pk}/", HTTP_HOST=ALPHA).content.decode()
        assert "Cancel receipt" in page
        response = client.post(cancel, {"reason": "Duplicate"}, HTTP_HOST=ALPHA, follow=True)
        assert "CANCELLED" in response.content.decode()

    def test_another_colleges_receipt_is_not_found(
        self, client, core_a, core_b, college_b, make_student, make_user, accountant
    ):
        from apps.accounts.roles import Role

        other = make_student(core_b, "26CSE001")
        with college_context(college_b):
            dues.raise_dues(core_b["be_cse_batch"], core_b["year"])
        receipt = pay(core_b, other, "100", make_user(college_b, "b", roles=[Role.ACCOUNTS]))
        client.force_login(accountant)
        assert client.get(f"/fees/receipts/{receipt.pk}/", HTTP_HOST=ALPHA).status_code == 404
        assert client.get(f"/fees/collect/{other.pk}/", HTTP_HOST=ALPHA).status_code == 404

    def test_home_links_to_the_counter_for_accounts_only(self, client, accountant, office):
        client.force_login(accountant)
        assert "Take a fee payment" in client.get("/", HTTP_HOST=ALPHA).content.decode()
        client.force_login(office)
        assert "Take a fee payment" not in client.get("/", HTTP_HOST=ALPHA).content.decode()


@pytest.mark.parametrize(
    ("value", "text"),
    [("0", "0.00"), ("999", "999.00"), ("1500", "1,500.00"), ("123456789.5", "12,34,56,789.50")],
)
def test_indian_digit_grouping(value, text):
    from apps.fees.templatetags.fees import inr

    assert inr(Decimal(value)) == text
