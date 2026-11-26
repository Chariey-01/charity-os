"""Phase 0B, B2: session PATCH is version-aware and never changes attribution."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

import execution.services as session_services
from execution.models import FocusSession, FocusSessionCorrection
from planning.models import Area, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("patch@example.com", "password")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def area(user):
    return Area.objects.create(user=user, name="Study", slug="study")


def start(client, area):
    return client.post(
        "/api/v1/sessions/start",
        {
            "id": str(uuid.uuid4()),
            "title": "Read",
            "area": str(area.id),
            "is_deep_work": True,
        },
        format="json",
    ).json()


def patch(client, session_id, **body):
    return client.patch(f"/api/v1/sessions/{session_id}", body, format="json")


def test_patch_requires_the_current_version_and_bumps_it(client, area):
    session = start(client, area)

    missing = patch(client, session["id"], notes="first")
    stale = patch(client, session["id"], notes="first", expected_version=9)
    saved = patch(client, session["id"], notes="first", expected_version=1)
    repeated = patch(client, session["id"], notes="second", expected_version=1)

    assert missing.status_code == 400
    assert "expected_version" in missing.json()["error"]["fields"]
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert saved.status_code == 200
    assert (saved.json()["notes"], saved.json()["version"]) == ("first", 2)
    assert repeated.status_code == 409  # a stale client cannot overwrite "first"
    assert FocusSession.objects.get(pk=session["id"]).notes == "first"


def test_audit_probe_attribution_cannot_be_patched(client, user, area):
    """2026-11-24 audit: PATCH changed is_deep_work and title with no version."""
    other_area = Area.objects.create(user=user, name="Work", slug="work")
    task = Task.objects.create(user=user, title="T")
    session = start(client, area)

    for field, value in (
        ("area", str(other_area.id)),
        ("task", str(task.id)),
        ("is_deep_work", False),
        ("roadmap_item", None),
    ):
        response = patch(client, session["id"], expected_version=1, **{field: value})
        assert response.status_code == 400, field
        assert response.json()["error"]["code"] == "use_correction"

    stored = FocusSession.objects.get(pk=session["id"])
    assert (stored.area_id, stored.task_id, stored.is_deep_work, stored.version) == (
        area.id,
        None,
        True,
        1,
    )


def test_ended_sessions_only_change_their_notes_outcome_and_learning(client, area):
    session = start(client, area)
    client.post(f"/api/v1/sessions/{session['id']}/finish", {"expected_version": 1})

    renamed = patch(client, session["id"], title="Renamed", expected_version=2)
    timed = patch(client, session["id"], duration_seconds=1, expected_version=2)
    noted = patch(
        client, session["id"], notes="n", outcome="o", learning="l", expected_version=2
    )

    assert renamed.status_code == 400 and "title" in renamed.json()["error"]["fields"]
    assert timed.status_code == 400
    assert noted.status_code == 200
    stored = FocusSession.objects.get(pk=session["id"])
    assert (stored.title, stored.notes, stored.outcome, stored.learning) == (
        "Read",
        "n",
        "o",
        "l",
    )
    assert not FocusSessionCorrection.objects.exists()


def test_open_sessions_may_be_renamed(client, area):
    session = start(client, area)

    renamed = patch(
        client, session["id"], title="  Read chapter 4 ", expected_version=1
    )
    blank = patch(client, session["id"], title="   ", expected_version=2)

    assert renamed.json()["title"] == "Read chapter 4"
    assert blank.status_code == 400


def test_another_users_session_cannot_be_patched(area, client, django_user_model):
    session = start(client, area)
    other = django_user_model.objects.create_user("other@example.com", "password")
    api = APIClient()
    api.force_authenticate(other)

    assert patch(api, session["id"], notes="x", expected_version=1).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_writers_with_the_same_version_one_wins(user, area, monkeypatch):
    real = session_services.parse_version

    def slow_parse(value):
        time.sleep(0.4)  # both writers have read the row before either writes
        return real(value)

    monkeypatch.setattr(session_services, "parse_version", slow_parse)
    api = APIClient()
    api.force_authenticate(user)
    session_id = start(api, area)["id"]

    def write(text):
        try:
            client = APIClient()
            client.force_authenticate(user)
            return patch(client, session_id, notes=text, expected_version=1).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(write, ["from phone", "from laptop"]))

    assert results == [200, 409]
    stored = FocusSession.objects.get(pk=session_id)
    assert stored.version == 2
    assert stored.notes in ("from phone", "from laptop")
