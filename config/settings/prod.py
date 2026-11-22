"""Production settings. Every secret and host comes from the environment."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env

DEBUG = False

if not FIELD_ENCRYPTION_KEYS or not FIELD_HASH_KEY:  # noqa: F405
    raise ImproperlyConfigured("Set FIELD_ENCRYPTION_KEYS and FIELD_HASH_KEY (decision D18).")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
