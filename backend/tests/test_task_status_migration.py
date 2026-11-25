"""planning.0007: task status workflow migration, forward and reverse.

docs/project-workspaces-design.md §13: existing data must round-trip
unchanged and related records (history, plan items, evidence, focus
sessions, schedule entries) must be untouched.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from planning.models import Task

BEFORE = "0006_default_categories"
AFTER = "0007_task_status_workflow"
T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def migrate(planning_migration):
    """Move planning to ``planning_migration``.

    Later migrations of other apps that depend on newer planning migrations
    (such as the Phase 0 restrict migrations) are unapplied along with it; the
    test re-applies every app at the end.
    """
    MigrationExecutor(connection).migrate([("planning", planning_migration)])
    return (
        MigrationExecutor(connection)
        ._create_project_state(with_applied_migrations=True)
        .apps
    )


def task_rows(apps, terminal_field):
    Task = apps.get_model("planning", "Task")
    return {
        row["id"]: row
        for row in Task.objects.values(
            "id", "status", "completed_at", terminal_field, "updated_at", "title"
        )
    }


def related_snapshot(apps):
    def ids(app, model, *fields):
        Model = apps.get_model(app, model)
        return sorted(Model.objects.values_list("id", *fields))

    return {
        "plan_items": ids("planning", "DailyPlanItem", "task_id", "state"),
        "events": ids("planning", "PlanningEvent", "task_id", "event_type", "snapshot"),
        "evidence": ids("records", "Evidence", "task_id", "text"),
        "sessions": ids("execution", "FocusSession", "task_id", "duration_seconds"),
        "entries": ids("scheduling", "ScheduleEntry", "task_id", "status"),
    }


@pytest.mark.django_db(transaction=True)
def test_status_migration_round_trips_and_preserves_related_records():
    apps = migrate(BEFORE)
    User = apps.get_model("users", "User")
    Area = apps.get_model("planning", "Area")
    OldTask = apps.get_model("planning", "Task")
    user = User.objects.create(email="legacy-tasks@example.com", timezone="UTC")
    area = Area.objects.create(user=user, name="Engineering", slug="engineering")
    planned = OldTask.objects.create(user=user, title="Open work", status="planned")
    completed = OldTask.objects.create(
        user=user, title="Shipped", status="completed", completed_at=T0
    )
    skipped = OldTask.objects.create(
        user=user, title="Dropped", status="skipped", skipped_at=T0 + timedelta(hours=1)
    )
    plan = apps.get_model("planning", "DailyPlan").objects.create(
        user=user, local_date=date(2026, 11, 20), timezone_name="UTC"
    )
    apps.get_model("planning", "DailyPlanItem").objects.create(
        user=user, plan=plan, task=planned, kind="primary", title_snapshot="Open work"
    )
    Event = apps.get_model("planning", "PlanningEvent")
    Event.objects.create(
        user=user, event_type="completed", task=completed, snapshot={"title": "Shipped"}
    )
    Event.objects.create(
        user=user, event_type="skipped", task=skipped, snapshot={"title": "Dropped"}
    )
    apps.get_model("records", "Evidence").objects.create(
        user=user, kind="note", text="Release notes", task=completed
    )
    apps.get_model("execution", "FocusSession").objects.create(
        user=user,
        area=area,
        task=completed,
        title="Build",
        status="completed",
        is_deep_work=True,
        started_at=T0 - timedelta(hours=1),
        ended_at=T0,
        duration_seconds=3600,
        timezone_snapshot="UTC",
        area_label_snapshot="Engineering",
    )
    apps.get_model("scheduling", "ScheduleEntry").objects.create(
        user=user,
        title="Work block",
        task=planned,
        start_at=T0,
        end_at=T0 + timedelta(hours=1),
        timezone_name="UTC",
        local_date=date(2026, 11, 20),
    )
    before = task_rows(apps, "skipped_at")
    related_before = related_snapshot(apps)

    # Forward: statuses map, timestamps and updated_at are kept.
    apps = migrate(AFTER)
    after = task_rows(apps, "cancelled_at")
    assert {row["title"]: row["status"] for row in after.values()} == {
        "Open work": "todo",
        "Shipped": "done",
        "Dropped": "cancelled",
    }
    for task_id, old in before.items():
        new = after[task_id]
        assert new["completed_at"] == old["completed_at"]
        assert new["cancelled_at"] == old["skipped_at"]
        assert new["updated_at"] == old["updated_at"]
    assert related_snapshot(apps) == related_before  # history included

    # Rows only the new schema can express.
    NewTask = apps.get_model("planning", "Task")
    created = {
        status: NewTask.objects.create(user_id=user.id, title=status, status=status).id
        for status in ("backlog", "in_progress", "in_review", "blocked")
    }

    # Reverse: original rows come back exactly; new-only states become open.
    apps = migrate(BEFORE)
    reverted = task_rows(apps, "skipped_at")
    for task_id, old in before.items():
        assert reverted[task_id] == old
    for task_id in created.values():
        assert reverted[task_id]["status"] == "planned"
        assert reverted[task_id]["completed_at"] is None
        assert reverted[task_id]["skipped_at"] is None
    assert related_snapshot(apps) == related_before

    # Forward again is stable, then return to the latest schema.
    apps = migrate(AFTER)
    assert task_rows(apps, "cancelled_at")[completed.id]["status"] == "done"
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {"status": "planned"},
        {"status": "done"},
        {"status": "cancelled"},
        {"status": "done", "completed_at": T0, "cancelled_at": T0},
        {"status": "in_progress", "completed_at": T0},
        {"status": "blocked", "cancelled_at": T0},
    ],
)
def test_database_rejects_inconsistent_task_states(django_user_model, fields):
    user = django_user_model.objects.create_user("states@example.com", "password")
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.create(user=user, title="Invalid", **fields)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {"status": status}
        for status in ("backlog", "todo", "in_progress", "in_review", "blocked")
    ]
    + [
        {"status": "done", "completed_at": T0},
        {"status": "cancelled", "cancelled_at": T0},
    ],
)
def test_database_accepts_every_workflow_state(django_user_model, fields):
    user = django_user_model.objects.create_user("valid@example.com", "password")
    assert Task.objects.create(user=user, title="Valid", **fields).pk
