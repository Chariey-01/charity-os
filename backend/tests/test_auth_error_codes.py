"""The client can tell "signed out" from "CSRF failed" from "not allowed".

Before: an expired session and a CSRF failure both answered 403 with a bare
``{"detail": ...}``, so the app could only show an error toast. An expired
session must send the user back to sign-in; a CSRF failure must not.
"""

import pytest
from django.contrib.sessions.models import Session
from rest_framework.test import APIClient

PASSWORD = "pw-123456-abc"


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", PASSWORD)


def signed_in(user, enforce_csrf=False):
    client = APIClient(enforce_csrf_checks=enforce_csrf)
    assert client.login(email=user.email, password=PASSWORD)
    return client


@pytest.mark.django_db
def test_an_anonymous_request_says_not_authenticated():
    response = APIClient().get("/api/v1/tasks")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.json()["detail"]  # kept for older clients


@pytest.mark.django_db
def test_a_session_that_ended_on_the_server_says_not_authenticated(user):
    client = signed_in(user)
    assert client.get("/api/v1/tasks").status_code == 200

    Session.objects.all().delete()  # expiry, sign-out elsewhere, erasure
    response = client.get("/api/v1/tasks")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
def test_a_missing_csrf_token_is_not_reported_as_signed_out(user):
    client = signed_in(user, enforce_csrf=True)

    response = client.post("/api/v1/tasks", {"title": "x"}, format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


@pytest.mark.django_db
def test_someone_elses_record_is_neither(user, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", PASSWORD)
    task = signed_in(other).post("/api/v1/tasks", {"title": "theirs"}, format="json")

    response = signed_in(user).get(f"/api/v1/tasks/{task.json()['id']}")

    assert response.status_code == 404
    assert response.json().get("error", {}).get("code") != "not_authenticated"
