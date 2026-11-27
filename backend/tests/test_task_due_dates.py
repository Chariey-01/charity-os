"""Task due dates (planning.0011), their history, and task list filters.

Due dates are optional. Every change is an append-only due_changed event,
so planning/progress.py can tell what a past week's workload was.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APIClient

from planning.models import Area, PlanningEvent, Task

PASSWORD = "pw-123456-abc"


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", PASSWORD)


@pytest.fixture
def client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def due_events(task_id):
    return list(
        PlanningEvent.objects.filter(task_id=task_id, event_type="due_changed")
        .order_by("created_at")
        .values_list("snapshot", flat=True)
    )


@pytest.mark.django_db
def test_a_task_needs_only_a_title(client):
    response = client.post("/api/v1/tasks", {"title": "Read chapter 3"}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert (body["due_date"], body["area"], body["estimated_minutes"]) == (
        None,
        None,
        None,
    )
    assert body["status"] == "todo"


@pytest.mark.django_db
def test_every_due_date_change_is_recorded(client):
    task = client.post(
        "/api/v1/tasks", {"title": "Invoice", "due_date": "2026-11-27"}, format="json"
    ).json()

    client.patch(
        f"/api/v1/tasks/{task['id']}", {"due_date": "2026-12-01"}, format="json"
    )
    client.patch(
        f"/api/v1/tasks/{task['id']}", {"title": "Invoice client"}, format="json"
    )
    client.patch(f"/api/v1/tasks/{task['id']}", {"due_date": None}, format="json")

    assert due_events(task["id"]) == [
        {"title": "Invoice", "from": "2026-11-27", "to": "2026-12-01"},
        {"title": "Invoice client", "from": "2026-12-01", "to": None},
    ]
    assert Task.objects.get(pk=task["id"]).due_date is None


@pytest.mark.django_db
def test_list_filters(client, user):
    learning = Area.objects.create(user=user, name="Learning", slug="learning")
    client.post(
        "/api/v1/tasks", {"title": "Open", "area": str(learning.id)}, format="json"
    ).json()
    client.post(
        "/api/v1/tasks", {"title": "Blocked", "status": "blocked"}, format="json"
    ).json()
    old_done = client.post(
        "/api/v1/tasks", {"title": "Done long ago", "status": "done"}, format="json"
    ).json()
    Task.objects.filter(pk=old_done["id"]).update(
        completed_at=timezone.now() - timedelta(days=30)
    )
    client.post(
        "/api/v1/tasks", {"title": "Done today", "status": "done"}, format="json"
    ).json()

    def titles(query):
        response = client.get(f"/api/v1/tasks?{query}")
        assert response.status_code == 200, response.json()
        return sorted(row["title"] for row in response.json())

    since = (timezone.now() - timedelta(days=7)).date().isoformat()
    assert titles("status=open") == ["Blocked", "Open"]
    assert titles("status=done") == ["Done long ago", "Done today"]
    assert titles(f"area={learning.id}") == ["Open"]
    assert titles(f"completed_since={since}") == ["Blocked", "Done today", "Open"]
    assert client.get("/api/v1/tasks?status=finished").status_code == 400
    assert client.get("/api/v1/tasks?completed_since=yesterday").status_code == 400
    assert client.get("/api/v1/tasks?area=not-a-uuid").status_code == 400
    assert client.get(f"/api/v1/tasks/{old_done['id']}?status=open").status_code == 200


def due_date_column_exists():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'planning_task' AND column_name = 'due_date'"
        )
        return cursor.fetchone()[0] == 1


def migrate_planning(target):
    MigrationExecutor(connection).migrate([("planning", target)])
    return (
        MigrationExecutor(connection)
        ._create_project_state(with_applied_migrations=True)
        .apps
    )


@pytest.mark.django_db(transaction=True)
def test_reversing_is_refused_while_due_dates_exist(user):
    task = Task.objects.create(user=user, title="Keep me", due_date="2026-11-30")
    try:
        with pytest.raises(RuntimeError, match="1 task\\(s\\) have a due date"):
            migrate_planning("0010_restrict_history_deletes")
        assert due_date_column_exists()
        task.refresh_from_db()
        assert str(task.due_date) == "2026-11-30"
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_existing_tasks_get_no_invented_due_date_and_the_migration_round_trips(user):
    try:
        old = migrate_planning("0010_restrict_history_deletes")
        assert not due_date_column_exists()
        OldTask = old.get_model("planning", "Task")
        legacy = OldTask.objects.create(
            user_id=user.pk,
            title="Old task",
            status="todo",
            priority=2,
            estimated_minutes=45,
        )
        before = OldTask.objects.values(
            "id", "title", "status", "priority", "estimated_minutes", "created_at"
        ).get(pk=legacy.pk)

        call_command("migrate", verbosity=0)
        after = Task.objects.values(
            "id",
            "title",
            "status",
            "priority",
            "estimated_minutes",
            "created_at",
            "due_date",
        ).get(pk=legacy.pk)
        assert after.pop("due_date") is None
        assert after == before

        migrate_planning("0010_restrict_history_deletes")  # no due dates: allowed
        assert not due_date_column_exists()
    finally:
        call_command("migrate", verbosity=0)
    assert Task.objects.filter(pk=legacy.pk, due_date__isnull=True).exists()
