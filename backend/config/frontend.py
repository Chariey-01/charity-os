"""Serving the built PWA (``frontend/dist``) from Django in production.

One origin serves everything, which the PWA and the session-cookie sign-in both
need: WhiteNoise serves ``frontend/dist`` at ``/`` (``WHITENOISE_ROOT``) and the
admin's files at ``/static/``; Django answers ``/api/`` and ``/admin/``. The app
routes with the URL hash (``/#/today``), so a refresh always asks for ``/`` and
no catch-all route is needed.

Caching, chosen so a deployment reaches phones promptly and never half-way:

* ``index.html``, ``sw.js`` and ``manifest.webmanifest``: ``no-cache``. The
  browser revalidates each time, so a new release is seen on the next load.
  The service worker keeps its own last-good copy for offline use.
* ``/assets/*`` built by Vite carry a content hash in their names: cached for a
  year as immutable. Admin files collected by Django's manifest storage too.
* Everything else (icons): WhiteNoise's default of 60 seconds.

``index.html`` also gets a Content-Security-Policy. The app loads scripts,
styles, images and data only from its own origin; React sets ``style``
attributes, hence ``'unsafe-inline'`` for styles only.
"""

import re

from django.conf import settings
from django.core.checks import Error, register

NO_CACHE = frozenset({"index.html", "sw.js", "manifest.webmanifest"})
# Vite: /assets/index-BSiiNENh.js. Django's ManifestStaticFilesStorage:
# /static/admin/css/base.1e7f6d0d6f2a.css.
HASHED_FRONTEND_ASSET = re.compile(r"^/assets/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")
HASHED_STATIC_FILE = re.compile(r"^/static/.+\.[0-9a-f]{12}\.[A-Za-z0-9]+$")

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def immutable_file(path, url):
    """``WHITENOISE_IMMUTABLE_FILE_TEST``: only content-hashed file names."""
    return bool(HASHED_FRONTEND_ASSET.match(url) or HASHED_STATIC_FILE.match(url))


# WhiteNoise has no type for .webmanifest and would send application/octet-stream.
MIMETYPES = {".webmanifest": "application/manifest+json"}


def add_headers(headers, path, url):
    """``WHITENOISE_ADD_HEADERS_FUNCTION``: see the module docstring."""
    # WhiteNoise registers index.html under its directory's URL ("/").
    name = "index.html" if url.endswith("/") else url.rsplit("/", 1)[-1]
    if name in NO_CACHE:
        headers["Cache-Control"] = "no-cache"
    if name == "index.html":
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        headers["X-Frame-Options"] = "DENY"


@register(deploy=True)
def check_frontend_build(app_configs, **kwargs):
    """``check --deploy``: production must have a built frontend to serve."""
    root = getattr(settings, "WHITENOISE_ROOT", None)
    if root is None:
        return []
    if not (root / "index.html").is_file():
        return [
            Error(
                f"No built frontend at {root}.",
                hint="Run `npm ci && npm run build` in frontend/, or set "
                "CHARITYOS_FRONTEND_DIST to the build's directory.",
                id="charityos.E001",
            )
        ]
    return []
