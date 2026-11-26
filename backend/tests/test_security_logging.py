"""Phase 0C, S12: security events are logged, and no secret or raw email is."""

import logging
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
PASSWORD = "Sup3r-secret-passw0rd"
EMAIL = "owner@example.com"


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(EMAIL, PASSWORD)


@pytest.fixture
def log(caplog):
    caplog.set_level(logging.INFO, logger="charityos.security")
    return caplog


def browser(ip="198.51.100.7"):
    client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR=ip)
    client.get("/api/v1/auth/csrf")
    return client


def login(client, email, password, with_token=True):
    headers = (
        {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if with_token else {}
    )
    return client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password},
        format="json",
        **headers,
    )


def events(log):
    return [record for record in log.records if record.name == "charityos.security"]


def by_event(log, name):
    return [
        record
        for record in events(log)
        if getattr(record, "security_event", None) == name
    ]


def assert_nothing_secret(log, *secrets):
    text = "\n".join(record.getMessage() for record in log.records)
    for secret in secrets:
        assert secret not in text, secret


def test_successful_sign_in_and_sign_out(user, log):
    client = browser()

    login(client, EMAIL, PASSWORD)
    session_key = client.cookies["sessionid"].value
    csrf = client.cookies["csrftoken"].value
    client.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=csrf)

    [signed_in] = by_event(log, "login_succeeded")
    message = signed_in.getMessage()
    assert "email=o***@example.com" in message
    assert f"user={user.pk}" in message
    assert "ip=198.51.100.0/24" in message
    assert by_event(log, "logout")
    assert_nothing_secret(log, EMAIL, PASSWORD, session_key, csrf)


def test_failed_sign_ins_are_logged_masked(user, log):
    client = browser()

    login(client, EMAIL, "Wr0ng-guess-123")
    login(client, "nobody@example.org", "Wr0ng-guess-456")

    failures = [record.getMessage() for record in by_event(log, "login_failed")]
    assert any("email=o***@example.com" in message for message in failures)
    assert any("email=n***@example.org" in message for message in failures)
    assert all(
        record.levelno == logging.WARNING for record in by_event(log, "login_failed")
    )
    assert_nothing_secret(
        log, EMAIL, "nobody@example.org", "Wr0ng-guess-123", "Wr0ng-guess-456"
    )


@override_settings(AXES_ENABLED=True)
def test_a_lockout_is_logged(user, log):
    client = browser()
    for _ in range(6):
        login(client, EMAIL, "Wr0ng-guess-123")

    [locked] = by_event(log, "login_locked_out")
    assert "email=o***@example.com" in locked.getMessage()
    assert "ip=198.51.100.0/24" in locked.getMessage()
    assert_nothing_secret(log, EMAIL, "Wr0ng-guess-123")


def test_csrf_rejections_are_logged(user, log):
    client = browser()

    login(client, EMAIL, PASSWORD, with_token=False)
    login(client, EMAIL, PASSWORD)
    client.post("/api/v1/tasks", {"title": "x"}, format="json")  # no token

    rejected = by_event(log, "csrf_rejected")
    assert {"path=/api/v1/auth/login", "path=/api/v1/tasks"} <= {
        part
        for record in rejected
        for part in record.getMessage().split()
        if part.startswith("path=")
    }
    assert_nothing_secret(log, EMAIL, PASSWORD, client.cookies["csrftoken"].value)


def test_admin_sign_in_failures_are_logged_too(user, log):
    from django.test import Client

    Client(REMOTE_ADDR="2001:db8:1234:5678::1").post(
        "/admin/login/", {"username": EMAIL, "password": "Wr0ng-guess-789"}
    )

    [failure] = by_event(log, "login_failed")
    assert "ip=2001:db8:1234::/48" in failure.getMessage()
    assert_nothing_secret(log, EMAIL, "Wr0ng-guess-789")


def test_erasure_and_its_dry_run_are_logged_without_the_email(user, log):
    user_id = user.pk
    call_command("erase_user", EMAIL, stdout=StringIO())
    call_command("erase_user", EMAIL, "--confirm", EMAIL, stdout=StringIO())

    [dry_run] = by_event(log, "erasure_dry_run")
    assert f"user={user_id}" in dry_run.getMessage()
    [erased] = by_event(log, "user_erased")
    assert f"user={user_id}" in erased.getMessage()
    assert "email=o***@example.com" in erased.getMessage()
    assert erased.levelno == logging.WARNING
    assert_nothing_secret(log, EMAIL)
