"""Settings for pytest and CI. Always PostgreSQL, never SQLite (decision D5)."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
# Fake keys for tests and CI only (D10, D18). Never use them anywhere else.
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEYS",
    "dGVzdC1vbmx5LWtleS1kby1ub3QtdXNlLWFueXdoZXI=",
)
os.environ.setdefault("FIELD_HASH_KEY", "test-only-hash-key")
os.environ.setdefault("DATABASE_URL", "postgres://kalvione:kalvione@localhost:5432/kalvione")

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = [".localhost", "testserver"]

# Fast hashing in tests only; production uses Argon2 (see base.py).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

INSTALLED_APPS = [*INSTALLED_APPS, "tests.testapp"]  # noqa: F405

TENANT_BASE_DOMAINS = ["localhost"]
TENANT_PLATFORM_HOSTS = ["testserver", "localhost"]
TENANT_DEDICATED_COLLEGE_SLUG = ""
ROOT_URLCONF = "tests.urls"
ALLOW_DEMO_SEED = True
COLLEGE_URL_TEMPLATE = "http://{slug}.{base}"
