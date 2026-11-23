"""The daily Tally file and the ledger list (D31)."""

from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest
from django.core.exceptions import ValidationError

from apps.fees import dues, receipts, tally
from apps.fees.models import Receipt, TallyExport
from apps.students.fakes import fake_aadhaar
from apps.tenancy.context import NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"


@pytest.fixture
def student(college_a, core_a, make_student):
    student = make_student(core_a, "26CSE001", name="KAVYA")
    with college_context(college_a):
        student.set_secret("aadhaar", fake_aadhaar(5))
        student.save()
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


def parse(xml: bytes) -> ET.Element:
    return ET.fromstring(xml)  # noqa: S314  (our own output, never an uploaded file)


def vouchers(xml: bytes):
    root = parse(xml)
    return root.findall(".//VOUCHER")


def entries(voucher):
    return [
        (e.findtext("LEDGERNAME"), e.findtext("ISDEEMEDPOSITIVE"), e.findtext("AMOUNT"))
        for e in voucher.findall("ALLLEDGERENTRIES.LIST")
    ]


def test_receipts_become_receipt_vouchers(college_a, core_a, student, accountant):
    receipt = pay(core_a, student, "26000", accountant, "upi", "bank", "UPI777")
    with college_context(college_a):
        export = tally.create_export(accountant)
        xml = tally.build_file(export)
    assert xml.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    root = parse(xml)
    assert root.findtext("HEADER/TALLYREQUEST") == "Import Data"
    assert root.findtext(".//REPORTNAME") == "Vouchers"
    (voucher,) = vouchers(xml)
    assert voucher.get("VCHTYPE") == "Receipt" and voucher.get("ACTION") == "Create"
    assert voucher.get("REMOTEID") == f"kalvione-ACE-receipt-{receipt.pk}"
    assert voucher.findtext("DATE") == f"{receipt.date:%Y%m%d}"
    assert voucher.findtext("VOUCHERNUMBER") == receipt.number
    assert voucher.findtext("REFERENCE") == "UPI777"
    assert voucher.findtext("NARRATION") == (
        f"Fee receipt {receipt.number} | 26CSE001 KAVYA | UPI UPI777"
    )
    assert entries(voucher) == [
        ("Fake Bank A/c", "Yes", "-26000.00"),
        ("Tuition Fees", "No", "25000.00"),
        ("Exam Fees", "No", "1000.00"),
    ]
    assert fake_aadhaar(5).encode() not in xml and b"aadhaar" not in xml.lower()
    assert (export.receipts, export.cancellations, export.total) == (1, 0, Decimal("26000"))


def test_gst_goes_to_its_own_ledgers(college_a, core_a, student, accountant):
    with college_context(college_a):
        exam = core_a["exam"]
        exam.gst_rate, exam.hsn_sac = Decimal("18"), "999293"
        exam.save()
    pay(core_a, student, "26500", accountant)
    with college_context(college_a):
        (voucher,) = vouchers(tally.build_file(tally.create_export(accountant)))
    assert entries(voucher) == [
        ("Cash", "Yes", "-26500.00"),
        ("Tuition Fees", "No", "25000.00"),
        ("Exam Fees", "No", "1271.19"),
        ("Output CGST", "No", "114.41"),
        ("Output SGST", "No", "114.40"),
    ]


def test_each_receipt_is_sent_once_and_files_can_be_downloaded_again(
    college_a, core_a, student, accountant
):
    pay(core_a, student, "100", accountant)
    with college_context(college_a):
        first = tally.create_export(accountant)
        with pytest.raises(ValidationError):
            tally.create_export(accountant)
    pay(core_a, student, "200", accountant)
    with college_context(college_a):
        second = tally.create_export(accountant)
        assert len(vouchers(tally.build_file(second))) == 1
        assert tally.build_file(first) == tally.build_file(first)
        assert TallyExport.objects.count() == 2


def test_cancellations_follow_only_receipts_already_sent(
    college_a, core_a, student, accountant, principal
):
    sent = pay(core_a, student, "100", accountant)
    with college_context(college_a):
        tally.create_export(accountant)
    never_sent = pay(core_a, student, "50", accountant)
    with college_context(college_a):
        receipts.cancel(sent, principal, "Wrong amount")
        receipts.cancel(never_sent, principal, "Typed twice")
        export = tally.create_export(accountant)
        (voucher,) = vouchers(tally.build_file(export))
        never_sent.refresh_from_db()
    assert (export.receipts, export.cancellations) == (0, 1)
    assert voucher.attrib == {
        "DATE": f"{sent.date:%d-%b-%Y}",
        "TAGNAME": "Voucher Number",
        "TAGVALUE": sent.number,
        "VCHTYPE": "Receipt",
        "ACTION": "Cancel",
    }
    assert voucher.findtext("NARRATION") == "Cancelled: Wrong amount"
    assert never_sent.tally_export is None


def test_company_name_is_set_when_configured(college_a, core_a, student, accountant):
    college_a.config = {
        "fees": {"tally_company": "Alpha Trust 2026-27", "tally_voucher_type": "Fee Receipt"}
    }
    college_a.save()
    pay(core_a, student, "100", accountant)
    with college_context(college_a):
        xml = tally.build_file(tally.create_export(accountant))
    assert parse(xml).findtext(".//SVCURRENTCOMPANY") == "Alpha Trust 2026-27"
    (voucher,) = vouchers(xml)
    assert voucher.get("VCHTYPE") == voucher.findtext("VOUCHERTYPENAME") == "Fee Receipt"


def test_ledger_list(college_a, core_a):
    with college_context(college_a):
        root = parse(tally.ledger_file(college_a))
        ledgers = {e.get("NAME"): e.findtext("PARENT") for e in root.iter("LEDGER")}
        assert ledgers == {
            "Tuition Fees": "Direct Incomes",
            "Exam Fees": "Direct Incomes",
            "Cash": "Cash-in-Hand",
            "Fake Bank A/c": "Bank Accounts",
        }
        exam = core_a["exam"]
        exam.gst_rate, exam.hsn_sac = Decimal("5"), "4901"
        exam.save()
        root = parse(tally.ledger_file(college_a))
    gst = {e.get("NAME"): e.findtext("GSTDUTYHEAD") for e in root.iter("LEDGER")}
    assert gst["Output CGST"] == "Central Tax" and gst["Output SGST"] == "State Tax"


def test_exports_are_isolated_per_college(
    college_a, college_b, core_a, core_b, student, accountant, make_student, make_user
):
    from apps.accounts.roles import Role

    pay(core_a, student, "100", accountant)
    other = make_student(core_b, "26CSE001")
    other_user = make_user(college_b, "b", roles=[Role.ACCOUNTS])
    with college_context(college_b):
        dues.raise_dues(core_b["be_cse_batch"], core_b["year"])
    pay(core_b, other, "100", other_user)
    with college_context(college_a):
        a = tally.create_export(accountant)
        assert Receipt.objects.filter(tally_export=a).count() == 1
    with college_context(college_b):
        assert not TallyExport.objects.exists()
        b = tally.create_export(other_user)
        assert len(vouchers(tally.build_file(b))) == 1
    with pytest.raises(NoCollegeSelected):
        TallyExport.objects.count()


def test_tally_page(client, core_a, student, accountant, office):
    pay(core_a, student, "26000", accountant)
    client.force_login(office)
    assert client.get("/fees/tally/", HTTP_HOST=ALPHA).status_code == 403
    client.force_login(accountant)
    page = client.get("/fees/tally/", HTTP_HOST=ALPHA).content.decode()
    assert "<strong>1</strong> receipt (₹26,000.00)" in page
    done = client.post("/fees/tally/", HTTP_HOST=ALPHA, follow=True).content.decode()
    assert "Tally file made with 1 receipt(s)" in done
    with college_context(student.college):
        export = TallyExport.objects.get()
    download = client.get(f"/fees/tally/{export.pk}/download/", HTTP_HOST=ALPHA)
    assert download["Content-Disposition"].startswith('attachment; filename="tally-receipts-ace-')
    assert len(vouchers(download.content)) == 1
    again = client.post("/fees/tally/", HTTP_HOST=ALPHA, follow=True).content.decode()
    assert "There is nothing new to send to Tally." in again
    ledgers = client.get("/fees/tally/ledgers.xml", HTTP_HOST=ALPHA)
    assert b"Tuition Fees" in ledgers.content
