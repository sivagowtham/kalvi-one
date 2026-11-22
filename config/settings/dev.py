"""Local development settings (used by manage.py and Docker Compose)."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
# Each college will be served on its own subdomain; *.localhost resolves to 127.0.0.1.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[".localhost", "127.0.0.1"])

ALLOW_DEMO_SEED = True

# Development-only fallback keys, so an existing .env keeps working (D18). Never use them on
# a server: prod.py refuses to start without real keys from the environment.
FIELD_ENCRYPTION_KEYS = FIELD_ENCRYPTION_KEYS or ["Hz1aogYy1NXrzWYsvwllmjgpmjiUI_O4eIEEEKcSqew="]  # noqa: F405
FIELD_HASH_KEY = FIELD_HASH_KEY or "dev-only-hash-key-change-me"  # noqa: F405
