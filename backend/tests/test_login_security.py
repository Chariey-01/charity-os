"""Phase 0C, S11: login needs CSRF, repeated failures lock out, nothing leaks."""

from datetime import timedelta

import pytest
from django.db.models import F
from django.test import Client, override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
PASSWORD = "correct-horse-battery-staple"

# django-axes is off in the test settings (Django's test client.login() calls
# authenticate() without a request, which axes refuses); these tests turn it on.
axes_on = override_settings(AXES_ENABLED=True)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", PASSWORD)


def browser(ip="198.51.100.7"):
    """A client that enforces CSRF like a real browser, holding a fresh token."""
    client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR=ip)
    client.get("/api/v1/auth/csrf")
    return client


def token(client):
    return client.cookies["csrftoken"].value


def login(client, email, password, with_token=True):
    headers = {"HTTP_X_CSRFTOKEN": token(client)} if with_token else {}
    return client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password},
        format="json",
        **headers,
    )


def test_audit_probe_login_without_a_csrf_token_is_refused(user):
    """2026-11-24 audit: login without a CSRF token answered 200."""
    response = login(browser(), "owner@example.com", PASSWORD, with_token=False)

    assert response.status_code == 403


def test_login_with_a_token_works_and_writes_then_need_the_new_token(user):
    client = browser()

    assert login(client, "owner@example.com", PASSWORD).status_code == 200
    # Django rotates the token at login; writes need the current one.
    without = client.post("/api/v1/tasks", {"title": "x"}, format="json")
    with_token = client.post(
        "/api/v1/tasks",
        {"title": "x"},
        format="json",
        HTTP_X_CSRFTOKEN=token(client),
    )

    assert without.status_code == 403
    assert with_token.status_code == 201


def test_failures_do_not_reveal_whether_an_account_exists(user):
    client = browser()

    wrong_password = login(client, "owner@example.com", "nope")
    unknown_email = login(client, "nobody@example.com", "nope")

    assert wrong_password.status_code == unknown_email.status_code == 400
    assert wrong_password.json() == unknown_email.json()


@axes_on
def test_five_failures_are_allowed_and_the_sixth_is_locked(user):
    client = browser()

    failures = [
        login(client, "owner@example.com", "nope").status_code for _ in range(5)
    ]
    sixth = login(client, "owner@example.com", "nope")
    afterwards = login(client, "owner@example.com", PASSWORD)  # still locked

    assert failures == [400] * 5
    assert sixth.status_code == afterwards.status_code == 429
    assert sixth.json()["error"]["code"] == "too_many_attempts"
    assert "owner@example.com" not in sixth.content.decode()


@axes_on
def test_the_right_password_after_five_failures_still_gets_in(user):
    client = browser()
    for _ in range(5):
        login(client, "owner@example.com", "nope")

    assert login(client, "owner@example.com", PASSWORD).status_code == 200


@axes_on
def test_lockout_looks_the_same_for_unknown_accounts(user):
    known, unknown = browser("198.51.100.1"), browser("198.51.100.2")
    for _ in range(5):
        login(known, "owner@example.com", "nope")
        login(unknown, "nobody@example.com", "nope")

    first = login(known, "owner@example.com", "nope")
    second = login(unknown, "nobody@example.com", "nope")

    assert first.status_code == second.status_code == 429
    assert first.json() == second.json()


@axes_on
def test_the_lock_is_per_email_and_ip_address(user, django_user_model):
    django_user_model.objects.create_user("other@example.com", PASSWORD)
    attacker = browser("203.0.113.9")
    for _ in range(6):
        login(attacker, "owner@example.com", "nope")

    other_account_same_ip = login(attacker, "other@example.com", PASSWORD)
    same_account_other_ip = login(
        browser("198.51.100.20"), "owner@example.com", PASSWORD
    )

    assert other_account_same_ip.status_code == 200
    assert same_account_other_ip.status_code == 200


@axes_on
def test_a_successful_login_resets_the_count(user):
    client = browser()
    for _ in range(4):
        login(client, "owner@example.com", "nope")
    assert login(client, "owner@example.com", PASSWORD).status_code == 200

    client = browser()
    later = [login(client, "owner@example.com", "nope").status_code for _ in range(4)]

    assert later == [400] * 4
    assert login(client, "owner@example.com", PASSWORD).status_code == 200


@axes_on
def test_the_lock_expires_after_fifteen_minutes(user):
    from axes.models import AccessAttempt, AccessAttemptExpiration

    client = browser()
    for _ in range(6):
        login(client, "owner@example.com", "nope")
    assert login(client, "owner@example.com", PASSWORD).status_code == 429

    # Let 16 minutes pass for the stored attempts.
    AccessAttempt.objects.update(attempt_time=F("attempt_time") - timedelta(minutes=16))
    AccessAttemptExpiration.objects.update(
        expires_at=F("expires_at") - timedelta(minutes=16)
    )

    assert login(client, "owner@example.com", PASSWORD).status_code == 200


@axes_on
def test_the_admin_login_is_protected_too(django_user_model):
    django_user_model.objects.create_superuser("admin@example.com", PASSWORD)
    client = Client(REMOTE_ADDR="198.51.100.30")

    def attempt(password):
        return client.post(
            "/admin/login/", {"username": "admin@example.com", "password": password}
        )

    failures = [attempt("nope").status_code for _ in range(5)]
    sixth = attempt("nope")
    afterwards = attempt(PASSWORD)

    assert failures == [200] * 5  # the admin re-shows its form on failure
    assert sixth.status_code == afterwards.status_code == 429
