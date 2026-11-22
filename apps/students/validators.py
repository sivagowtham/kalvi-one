"""Validators for Indian identifiers and contact details."""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

mobile_validator = RegexValidator(r"^[6-9]\d{9}$", "Enter a 10-digit Indian mobile number.")
pincode_validator = RegexValidator(r"^[1-9]\d{5}$", "Enter a 6-digit PIN code.")

# Verhoeff tables: Aadhaar's last digit is a Verhoeff check digit.
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(digits: str) -> str:
    check = 0
    for i, digit in enumerate(reversed(digits)):
        check = _D[check][_P[(i + 1) % 8][int(digit)]]
    return str(_INV[check])


def verhoeff_is_valid(digits: str) -> bool:
    check = 0
    for i, digit in enumerate(reversed(digits)):
        check = _D[check][_P[i % 8][int(digit)]]
    return check == 0


def normalise_aadhaar(value: str) -> str:
    """Strip spaces and dashes, then check the form and the Verhoeff check digit."""
    digits = "".join(ch for ch in value if ch not in " -")
    if not (len(digits) == 12 and digits.isdigit() and digits[0] not in "01"):
        raise ValidationError("An Aadhaar number has 12 digits and does not start with 0 or 1.")
    if not verhoeff_is_valid(digits):
        raise ValidationError("This Aadhaar number fails its check digit. Check for a typo.")
    return digits
