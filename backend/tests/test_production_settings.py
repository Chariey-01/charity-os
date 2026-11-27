"""Production settings: the platform's DATABASE_URL, start-up guards and
serving the built PWA (config/database.py, config/frontend.py)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client

from config import frontend
from config.database import database_from_url, parse_database_url

BACKEND = Path(__file__).resolve().parents[1]
STRONG_KEY = "Zq3vX8pL2mN7rT1wY6sB4dF9gH0jK5cV8nM2xQ7eR1t="  # 44 chars, like Render's

# ---------------------------------------------------------------- DATABASE_URL


def test_database_url_gives_every_field():
    fields = parse_database_url(
        "postgresql://char%40os:p%3Ass%2Fw0rd@dpg-abc123-a:6543/charityos"
    )
    assert fields == {
        "NAME": "charityos",
        "USER": "char@os",
        "PASSWORD": "p:ss/w0rd",
        "HOST": "dpg-abc123-a",
        "PORT": "6543",
        "OPTIONS": {},
    }


def test_database_url_defaults_port_and_reads_sslmode():
    fields = parse_database_url("postgres://u:p@db.internal/app?sslmode=require")
    assert fields["PORT"] == "5432"
    assert fields["OPTIONS"] == {"sslmode": "require"}


@pytest.mark.parametrize(
    "url",
    [
        "mysql://u:p@h/db",
        "postgresql://u:p@h/",
        "postgresql://h/db",
        "postgresql://u:p@/db",
        "postgresql://u:p@h:notaport/db",
        "postgresql://u:p@h/db/extra",
        "postgresql://u:p@h/db?sslmode=sometimes",
        "postgresql://u:p@h/db?options=-c%20x",
    ],
)
def test_database_url_refuses_what_it_cannot_honour(url):
    with pytest.raises(ImproperlyConfigured) as error:
        parse_database_url(url)
    assert "p@" not in str(error.value)  # the URL (with its password) is never echoed


def test_database_url_and_postgres_variables_are_never_both_used():
    environ = {
        "DATABASE_URL": "postgresql://u:secret@h/db",
        "POSTGRES_HOST": "other",
        "POSTGRES_DB": "",
    }
    with pytest.raises(ImproperlyConfigured) as error:
        database_from_url(environ)
    assert "POSTGRES_HOST" in str(error.value)
    assert "POSTGRES_DB" not in str(error.value)  # empty means unset
    assert "secret" not in str(error.value)


def test_no_database_url_means_postgres_variables():
    assert database_from_url({"DATABASE_URL": "  ", "POSTGRES_HOST": "h"}) is None


# ---------------------------------------------------------- production settings

PROBE = """
import json
from django.conf import settings
db = settings.DATABASES["default"]
print(json.dumps({
    "debug": settings.DEBUG,
    "db": [db["NAME"], db["USER"], db["HOST"], db["PORT"], db["OPTIONS"]],
    "conn": [db["CONN_MAX_AGE"], db["CONN_HEALTH_CHECKS"]],
    "middleware": settings.MIDDLEWARE[:3],
    "root": str(settings.WHITENOISE_ROOT),
    "cookies": [settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE],
    "redirect": settings.SECURE_SSL_REDIRECT,
}))
"""


def load_production(**overrides):
    """Import production settings in a fresh interpreter with ``overrides``."""
    environ = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("POSTGRES_", "DJANGO_", "DATABASE_", "CHARITYOS_"))
    }
    # Explicitly empty, so the checkout's .env (load_dotenv) cannot fill them in.
    environ.update({name: "" for name in ("POSTGRES_DB", "POSTGRES_USER")})
    environ.update({name: "" for name in ("POSTGRES_PASSWORD", "POSTGRES_HOST")})
    environ.update({"POSTGRES_PORT": "", "DJANGO_CSRF_TRUSTED_ORIGINS": ""})
    environ.update(
        DJANGO_SETTINGS_MODULE="config.settings.production",
        DJANGO_SECRET_KEY=STRONG_KEY,
        DJANGO_ALLOWED_HOSTS="charityos.onrender.com",
        DATABASE_URL="postgresql://charityos:pw@dpg-x-a/charityos",
    )
    environ.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()\n" + PROBE],
        cwd=BACKEND,
        env=environ,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_production_settings_use_the_platform_database_and_serve_the_pwa():
    result = load_production(CHARITYOS_FRONTEND_DIST="/srv/dist")
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    assert loaded["debug"] is False
    assert loaded["db"] == ["charityos", "charityos", "dpg-x-a", "5432", {}]
    assert loaded["conn"] == [60, True]
    assert loaded["middleware"] == [
        "config.health_probe.HealthProbeMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
    ]
    assert loaded["root"] == "/srv/dist"
    assert loaded["cookies"] == [True, True]
    assert loaded["redirect"] is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"DJANGO_SECRET_KEY": ""}, "DJANGO_SECRET_KEY must be set"),
        ({"DJANGO_SECRET_KEY": "short-key"}, "at least 40 characters"),
        ({"DJANGO_SECRET_KEY": "ab" * 30}, "at least 40 characters"),
        (
            {"DJANGO_SECRET_KEY": "django-insecure-" + STRONG_KEY},
            "at least 40 characters",
        ),
        ({"DJANGO_ALLOWED_HOSTS": ""}, "DJANGO_ALLOWED_HOSTS must name"),
        (
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://charityos.onrender.com"},
            "must all be https://",
        ),
        ({"POSTGRES_HOST": "localhost"}, "are both set"),
    ],
)
def test_production_settings_refuse_to_start_misconfigured(overrides, message):
    result = load_production(**overrides)
    assert result.returncode != 0
    assert message in result.stderr
    assert "pw@" not in result.stderr


# ---------------------------------------------------------------- PWA serving


@pytest.fixture
def built_frontend(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "icons").mkdir()
    (dist / "index.html").write_text("<!doctype html><title>CharityOS</title>")
    (dist / "sw.js").write_text("self.addEventListener('fetch', () => {});")
    (dist / "manifest.webmanifest").write_text('{"name": "CharityOS"}')
    (dist / "assets" / "index-BSiiNENh.js").write_text("console.log(1)")
    (dist / "icons" / "icon-192.png").write_bytes(b"\x89PNG\r\n")
    return dist


@pytest.fixture
def pwa_client(settings, built_frontend, tmp_path):
    settings.MIDDLEWARE = [
        *settings.MIDDLEWARE[:2],
        "whitenoise.middleware.WhiteNoiseMiddleware",
        *settings.MIDDLEWARE[2:],
    ]
    settings.WHITENOISE_ROOT = built_frontend
    settings.WHITENOISE_INDEX_FILE = True
    settings.WHITENOISE_IMMUTABLE_FILE_TEST = frontend.immutable_file
    settings.WHITENOISE_ADD_HEADERS_FUNCTION = frontend.add_headers
    settings.WHITENOISE_MIMETYPES = frontend.MIMETYPES
    settings.STATIC_ROOT = tmp_path / "static"
    (tmp_path / "static").mkdir()
    settings.ALLOWED_HOSTS = ["testserver"]
    return Client()


def test_the_app_shell_is_served_at_the_root_and_always_revalidated(pwa_client):
    response = pwa_client.get("/")
    assert response.status_code == 200
    assert b"<title>CharityOS</title>" in b"".join(response.streaming_content)
    assert response["Cache-Control"] == "no-cache"
    assert response["Content-Type"].startswith("text/html")
    assert "script-src 'self'" in response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert pwa_client.get("/index.html").status_code == 302  # one URL for the shell


def test_service_worker_and_manifest_are_always_revalidated(pwa_client):
    worker = pwa_client.get("/sw.js")
    assert worker.status_code == 200
    assert worker["Cache-Control"] == "no-cache"
    assert "javascript" in worker["Content-Type"]
    manifest = pwa_client.get("/manifest.webmanifest")
    assert manifest["Cache-Control"] == "no-cache"
    assert manifest["Content-Type"] == "application/manifest+json"


def test_hashed_assets_are_immutable_and_icons_short_lived(pwa_client):
    asset = pwa_client.get("/assets/index-BSiiNENh.js")
    assert asset.status_code == 200
    assert "immutable" in asset["Cache-Control"]
    icon = pwa_client.get("/icons/icon-192.png")
    assert icon["Cache-Control"] == "max-age=60, public"


@pytest.mark.django_db
def test_the_api_is_still_answered_by_django(pwa_client):
    assert pwa_client.get("/api/v1/auth/csrf").status_code == 200
    assert pwa_client.get("/api/v1/me").status_code == 403


def test_immutable_test_matches_only_content_hashed_names():
    assert frontend.immutable_file("", "/assets/index-D7fHeuzi.css")
    assert frontend.immutable_file("", "/static/admin/css/base.1e7f6d0d6f2a.css")
    assert not frontend.immutable_file("", "/sw.js")
    assert not frontend.immutable_file("", "/assets/logo.svg")
    assert not frontend.immutable_file("", "/static/admin/css/base.css")


def test_deploy_check_requires_a_built_frontend(settings, tmp_path, built_frontend):
    settings.WHITENOISE_ROOT = tmp_path / "missing"
    errors = frontend.check_frontend_build(None)
    assert [error.id for error in errors] == ["charityos.E001"]
    settings.WHITENOISE_ROOT = built_frontend
    assert frontend.check_frontend_build(None) == []
