"""Phase 0B, B2: focus-session versions are compared as numbers; stale writes get 409."""

import uuid

import pytest
from rest_framework.test import APIClient

from execution.models import FocusSession
from planning.models import Area

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("versions@example.com", "password")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def session(client, user):
    area = Area.objects.create(user=user, name="Study", slug="study")
    body = client.post(
        "/api/v1/sessions/start",
        {
            "id": str(uuid.uuid4()),
            "title": "Read",
            "area": str(area.id),
            "is_deep_work": True,
        },
        format="json",
    ).json()
    return FocusSession.objects.get(pk=body["id"])


def test_a_stale_version_is_a_409_conflict_and_changes_nothing(client, session):
    response = client.post(
        f"/api/v1/sessions/{session.id}/pause",
        {"id": str(uuid.uuid4()), "expected_version": 7},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"
    session.refresh_from_db()
    assert (session.status, session.version) == ("active", 1)


def test_a_version_sent_as_text_is_the_same_version(client, session):
    paused = client.post(
        f"/api/v1/sessions/{session.id}/pause",
        {"id": str(uuid.uuid4()), "expected_version": "1"},
        format="json",
    )
    finished = client.post(
        f"/api/v1/sessions/{session.id}/finish",
        {"expected_version": "2"},
        format="json",
    )

    assert paused.status_code == 200
    assert finished.status_code == 200
    assert finished.json()["status"] == "completed"


@pytest.mark.parametrize("bad", ["two", "1.5", True, -1, 0])
def test_a_malformed_version_is_a_field_error_not_a_500(client, session, bad):
    response = client.post(
        f"/api/v1/sessions/{session.id}/finish",
        {"expected_version": bad},
        format="json",
    )

    assert response.status_code == 400
    assert "expected_version" in response.json()["error"]["fields"]
    session.refresh_from_db()
    assert session.status == "active"


def test_actions_without_a_version_still_work(client, session):
    response = client.post(f"/api/v1/sessions/{session.id}/finish")

    assert response.status_code == 200
