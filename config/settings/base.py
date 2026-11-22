"""Settings shared by every environment.

Values that differ between environments are read from environment variables
(see .env.example). Environment-specific modules (dev, test, prod) import from
here and override only what they must.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # KalviOne apps
    "apps.core",
    "apps.tenancy",
    "apps.accounts",
    "apps.audit",
    "apps.academics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.tenancy.middleware.TenantMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.audit.context.AuditContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# PostgreSQL only (decision D5). DATABASE_URL example:
# postgres://kalvione:kalvione@localhost:5432/kalvione
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# Multi-tenancy (D2, D12). A college is served on <slug>.<base domain>.
TENANT_BASE_DOMAINS = env.list("TENANT_BASE_DOMAINS", default=["localhost"])
# Hosts that serve the platform itself (no college), e.g. the bare domain.
TENANT_PLATFORM_HOSTS = env.list("TENANT_PLATFORM_HOSTS", default=["localhost", "127.0.0.1"])
# Dedicated deployment: serve this one college on every host. Empty for SaaS.
TENANT_DEDICATED_COLLEGE_SLUG = env("TENANT_DEDICATED_COLLEGE_SLUG", default="")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Users belong to one college; login is checked against the request's college (D6).
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.CollegeBackend"]
LOGIN_URL = "admin:login"
# Usernames are unique per college, not globally; CollegeBackend handles lookup (D6).
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}
