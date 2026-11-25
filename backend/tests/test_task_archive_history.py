"""Archiving a task is recorded in its history and destroys nothing."""

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from planning.models import DailyPlan, DailyPlanItem, PlanningEvent, Task
from planning.services import archive_task, restore_task, transition_task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("archive@example.com", "password")


def events(task):
    return list(
        PlanningEvent.objects.filter(task=task)
        .order_by("created_at")
        .values_list("event_type", flat=True)
    )


def test_archive_and_restore_each_write_one_event(user):
    task = Task.objects.create(user=user, title="Draft essay")
    transition_task(user=user, task=task, target="in_progress")

    archived = archive_task(user=user, task=task)
    again = archive_task(user=user, task=task)
    restored = restore_task(user=user, task=task)
    restore_task(user=user, task=task)

    assert archived.archived_at is not None
    assert again.archived_at == archived.archived_at
    assert restored.archived_at is None
    assert restored.status == "in_progress"
    assert events(task) == ["status_changed", "archived", "restored"]
    archived_event = PlanningEvent.objects.get(task=task, event_type="archived")
    assert archived_event.snapshot == {"title": "Draft essay", "status": "in_progress"}


def test_archiving_keeps_plan_history(user):
    task = Task.objects.create(user=user, title="Read")
    plan = DailyPlan.objects.create(
        user=user, local_date=date(2026, 11, 25), timezone_name="UTC"
    )
    item = DailyPlanItem.objects.create(
        user=user, plan=plan, task=task, title_snapshot="Read"
    )

    archive_task(user=user, task=task)

    item.refresh_from_db()
    assert item.task_id == task.id
    assert item.state == DailyPlanItem.State.CURRENT
    assert Task.objects.filter(pk=task.pk).exists()


def test_another_users_task_cannot_be_archived(user, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "password")
    task = Task.objects.create(user=other, title="Theirs")

    with pytest.raises(Task.DoesNotExist):
        archive_task(user=user, task=task)
    task.refresh_from_db()
    assert task.archived_at is None


def test_migration_0009_is_state_only():
    out = StringIO()
    call_command("sqlmigrate", "planning", "0009", stdout=out)

    statements = [
        line
        for line in out.getvalue().splitlines()
        if line.strip() and not line.startswith("--")
    ]
    assert statements == ["BEGIN;", "COMMIT;"]


def migrate(planning_target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    targets = [
        node for node in executor.loader.graph.leaf_nodes() if node[0] != "planning"
    ] + [("planning", planning_target)]
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_migration_0009_round_trips_existing_events():
    apps = migrate("0009_planningevent_archive_events")
    User = apps.get_model("users", "User")
    Task = apps.get_model("planning", "Task")
    Event = apps.get_model("planning", "PlanningEvent")
    owner = User.objects.create(email="round@example.com", password="x")
    task = Task.objects.create(user=owner, title="Kept")
    for kind in ("archived", "restored"):
        Event.objects.create(user=owner, task=task, event_type=kind, snapshot={})
    before = sorted(Event.objects.values_list("id", "event_type", "task_id"))

    apps = migrate("0008_planningevent_status_changed")
    after_reverse = sorted(
        apps.get_model("planning", "PlanningEvent").objects.values_list(
            "id", "event_type", "task_id"
        )
    )
    apps = migrate("0009_planningevent_archive_events")
    after_forward = sorted(
        apps.get_model("planning", "PlanningEvent").objects.values_list(
            "id", "event_type", "task_id"
        )
    )

    assert after_reverse == before
    assert after_forward == before
