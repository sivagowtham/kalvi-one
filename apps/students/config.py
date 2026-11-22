"""Per-college settings for the students module, stored in College.config["students"] (D20).

Every key has a Tamil Nadu default here, so a college needs config only where it differs.
"""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {
    # Tamil Nadu reservation categories as used on community certificates and in TNEA.
    "communities": [
        ["OC", "Open Competition"],
        ["BC", "Backward Class"],
        ["BCM", "Backward Class (Muslim)"],
        ["MBC", "Most Backward Class and Denotified Community"],
        ["SC", "Scheduled Caste"],
        ["SCA", "Scheduled Caste (Arunthathiyar)"],
        ["ST", "Scheduled Tribe"],
    ],
    "quotas": [
        ["GOVT", "Government (counselling)"],
        ["MGMT", "Management"],
    ],
    # Placeholders: {yy} admission year, {dept} department code, {prog} programme code,
    # {seq} a running number per filled-in prefix, e.g. {seq:03} gives 001.
    "roll_number_pattern": "{yy}{dept}{seq:03}",
    "admission_number_pattern": "A{yy}{seq:04}",
    "application_number_pattern": "APP{yy}{seq:04}",
    "required_documents": [
        ["TC", "Transfer certificate"],
        ["SSLC", "10th mark sheet"],
        ["HSC", "12th or diploma mark sheet"],
        ["COMMUNITY", "Community certificate"],
    ],
    "consent_notice_version": "v1",
}


def setting(college, key: str) -> Any:
    return (college.config or {}).get("students", {}).get(key, DEFAULTS[key])


def choices(college, key: str) -> list[tuple[str, str]]:
    return [(code, label) for code, label in setting(college, key)]


def codes(college, key: str) -> set[str]:
    return {code for code, _ in setting(college, key)}
