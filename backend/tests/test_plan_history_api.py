"""Plans keep their history: items are removed, plans and capacities are edited."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from planning.models import (
    DailyCapacity,
    DailyPlan,
    DailyPlanItem,
    PlanningEvent,
    Task,
)

pytestmark = pytest.mark.django_db
DAY = date(2026, 11, 24)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        "plans@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def plan(user):
    return DailyPlan.objects.create(user=user, local_date=DAY, timezone_name="UTC")


@pytest.fixture
def item(client, user, plan):
    task = Task.objects.create(user=user, title="Write report")
    response = client.post(
        "/api/v1/daily-plan-items",
        {"plan": str(plan.id), "task": str(task.id), "kind": "primary"},
        format="json",
    )
    assert response.status_code == 201
    return DailyPlanItem.objects.get(pk=response.json()["id"])


def test_plan_items_are_removed_not_deleted(client, item):
    refused = client.delete(f"/api/v1/daily-plan-items/{item.id}")
    removed = client.post(
        f"/api/v1/daily-plan-items/{item.id}/remove",
        {"reason": "Not today"},
        format="json",
    )
    again = client.post(f"/api/v1/daily-plan-items/{item.id}/remove")

    assert refused.status_code == 405
    assert refused.json()["error"]["code"] == "remove_instead"
    assert removed.status_code == 200
    assert removed.json()["state"] == "removed"
    assert again.json()["state"] == "removed"
    item.refresh_from_db()
    assert item.state == "removed"
    event = PlanningEvent.objects.get(event_type="removed")
    assert event.source_item_id == item.id
    assert event.task_id == item.task_id
    assert event.snapshot == {
        "title": "Write report",
        "date": "2026-11-24",
        "reason": "Not today",
    }


def test_removed_items_leave_today_and_the_task_can_be_planned_again(
    client, item, plan
):
    client.post(f"/api/v1/daily-plan-items/{item.id}/remove")

    today = client.get("/api/v1/daily-plans/today?date=2026-11-24").json()
    replanned = client.post(
        "/api/v1/daily-plan-items",
        {"plan": str(plan.id), "task": str(item.task_id)},
        format="json",
    )

    assert today["items"] == []
    assert replanned.status_code == 201
    assert DailyPlanItem.objects.filter(task=item.task).count() == 2


def test_only_current_items_can_be_removed(client, item):
    client.post(
        f"/api/v1/daily-plan-items/{item.id}/carry-over",
        {"destination_date": "2026-11-25"},
        format="json",
    )

    response = client.post(f"/api/v1/daily-plan-items/{item.id}/remove")

    assert response.status_code == 400
    item.refresh_from_db()
    assert item.state == "carried_forward"


def test_state_cannot_be_patched_around_the_history(client, item):
    response = client.patch(
        f"/api/v1/daily-plan-items/{item.id}", {"state": "removed"}, format="json"
    )

    assert response.status_code == 400
    assert "state" in response.json()
    item.refresh_from_db()
    assert item.state == "current"
    assert not PlanningEvent.objects.filter(event_type="removed").exists()


def test_another_users_item_cannot_be_removed(item, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "password")
    api = APIClient()
    api.force_authenticate(other)

    response = api.post(f"/api/v1/daily-plan-items/{item.id}/remove")

    assert response.status_code == 404
    item.refresh_from_db()
    assert item.state == "current"


def test_plans_and_capacities_are_edited_not_deleted(client, user, plan):
    capacity = DailyCapacity.objects.create(
        user=user, local_date=DAY, timezone_name="UTC", available_minutes=300
    )

    plan_delete = client.delete(f"/api/v1/daily-plans/{plan.id}")
    capacity_delete = client.delete(f"/api/v1/capacities/{capacity.id}")
    edited = client.patch(
        f"/api/v1/capacities/{capacity.id}", {"available_minutes": 240}, format="json"
    )
    noted = client.patch(
        f"/api/v1/daily-plans/{plan.id}", {"notes": "Light day"}, format="json"
    )

    assert plan_delete.status_code == capacity_delete.status_code == 405
    assert plan_delete.json()["error"]["code"] == "edit_instead"
    assert capacity_delete.json()["error"]["code"] == "edit_instead"
    assert DailyPlan.objects.filter(pk=plan.pk).exists()
    assert edited.json()["available_minutes"] == 240
    assert noted.json()["notes"] == "Light day"


def test_audit_probe_deleting_a_task_no_longer_destroys_its_plan_history(client, item):
    """2026-11-24 audit: DELETE /tasks/{id} returned 204 and left 0 plan items."""
    response = client.delete(f"/api/v1/tasks/{item.task_id}")

    assert response.status_code == 405
    assert Task.objects.filter(pk=item.task_id).exists()
    assert DailyPlanItem.objects.filter(pk=item.pk).exists()
    assert PlanningEvent.objects.filter(task_id=item.task_id).exists()
