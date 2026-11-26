"""Archive instead of delete: categories, tasks and challenges (api/archive.py)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from challenges.models import Challenge
from execution.models import FocusSession
from planning.categories import ensure_default_categories
from planning.models import Area, DailyPlan, DailyPlanItem, PlanningEvent, Task

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        "archive@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def records(user):
    area = Area.objects.create(user=user, name="Study", slug="study")
    task = Task.objects.create(user=user, title="Read chapter 3", area=area)
    challenge = Challenge.objects.create(
        user=user,
        name="Road to 2027",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 12, 5),
        status="active",
        is_primary=True,
    )
    return {"areas": area, "tasks": task, "challenges": challenge}


RESOURCES = ("areas", "tasks", "challenges")


@pytest.mark.parametrize("resource", RESOURCES)
def test_delete_is_refused_with_a_stable_code_and_nothing_is_deleted(
    client, records, resource
):
    record = records[resource]

    response = client.delete(f"/api/v1/{resource}/{record.id}")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "archive_instead"
    assert "DELETE" not in response["Allow"]
    assert type(record).objects.filter(pk=record.pk).exists()


@pytest.mark.parametrize("resource", RESOURCES)
def test_archive_and_restore_round_trip(client, records, resource):
    record = records[resource]

    archived = client.post(f"/api/v1/{resource}/{record.id}/archive")
    repeated = client.post(f"/api/v1/{resource}/{record.id}/archive")
    restored = client.post(f"/api/v1/{resource}/{record.id}/restore")

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert repeated.json()["archived_at"] == archived.json()["archived_at"]
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


@pytest.mark.parametrize("resource", RESOURCES)
def test_lists_hide_archived_records_unless_asked(client, records, resource):
    record = records[resource]
    client.post(f"/api/v1/{resource}/{record.id}/archive")

    def ids(query=""):
        return {row["id"] for row in client.get(f"/api/v1/{resource}{query}").json()}

    assert str(record.id) not in ids()
    assert str(record.id) not in ids("?archived=exclude")
    assert str(record.id) in ids("?archived=include")
    assert ids("?archived=only") == {str(record.id)}
    assert client.get(f"/api/v1/{resource}/{record.id}").status_code == 200
    bad = client.get(f"/api/v1/{resource}?archived=maybe")
    assert bad.status_code == 400
    assert "archived" in bad.json()


@pytest.mark.parametrize("resource", RESOURCES)
def test_archived_at_cannot_be_written_directly(client, records, resource):
    record = records[resource]

    response = client.patch(
        f"/api/v1/{resource}/{record.id}",
        {"archived_at": NOW.isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert "archived_at" in response.json()
    record.refresh_from_db()
    assert record.archived_at is None


def test_another_users_record_cannot_be_archived(client, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "password")
    theirs = Area.objects.create(user=other, name="Theirs", slug="theirs")

    response = client.post(f"/api/v1/areas/{theirs.id}/archive")

    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.archived_at is None


def test_archiving_requires_authentication(records):
    response = APIClient().post(f"/api/v1/areas/{records['areas'].id}/archive")

    assert response.status_code == 403


def test_restoring_into_a_name_now_taken_is_a_conflict(client, user, records):
    old = records["areas"]
    client.post(f"/api/v1/areas/{old.id}/archive")
    Area.objects.create(user=user, name="Study", slug="study-2")

    response = client.post(f"/api/v1/areas/{old.id}/restore")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "restore_conflict"
    old.refresh_from_db()
    assert old.archived_at is not None


def test_task_archive_is_recorded_in_its_history(client, records):
    task = records["tasks"]

    client.post(f"/api/v1/tasks/{task.id}/archive")
    client.post(f"/api/v1/tasks/{task.id}/archive")
    client.post(f"/api/v1/tasks/{task.id}/restore")

    assert list(
        PlanningEvent.objects.filter(task=task)
        .order_by("created_at")
        .values_list("event_type", flat=True)
    ) == ["archived", "restored"]


def test_archiving_a_challenge_keeps_its_status_and_ends_primacy(client, records):
    challenge = records["challenges"]

    body = client.post(f"/api/v1/challenges/{challenge.id}/archive").json()

    assert body["is_primary"] is False
    assert body["status"] == "active"
    blocked = client.post(f"/api/v1/challenges/{challenge.id}/set-primary")
    assert blocked.status_code == 400
    assert client.get("/api/v1/challenges/primary").data is None


def test_today_leaves_out_archived_tasks(client, user, records):
    task = records["tasks"]
    plan = DailyPlan.objects.create(
        user=user, local_date=date(2026, 11, 24), timezone_name="UTC"
    )
    DailyPlanItem.objects.create(user=user, plan=plan, task=task, title_snapshot="x")
    Task.objects.filter(pk=task.pk).update(created_at=NOW)

    before = client.get("/api/v1/daily-plans/today?date=2026-11-24").json()
    client.post(f"/api/v1/tasks/{task.id}/archive")
    after = client.get("/api/v1/daily-plans/today?date=2026-11-24").json()

    assert [item["task"] for item in before["items"]] == [str(task.id)]
    assert [row["id"] for row in before["tasks"]] == [str(task.id)]
    assert after["items"] == []
    assert after["tasks"] == []
    assert DailyPlanItem.objects.filter(task=task).count() == 1


def test_archiving_never_removes_time_from_insights(client, user, records):
    ensure_default_categories(user)
    task = records["tasks"]
    area = records["areas"]
    entry = client.post(
        "/api/v1/schedule-entries",
        {
            "title": "Read",
            "start_local": "2026-11-24T08:00",
            "end_local": "2026-11-24T09:00",
            "area": str(area.id),
            "task": str(task.id),
        },
        format="json",
    ).json()
    client.post(
        f"/api/v1/schedule-entries/{entry['id']}/complete",
        {"actual_minutes": 50},
        format="json",
    )
    FocusSession.objects.create(
        user=user,
        area=area,
        task=task,
        title="Focus",
        is_deep_work=True,
        started_at=NOW - timedelta(hours=3),
        ended_at=NOW - timedelta(hours=2),
        duration_seconds=3600,
        status="completed",
        timezone_snapshot="UTC",
        area_label_snapshot=area.name,
    )
    views = ("/api/v1/insights?period=7d", "/api/v1/analytics/metrics?period=7d")
    before = [client.get(path).json() for path in views]

    client.post(f"/api/v1/tasks/{task.id}/archive")
    client.post(f"/api/v1/areas/{area.id}/archive")
    after = [client.get(path).json() for path in views]

    assert before[0]["totals"]["completed"] == 1
    assert before[1]["total_focused_minutes"] == 60
    assert after == before
