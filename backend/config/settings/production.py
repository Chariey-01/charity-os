"""Production: one HTTPS origin, Django behind the hosting platform's proxy.

Two layouts, chosen with ``CHARITYOS_FRONTEND``:

* ``django`` (default): Django serves the API, the admin and the built PWA
  (``config/frontend.py``). See ``docs/operations/production-runbook.md``.
* ``external``: Cloudflare serves the PWA and forwards ``/api/``, ``/admin/``
  and ``/static/`` here, so the site is still one origin. Django then answers
  only requests carrying ``CHARITYOS_EDGE_PROXY_SECRET``
  (``config/edge_proxy.py``). See ``docs/operations/cloudflare-deployment.md``.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.database import database_from_url
from config.edge_proxy import validate_secret
from config.frontend import MIMETYPES, add_headers, immutable_file

from .base import *  # noqa: F403
from .base import (
    ALLOWED_HOSTS,
    BASE_DIR,
    CHARITYOS_EDGE_PROXY_SECRET,
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

FRONTEND_MODE = os.environ.get("CHARITYOS_FRONTEND", "django").strip() or "django"
if FRONTEND_MODE not in ("django", "external"):
    raise ImproperlyConfigured("CHARITYOS_FRONTEND must be django or external")
validate_secret(CHARITYOS_EDGE_PROXY_SECRET)  # at start-up, not on a request
if FRONTEND_MODE == "external":
    # This host has a public address of its own; without the secret anyone
    # could reach the API and the admin around Cloudflare.
    if not CHARITYOS_EDGE_PROXY_SECRET:
        raise ImproperlyConfigured(
            "CHARITYOS_FRONTEND=external needs CHARITYOS_EDGE_PROXY_SECRET, the "
            "value the Cloudflare Worker sends (docs/operations/"
            "cloudflare-deployment.md)."
        )
    # The browser's origin is the Worker's, not this host's.
    if not CSRF_TRUSTED_ORIGINS:
        raise ImproperlyConfigured(
            "CHARITYOS_FRONTEND=external needs DJANGO_CSRF_TRUSTED_ORIGINS set to "
            "the site's https:// address on Cloudflare."
        )

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
# With an external frontend WhiteNoise serves only the admin's files.
WHITENOISE_ROOT = (
    None
    if FRONTEND_MODE == "external"
    else Path(
        os.environ.get("CHARITYOS_FRONTEND_DIST")
        or BASE_DIR.parent / "frontend" / "dist"
    )
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
