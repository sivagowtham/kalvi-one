"""Settings for pytest and CI. Always PostgreSQL, never SQLite (decision D5)."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
os.environ.setdefault("DATABASE_URL", "postgres://kalvione:kalvione@localhost:5432/kalvione")

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = [".localhost", "testserver"]

# Fast hashing in tests only; production uses Argon2 (see base.py).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
