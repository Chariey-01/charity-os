"""The health check the hosting platform polls (config/health_probe.py)."""

import logging

import pytest
from django.db.utils import OperationalError
from django.test import Client, override_settings

from config import health_probe


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["charityos.onrender.com"])
def test_platform_probe_is_answered_despite_internal_host_and_plain_http():
    client = Client(HTTP_HOST="10.214.3.7:10000")
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response["Cache-Control"] == "no-store"
    assert client.head("/api/v1/health").status_code == 200
    # Only that one path skips the host and HTTPS checks.
    assert client.get("/api/v1/auth/csrf").status_code == 400
    secure_host = Client(HTTP_HOST="charityos.onrender.com")
    assert secure_host.get("/api/v1/auth/csrf").status_code == 301


def test_probe_reports_an_unreachable_database_without_details(monkeypatch):
    class Down:
        def cursor(self):
            raise OperationalError('connection to "dpg-secret-host" failed')

    monkeypatch.setattr(health_probe, "connection", Down())
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logging.getLogger("django.request").addHandler(handler)
    try:
        response = Client().get("/api/v1/health")
    finally:
        logging.getLogger("django.request").removeHandler(handler)
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "unavailable"}
    logged = "\n".join(record.getMessage() for record in records)
    assert "health check: database unavailable (OperationalError)" in logged
    assert "dpg-secret-host" not in logged


@pytest.mark.django_db
def test_other_methods_still_reach_the_view(client):
    assert client.post("/api/v1/health").status_code == 405
