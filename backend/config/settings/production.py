"""Production: one HTTPS origin, Django behind the hosting platform's proxy.

Django serves the API, the admin and the built PWA (``config/frontend.py``).
Deployment, environment variables and recovery are described in
``docs/operations/production-runbook.md``.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.database import database_from_url
from config.frontend import MIMETYPES, add_headers, immutable_file

from .base import *  # noqa: F403
from .base import (
    ALLOWED_HOSTS,
    BASE_DIR,
    CSRF_TRUSTED_ORIGINS,
    DATABASES,
    MIDDLEWARE,
    SECRET_KEY,
    SILENCED_SYSTEM_CHECKS,
)

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set")
# Refuse a short, repetitive or copied-placeholder key at start-up. This
# replaces Django's security.W009 heuristic (50 characters), which warns about
# Render's generateValue: 256 random bits written as 44 base64 characters.
if (
    len(SECRET_KEY) < 40
    or len(set(SECRET_KEY)) < 20
    or SECRET_KEY.startswith("django-insecure-")
    or "replace-with" in SECRET_KEY
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be a random value of at least 40 characters, "
        "e.g. python -c 'import secrets; print(secrets.token_urlsafe(50))'"
    )
SILENCED_SYSTEM_CHECKS = [*SILENCED_SYSTEM_CHECKS, "security.W009"]
if not ALLOWED_HOSTS:
    # Otherwise every request is refused with 400, which is hard to diagnose.
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must name this site's host, e.g. app.example.org"
    )
if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must all be https://")

# Database: the five POSTGRES_* variables, or a platform's DATABASE_URL, never
# both (config/database.py). Connections are kept for a minute and checked
# before reuse, so a restarted database server costs one retry, not errors.
_database_url = database_from_url(os.environ)
if _database_url:
    DATABASES["default"].update(_database_url)
DATABASES["default"]["CONN_MAX_AGE"] = int(
    os.environ.get("CHARITYOS_DB_CONN_MAX_AGE", "60")
)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# The built PWA and the admin's static files, served by WhiteNoise straight
# after SecurityMiddleware (so HTTPS redirects and security headers apply).
MIDDLEWARE = [*MIDDLEWARE]
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
WHITENOISE_ROOT = Path(
    os.environ.get("CHARITYOS_FRONTEND_DIST") or BASE_DIR.parent / "frontend" / "dist"
)
WHITENOISE_INDEX_FILE = True
WHITENOISE_IMMUTABLE_FILE_TEST = immutable_file
WHITENOISE_ADD_HEADERS_FUNCTION = add_headers
WHITENOISE_MIMETYPES = MIMETYPES
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
