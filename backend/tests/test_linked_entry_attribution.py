"""Phase 0B, B2: a linked entry and its focus session keep one attribution."""

import pytest
from rest_framework.test import APIClient

from execution.models import FocusSession
from planning.models import Area
from scheduling.models import ScheduleEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        "linked@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def test_a_running_linked_entry_cannot_switch_category_alone(client, user):
    study = Area.objects.create(user=user, name="Study", slug="study")
    work = Area.objects.create(user=user, name="Work", slug="work")
    entry = client.post(
        "/api/v1/schedule-entries",
        {
            "title": "Read",
            "start_local": "2030-01-01T09:00",
            "end_local": "2030-01-01T10:00",
            "area": str(study.id),
            "tracking": "focus",
        },
        format="json",
    ).json()
    running = client.post(f"/api/v1/schedule-entries/{entry['id']}/start").json()
    url = f"/api/v1/schedule-entries/{entry['id']}"

    switched = client.patch(
        url,
        {"area": str(work.id), "expected_version": running["version"]},
        format="json",
    )
    # The edit form re-sends the unchanged category with other edits.
    renamed = client.patch(
        url,
        {
            "title": "Read chapter 4",
            "area": str(study.id),
            "expected_version": running["version"],
        },
        format="json",
    )

    assert switched.status_code == 400
    assert "area" in switched.json()["error"]["fields"]
    assert renamed.status_code == 200
    stored = ScheduleEntry.objects.get(pk=entry["id"])
    session = FocusSession.objects.get(pk=stored.focus_session_id)
    assert stored.area_id == session.area_id == study.id
