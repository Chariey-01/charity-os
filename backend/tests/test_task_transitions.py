"""Task status transition service (docs/project-workspaces-design.md §13)."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from planning.models import DailyPlan, PlanningEvent, Task
from planning.services import add_plan_item, carry_over, transition_task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("flow@example.com", "password")


@pytest.fixture
def task(user):
    return Task.objects.create(user=user, title="Write the PRD")


def events(task):
    return list(
        PlanningEvent.objects.filter(task=task)
        .order_by("created_at")
        .values_list("event_type", "snapshot")
    )


def test_new_tasks_start_as_todo(task):
    assert task.status == "todo"


@pytest.mark.parametrize("target", ["backlog", "in_progress", "in_review", "blocked"])
def test_moves_between_open_states_have_no_terminal_timestamps(user, task, target):
    moved = transition_task(user=user, task=task, target=target)

    assert moved.status == target
    assert moved.completed_at is None and moved.cancelled_at is None
    assert events(task) == [
        ("status_changed", {"title": "Write the PRD", "from": "todo", "to": target})
    ]


def test_done_and_cancelled_set_their_timestamp_and_keep_event_names(user, task):
    done = transition_task(user=user, task=task, target="done")
    assert done.completed_at is not None and done.cancelled_at is None

    cancelled = transition_task(user=user, task=task, target="cancelled")
    assert cancelled.cancelled_at is not None and cancelled.completed_at is None

    assert [name for name, _ in events(task)] == ["completed", "skipped"]


def test_reopening_clears_timestamps_and_is_recorded(user, task):
    transition_task(user=user, task=task, target="done")
    reopened = transition_task(user=user, task=task, target="in_progress")

    assert reopened.status == "in_progress"
    assert reopened.completed_at is None
    assert events(task)[-1] == (
        "reopened",
        {"title": "Write the PRD", "from": "done", "to": "in_progress"},
    )


def test_repeating_a_transition_is_a_no_op(user, task):
    first = transition_task(user=user, task=task, target="done")
    second = transition_task(user=user, task=task, target="done")

    assert second.completed_at == first.completed_at  # original time kept
    assert len(events(task)) == 1


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [("completed", "done"), ("skipped", "cancelled"), ("planned", "todo")],
)
def test_legacy_targets_are_accepted(user, task, legacy, expected):
    if legacy == "planned":
        transition_task(user=user, task=task, target="blocked")
    assert transition_task(user=user, task=task, target=legacy).status == expected


def test_unknown_target_is_rejected_without_side_effects(user, task):
    with pytest.raises(ValidationError):
        transition_task(user=user, task=task, target="archived")

    task.refresh_from_db()
    assert task.status == "todo"
    assert events(task) == []


def test_reason_is_kept_in_history(user, task):
    transition_task(
        user=user, task=task, target="blocked", reason="  Waiting on PayPal  "
    )

    assert events(task)[0][1]["reason"] == "Waiting on PayPal"


def test_history_is_append_only_across_transitions(user, task):
    transition_task(user=user, task=task, target="in_progress")
    earlier = events(task)
    transition_task(user=user, task=task, target="blocked")
    transition_task(user=user, task=task, target="done")
    transition_task(user=user, task=task, target="todo")

    history = events(task)
    assert history[: len(earlier)] == earlier
    assert [name for name, _ in history] == [
        "status_changed",
        "status_changed",
        "completed",
        "reopened",
    ]


def test_another_users_task_cannot_be_transitioned(user, task, django_user_model):
    intruder = django_user_model.objects.create_user("x@example.com", "password")

    with pytest.raises(Task.DoesNotExist):
        transition_task(user=intruder, task=task, target="done")


@pytest.mark.parametrize("status", ["backlog", "in_progress", "in_review", "blocked"])
def test_any_open_task_can_be_planned_and_carried_over(user, status):
    task = Task.objects.create(user=user, title="Open", status=status)
    plan = DailyPlan.objects.create(
        user=user, local_date=date(2026, 11, 24), timezone_name="UTC"
    )

    item = add_plan_item(user=user, plan=plan, task=task, kind="secondary", position=0)
    moved = carry_over(user=user, item=item, destination_date=date(2026, 11, 25))

    assert moved.plan.local_date == date(2026, 11, 25)


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_closed_tasks_cannot_be_planned(user, status):
    task = Task.objects.create(user=user, title="Closed")
    transition_task(user=user, task=task, target=status)
    plan = DailyPlan.objects.create(
        user=user, local_date=date(2026, 11, 24), timezone_name="UTC"
    )

    with pytest.raises(ValidationError, match="open tasks"):
        add_plan_item(user=user, plan=plan, task=task, kind="secondary", position=0)
