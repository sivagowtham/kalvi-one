"""Local development settings (used by manage.py and Docker Compose)."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
# Each college will be served on its own subdomain; *.localhost resolves to 127.0.0.1.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[".localhost", "127.0.0.1"])

ALLOW_DEMO_SEED = True
