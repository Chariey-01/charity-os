"""Task API compatibility across the status migration (§13)."""

import pytest
from rest_framework.test import APIClient

from planning.models import PlanningEvent, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("api-tasks@example.com", "password")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def task(user):
    return Task.objects.create(user=user, title="Draft the PRD")


def url(task, suffix=""):
    return f"/api/v1/tasks/{task.id}{suffix}"


def test_patching_status_goes_through_the_transition_service(client, task):
    # Previously HTTP 500: the raw status write broke the timestamp constraint.
    response = client.patch(url(task), {"status": "done"}, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "done"
    assert body["completed_at"] is not None
    assert PlanningEvent.objects.get(task=task).event_type == "completed"


def test_patch_can_change_fields_and_status_together(client, task):
    response = client.patch(
        url(task), {"title": "Final PRD", "status": "in_review"}, format="json"
    )

    assert response.status_code == 200
    task.refresh_from_db()
    assert (task.title, task.status) == ("Final PRD", "in_review")


def test_timestamps_cannot_be_written_directly(client, task):
    client.patch(url(task), {"completed_at": "2026-01-01T00:00:00Z"}, format="json")

    task.refresh_from_db()
    assert task.completed_at is None


@pytest.mark.parametrize("bad", ["archived", "", "COMPLETED"])
def test_unknown_status_is_a_400(client, task, bad):
    response = client.patch(url(task), {"status": bad}, format="json")

    assert response.status_code == 400
    task.refresh_from_db()
    assert task.status == "todo"


@pytest.mark.parametrize(
    ("sent", "status", "legacy", "events"),
    [
        (None, "todo", "planned", []),
        ("planned", "todo", "planned", []),
        ("backlog", "backlog", "planned", []),
        ("completed", "done", "completed", ["completed"]),
        ("cancelled", "cancelled", "skipped", ["skipped"]),
    ],
)
def test_create_accepts_workflow_and_legacy_statuses(
    client, sent, status, legacy, events
):
    payload = {"title": "New"} | ({"status": sent} if sent else {})

    response = client.post("/api/v1/tasks", payload, format="json")

    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["status"], body["legacy_status"]) == (status, legacy)
    assert (body["completed_at"] is not None) == (status == "done")
    assert (body["cancelled_at"] is not None) == (status == "cancelled")
    created = Task.objects.get(pk=body["id"])
    assert [e.event_type for e in created.planning_events.all()] == events


@pytest.mark.parametrize(
    ("action", "status", "legacy"),
    [("complete", "done", "completed"), ("skip", "cancelled", "skipped")],
)
def test_legacy_endpoints_still_work(client, task, action, status, legacy):
    response = client.post(url(task, f"/{action}"))

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["legacy_status"]) == (
        status,
        legacy,
    )
    reopened = client.post(url(task, "/reopen")).json()
    assert (reopened["status"], reopened["legacy_status"]) == ("todo", "planned")


def test_transition_endpoint_reaches_every_status_with_a_reason(client, task):
    for status in ("backlog", "in_progress", "blocked", "in_review", "done", "todo"):
        response = client.post(
            url(task, "/transition"),
            {"status": status, "reason": "progress"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == status

    snapshots = PlanningEvent.objects.filter(task=task).values_list(
        "snapshot", flat=True
    )
    assert all(snapshot["reason"] == "progress" for snapshot in snapshots)


def test_transition_endpoint_validates_input(client, task):
    assert client.post(url(task, "/transition"), {}, format="json").status_code == 400
    response = client.post(
        url(task, "/transition"), {"status": "archived"}, format="json"
    )
    assert response.status_code == 400
    assert "Unknown task status" in response.json()["detail"]


def test_responses_use_cancelled_at_not_skipped_at(client, task):
    body = client.get(url(task)).json()

    assert "cancelled_at" in body and "skipped_at" not in body


def test_other_users_cannot_transition_or_patch(task, django_user_model):
    intruder = django_user_model.objects.create_user("intruder@example.com", "password")
    other = APIClient()
    other.force_authenticate(intruder)

    assert (
        other.post(
            url(task, "/transition"), {"status": "done"}, format="json"
        ).status_code
        == 404
    )
    assert other.patch(url(task), {"status": "done"}, format="json").status_code == 404
    for action in ("complete", "skip", "reopen"):
        assert other.post(url(task, f"/{action}")).status_code == 404
    task.refresh_from_db()
    assert task.status == "todo"
