"""Field-level encryption and keyed hashes for sensitive personal data (D18)."""

from __future__ import annotations

import hashlib
import hmac
from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@cache
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS is not set (D18).")
    return MultiFernet([Fernet(key) for key in keys])


def _keys() -> tuple[str, ...]:
    return tuple(settings.FIELD_ENCRYPTION_KEYS)


def encrypt(value: str) -> str:
    """Encrypt ``value`` with the first key. Empty stays empty."""
    if not value:
        return ""
    return _fernet(_keys()).encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt with any configured key. Empty stays empty."""
    if not token:
        return ""
    try:
        return _fernet(_keys()).decrypt(token.encode()).decode()
    except InvalidToken as error:
        raise ImproperlyConfigured("A stored value cannot be decrypted with these keys.") from error


def rotate(token: str) -> str:
    """Re-encrypt ``token`` with the current first key."""
    return _fernet(_keys()).rotate(token.encode()).decode() if token else ""


def keyed_hash(value: str) -> str:
    """HMAC-SHA256 of ``value``, for finding duplicates without decrypting. Empty stays empty."""
    if not value:
        return ""
    key = settings.FIELD_HASH_KEY
    if not key:
        raise ImproperlyConfigured("FIELD_HASH_KEY is not set (D18).")
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
