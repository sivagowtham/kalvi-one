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

# Field-level encryption for sensitive personal data such as Aadhaar (D18).
# FIELD_ENCRYPTION_KEYS: Fernet keys, comma-separated. The first encrypts; all decrypt,
# so a key can be rotated by putting the new key first. FIELD_HASH_KEY keys the HMAC
# used to find duplicates without decrypting. Production refuses to start without them.
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])
FIELD_HASH_KEY = env("FIELD_HASH_KEY", default="")

# Claude, for AI features (D32). Without a key the AI features are hidden; nothing else changes.
# The model is a setting per feature so it can be swapped without a code change.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
FEES_AI_MODEL = env("FEES_AI_MODEL", default="claude-haiku-5-5")

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
    "apps.students",
    "apps.admissions",
    "apps.fees",
    "apps.exams",
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
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"
# Wrong passwords for one username from one IP address before logins pause (D23).
LOGIN_FAILURE_LIMIT = env.int("LOGIN_FAILURE_LIMIT", default=5)
LOGIN_LOCKOUT_MINUTES = env.int("LOGIN_LOCKOUT_MINUTES", default=15)
# Emailed "set a new password" links stop working after this many seconds (D24).
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=60 * 60)
# Reset emails sent to one account per hour, to stop the form being used to flood an inbox.
PASSWORD_RESET_EMAILS_PER_HOUR = env.int("PASSWORD_RESET_EMAILS_PER_HOUR", default=3)
# Invite links for a first password last longer than reset links (D25).
INVITE_LINK_TIMEOUT = env.int("INVITE_LINK_TIMEOUT", default=7 * 24 * 60 * 60)
# Each college's web address, used in emails sent from admin or a command (D25).
# {slug} is the college subdomain and {base} the first TENANT_BASE_DOMAINS entry. A dedicated
# deployment can use a fixed address, e.g. https://erp.yourcollege.in
COLLEGE_URL_TEMPLATE = env("COLLEGE_URL_TEMPLATE", default="http://{slug}.{base}:8000")

# Email (D24). EMAIL_URL examples: consolemail:// (print to the console, the default),
# smtp+tls://user:password@smtp.zoho.in:587. See django-environ's email_url.
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="KalviOne <no-reply@kalvione.in>")
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

# The seed_demo command creates fake data; only development and tests allow it (D10).
ALLOW_DEMO_SEED = False
