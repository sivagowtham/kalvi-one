"""Per-college settings for the fees module, stored in College.config["fees"] (D13, D27).

Every key has a default here, so a college needs config only where it differs.
"""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {
    # The Tally company the daily file is meant for, shown to the accountant as a check.
    "tally_company": "",
    # Ledgers that collect GST on taxable fee heads. Fees inside Tamil Nadu are intra-state,
    # so tax is split into CGST and SGST.
    "gst_ledgers": {"cgst": "Output CGST", "sgst": "Output SGST"},
    # Placeholders: {code} college code, {fy} financial year such as 2026-27,
    # {seq} a running number per financial year, e.g. {seq:06} gives 000123.
    "receipt_number_pattern": "{code}/{fy}/{seq:06}",
    # Indian financial years start in April.
    "financial_year_start_month": 4,
    # Kinds of concession: [code, label, who pays]. "government" means the student owes
    # nothing for that share, but the college expects it from a government scholarship.
    # "college" means the college gives it up.
    "concession_types": [
        ["PMS", "Post-Matric Scholarship (SC/SCA/ST)", "government"],
        ["FG", "First graduate fee concession", "government"],
        ["GOVT_SCHOOL", "7.5% government school students (fees paid by government)", "government"],
        ["BC_MBC", "BC/MBC/DNC scholarship", "government"],
        ["MERIT", "Merit scholarship", "college"],
        ["STAFF_WARD", "Staff ward concession", "college"],
        ["SPORTS", "Sports concession", "college"],
        ["MGMT", "Management concession", "college"],
    ],
}

FUNDERS = {"government", "college"}


def setting(college, key: str) -> Any:
    return (college.config or {}).get("fees", {}).get(key, DEFAULTS[key])


def concession_types(college) -> dict[str, tuple[str, str]]:
    """Code to (label, who pays) for the college's concession types."""
    return {code: (label, funder) for code, label, funder in setting(college, "concession_types")}
