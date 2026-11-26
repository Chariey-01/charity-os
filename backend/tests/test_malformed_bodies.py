"""A request body that is not a JSON object is a 400, never a server error.

Review of Phase 0C (26 Nov 2026): a JSON array sent to sign-in, a session
edit, a correction, a reflection or a daily total raised AttributeError
(HTTP 500), and a non-text password raised TypeError in the hasher.
"""

import json
import uuid

import pytest
from rest_framework.test import APIClient

from planning.models import Area

pytestmark = pytest.mark.django_db
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", PASSWORD)


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def session_id(api, user):
    area = Area.objects.create(user=user, name="Study", slug="study")
    session_id = str(uuid.uuid4())
    started = api.post(
        "/api/v1/sessions/start",
        {"id": session_id, "title": "Read", "area": str(area.id), "is_deep_work": True},
        format="json",
    )
    assert started.status_code in (200, 201), started.content
    return session_id


def send(client, method, path, body):
    return getattr(client, method)(
        path, data=json.dumps(body), content_type="application/json"
    )


@pytest.mark.parametrize("body", [[1, 2], "text", 7, None])
def test_sign_in_refuses_a_body_that_is_not_an_object(user, body):
    response = send(APIClient(), "post", "/api/v1/auth/login", body)

    assert response.status_code == 400
    assert "object" in json.dumps(response.json())


def test_sign_in_refuses_credentials_that_are_not_text(user):
    response = send(
        APIClient(),
        "post",
        "/api/v1/auth/login",
        {"email": {"x": 1}, "password": ["p"]},
    )

    assert response.status_code == 400
    # The API's usual field-error shape: {"field": ["message"]}.
    assert set(response.json()) == {"email", "password"}


def test_sign_in_still_works_and_still_hides_which_part_was_wrong(user):
    client = APIClient()
    wrong = send(
        client,
        "post",
        "/api/v1/auth/login",
        {"email": "x@example.com", "password": "y"},
    )
    right = send(
        client,
        "post",
        "/api/v1/auth/login",
        {"email": "owner@example.com", "password": PASSWORD},
    )

    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert right.status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/daily-reflections"),
        ("post", "/api/v1/weekly-reviews"),
        ("post", "/api/v1/water"),
        ("post", "/api/v1/nutrition"),
        ("post", "/api/v1/tasks"),
        ("patch", "/api/v1/me"),
    ],
)
def test_writes_refuse_a_body_that_is_not_an_object(api, method, path):
    response = send(api, method, path, [1, 2])

    assert response.status_code == 400


@pytest.mark.parametrize("suffix", ["", "/corrections", "/finish", "/pause"])
def test_session_writes_refuse_a_body_that_is_not_an_object(api, session_id, suffix):
    method = "patch" if suffix == "" else "post"

    response = send(api, method, f"/api/v1/sessions/{session_id}{suffix}", [1])

    assert response.status_code == 400


def test_form_posts_still_parse(user):
    response = APIClient().post(
        "/api/v1/auth/login", {"email": "owner@example.com", "password": PASSWORD}
    )

    # Multipart form data still reaches the view (CSRF is not enforced by
    # the test client); credentials are read from it as before.
    assert response.status_code == 200
