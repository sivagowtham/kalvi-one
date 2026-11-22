"""Field encryption, keyed hashes and Aadhaar validation (D18)."""

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import override_settings

from apps.students import crypto
from apps.students.fakes import fake_aadhaar
from apps.students.validators import normalise_aadhaar, verhoeff_is_valid


def test_round_trip_and_empty_values():
    token = crypto.encrypt("hello")
    assert token != "hello"
    assert crypto.decrypt(token) == "hello"
    assert crypto.encrypt("") == "" and crypto.decrypt("") == ""


def test_key_rotation_keeps_old_values_readable():
    old = Fernet.generate_key().decode()
    new = Fernet.generate_key().decode()
    with override_settings(FIELD_ENCRYPTION_KEYS=[old]):
        token = crypto.encrypt("secret")
    with override_settings(FIELD_ENCRYPTION_KEYS=[new, old]):
        assert crypto.decrypt(token) == "secret"
        rotated = crypto.rotate(token)
    with override_settings(FIELD_ENCRYPTION_KEYS=[new]):
        assert crypto.decrypt(rotated) == "secret"
        with pytest.raises(ImproperlyConfigured):
            crypto.decrypt(token)
    assert crypto.rotate("") == ""


def test_missing_keys_fail_loudly():
    with override_settings(FIELD_ENCRYPTION_KEYS=[]), pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")
    with override_settings(FIELD_HASH_KEY=""), pytest.raises(ImproperlyConfigured):
        crypto.keyed_hash("x")


def test_keyed_hash_is_stable_and_keyed():
    assert crypto.keyed_hash("123") == crypto.keyed_hash("123")
    assert len(crypto.keyed_hash("123")) == 64
    assert crypto.keyed_hash("") == ""
    with override_settings(FIELD_HASH_KEY="another"):
        other = crypto.keyed_hash("123")
    assert other != crypto.keyed_hash("123")


def test_fake_aadhaar_numbers_are_valid_and_distinct():
    numbers = {fake_aadhaar(n) for n in range(50)}
    assert len(numbers) == 50
    assert all(verhoeff_is_valid(n) for n in numbers)


def test_normalise_aadhaar():
    number = fake_aadhaar(7)
    spaced = f"{number[:4]} {number[4:8]}-{number[8:]}"
    assert normalise_aadhaar(spaced) == number
    typo = number[:-1] + str((int(number[-1]) + 1) % 10)
    for bad in [typo, "12345", "012345678901", "abcdabcdabcd"]:
        with pytest.raises(ValidationError):
            normalise_aadhaar(bad)
