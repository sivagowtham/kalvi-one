"""Fake identifiers for seed data and tests only (D10)."""

from .validators import verhoeff_check_digit


def fake_aadhaar(serial: int) -> str:
    """A 12-digit number that passes the Verhoeff check, starting 9999 so it reads as fake."""
    body = f"9999{serial:07d}"
    return body + verhoeff_check_digit(body)
