"""The Tally file: fee receipts as Receipt vouchers, and a list of the ledgers they use (D31).

The XML is Tally's own import format ("Import Data" envelope), which Tally Prime and Tally
ERP 9 both read through Import > Transactions (or Masters for the ledger list).
"""

from __future__ import annotations

import datetime as dt
from collections import OrderedDict
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import config
from .models import ZERO, FeeHead, PaymentAccount, PaymentMode, Receipt, TallyExport


def _text(parent, tag: str, value) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = str(value)
    return element


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _envelope(college, report: str) -> tuple[ET.Element, ET.Element]:
    """The import envelope; returns (root, the element messages go into)."""
    root = ET.Element("ENVELOPE")
    header = ET.SubElement(root, "HEADER")
    _text(header, "TALLYREQUEST", "Import Data")
    body = ET.SubElement(ET.SubElement(root, "BODY"), "IMPORTDATA")
    desc = ET.SubElement(body, "REQUESTDESC")
    _text(desc, "REPORTNAME", report)
    company = config.setting(college, "tally_company")
    if company:
        _text(ET.SubElement(desc, "STATICVARIABLES"), "SVCURRENTCOMPANY", company)
    return root, ET.SubElement(body, "REQUESTDATA")


def _to_bytes(root: ET.Element) -> bytes:
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def remote_id(receipt: Receipt) -> str:
    """A stable id, so Tally can find the same voucher again to cancel it."""
    return f"kalvione-{receipt.college.code}-receipt-{receipt.pk}"


def narration(receipt: Receipt) -> str:
    """Receipt number, roll number, name and payment reference. Never sensitive fields."""
    parts = [
        f"Fee receipt {receipt.number}",
        f"{receipt.student.roll_number} {receipt.student.name}",
        PaymentMode(receipt.mode).label + (f" {receipt.reference}" if receipt.reference else ""),
    ]
    return " | ".join(parts)


def ledger_amounts(receipt: Receipt) -> OrderedDict[str, Decimal]:
    """Credit per ledger: fee heads at their taxable value, then the GST ledgers."""
    gst = config.setting(receipt.college, "gst_ledgers")
    credits: OrderedDict[str, Decimal] = OrderedDict()
    cgst = sgst = ZERO
    for line in receipt.lines.select_related("head").order_by("head__sort_order", "pk"):
        ledger = line.head.tally_ledger
        credits[ledger] = credits.get(ledger, ZERO) + line.taxable_value
        cgst += line.cgst
        sgst += line.sgst
    if cgst:
        credits[gst["cgst"]] = credits.get(gst["cgst"], ZERO) + cgst
    if sgst:
        credits[gst["sgst"]] = credits.get(gst["sgst"], ZERO) + sgst
    return credits


def _ledger_entry(voucher, ledger: str, amount: Decimal, *, debit: bool) -> None:
    entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
    _text(entry, "LEDGERNAME", ledger)
    _text(entry, "ISDEEMEDPOSITIVE", "Yes" if debit else "No")
    # Tally writes debits as negative amounts and credits as positive ones.
    _text(entry, "AMOUNT", _amount(-amount if debit else amount))


def receipt_voucher(message, receipt: Receipt) -> None:
    voucher_type = config.setting(receipt.college, "tally_voucher_type")
    voucher = ET.SubElement(
        message,
        "VOUCHER",
        REMOTEID=remote_id(receipt),
        VCHTYPE=voucher_type,
        ACTION="Create",
        OBJVIEW="Accounting Voucher View",
    )
    _text(voucher, "DATE", f"{receipt.date:%Y%m%d}")
    _text(voucher, "EFFECTIVEDATE", f"{receipt.date:%Y%m%d}")
    _text(voucher, "VOUCHERTYPENAME", voucher_type)
    _text(voucher, "VOUCHERNUMBER", receipt.number)
    if receipt.reference:
        _text(voucher, "REFERENCE", receipt.reference)
    _text(voucher, "NARRATION", narration(receipt))
    _text(voucher, "PERSISTEDVIEW", "Accounting Voucher View")
    _ledger_entry(voucher, receipt.account.tally_ledger, receipt.amount, debit=True)
    credits = ledger_amounts(receipt)
    if sum(credits.values(), ZERO) != receipt.amount:
        raise ValidationError(f"Receipt {receipt.number} does not add up; it was not exported.")
    for ledger, amount in credits.items():
        _ledger_entry(voucher, ledger, amount, debit=False)


def cancel_voucher(message, receipt: Receipt) -> None:
    """Tally finds the voucher by its date, type and number, as its import guide describes."""
    voucher = ET.SubElement(
        message,
        "VOUCHER",
        DATE=f"{receipt.date:%d-%b-%Y}",
        TAGNAME="Voucher Number",
        TAGVALUE=receipt.number,
        VCHTYPE=config.setting(receipt.college, "tally_voucher_type"),
        ACTION="Cancel",
    )
    _text(voucher, "NARRATION", f"Cancelled: {receipt.cancel_reason}")


def pending(up_to: dt.date):
    """(receipts to send, cancellations to send) up to and including ``up_to``.

    A receipt cancelled before it was ever sent is never sent at all.
    """
    receipts = Receipt.objects.filter(
        date__lte=up_to, status=Receipt.Status.VALID, tally_export__isnull=True
    )
    cancellations = Receipt.objects.filter(
        status=Receipt.Status.CANCELLED,
        tally_export__isnull=False,
        tally_cancel_export__isnull=True,
    )
    return receipts, cancellations


def build_file(export: TallyExport) -> bytes:
    """The XML for an export. Downloading it again gives the same vouchers."""
    root, data = _envelope(export.college, "Vouchers")
    message = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
    related = ("student", "account", "college")
    for receipt in export.sent_receipts.select_related(*related).order_by("date", "number"):
        receipt_voucher(message, receipt)
    for receipt in export.sent_cancellations.select_related(*related).order_by("date", "number"):
        cancel_voucher(message, receipt)
    return _to_bytes(root)


def create_export(user, up_to: dt.date | None = None) -> TallyExport:
    """Mark everything pending as sent in a new export, and return it."""
    up_to = up_to or timezone.localdate()
    with transaction.atomic():
        receipts, cancellations = pending(up_to)
        receipts = list(receipts.select_for_update())
        cancellations = list(cancellations.select_for_update())
        if not receipts and not cancellations:
            raise ValidationError("There is nothing new to send to Tally.")
        export = TallyExport.objects.create(
            up_to=up_to,
            created_by=user,
            receipts=len(receipts),
            cancellations=len(cancellations),
            total=sum((r.amount for r in receipts), ZERO),
        )
        for receipt in receipts:
            receipt.tally_export = export
            receipt.save(update_fields=["tally_export"])
        for receipt in cancellations:
            receipt.tally_cancel_export = export
            receipt.save(update_fields=["tally_cancel_export"])
        build_file(export)  # refuse the export now if any voucher would not add up
    return export


def ledger_file(college) -> bytes:
    """Every ledger the vouchers use, to create missing ones in Tally in one import."""
    groups = config.setting(college, "tally_groups")
    gst = config.setting(college, "gst_ledgers")
    root, data = _envelope(college, "All Masters")
    message = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
    seen = set()

    def ledger(name: str, parent: str, **extra) -> None:
        if name in seen:
            return
        seen.add(name)
        element = ET.SubElement(message, "LEDGER", NAME=name, ACTION="Create")
        names = ET.SubElement(element, "NAME.LIST")
        _text(names, "NAME", name)
        _text(element, "PARENT", parent)
        for tag, value in extra.items():
            _text(element, tag, value)

    for head in FeeHead.objects.filter(is_active=True):
        ledger(head.tally_ledger, groups["fee"])
    for account in PaymentAccount.objects.filter(is_active=True):
        ledger(account.tally_ledger, groups["cash" if account.kind == "cash" else "bank"])
    if FeeHead.objects.filter(gst_rate__gt=0).exists():
        ledger(gst["cgst"], groups["gst"], TAXTYPE="GST", GSTDUTYHEAD="Central Tax")
        ledger(gst["sgst"], groups["gst"], TAXTYPE="GST", GSTDUTYHEAD="State Tax")
    return _to_bytes(root)
