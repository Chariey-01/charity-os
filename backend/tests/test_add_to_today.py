"""Phase 0B, B4: Add to Today (and Start focus) is one transaction."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

import planning.services as planning_services
from execution.models import FocusSession
from planning.models import Area, DailyPlan, DailyPlanItem, PlanningEvent, Task
from roadmaps.models import Roadmap, RoadmapNode

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
TODAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        "today@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def study(user):
    return Area.objects.create(user=user, name="Study", slug="study")


@pytest.fixture
def node(user, study):
    roadmap = Roadmap.objects.create(user=user, title="Python", area=study)
    return RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Loops", node_type="item"
    )


def add(client, node, **body):
    return client.post(
        f"/api/v1/roadmap-nodes/{node.id}/add-to-today", body, format="json"
    )


def counts():
    return (
        Task.objects.count(),
        DailyPlan.objects.count(),
        DailyPlanItem.objects.count(),
        PlanningEvent.objects.count(),
        FocusSession.objects.count(),
    )


def test_first_tap_creates_and_plans_and_repeats_change_nothing(client, node):
    first = add(client, node)
    after_first = counts()
    second = add(client, node)
    third = add(client, node)

    assert first.status_code == 200
    body = first.json()
    assert body["created_task"] is True
    assert body["task"]["roadmap_item"] == str(node.id)
    assert body["plan_item"]["task"] == body["task"]["id"]
    assert body["session"] is None
    assert DailyPlan.objects.get().local_date == TODAY
    assert second.json()["created_task"] is False
    assert third.json()["plan_item"]["id"] == body["plan_item"]["id"]
    assert counts() == after_first  # no duplicate task or plan item
    assert after_first[:3] == (1, 1, 1)


def test_an_existing_open_task_is_reused(client, user, node):
    existing = Task.objects.create(user=user, title="Loops", roadmap_item=node)

    body = add(client, node).json()

    assert body["task"]["id"] == str(existing.id)
    assert Task.objects.count() == 1


def test_a_task_planned_for_yesterday_is_carried_over(client, user, node):
    task = Task.objects.create(user=user, title="Loops", roadmap_item=node)
    yesterday = DailyPlan.objects.create(
        user=user, local_date=TODAY - timedelta(days=1), timezone_name="UTC"
    )
    old = DailyPlanItem.objects.create(
        user=user, plan=yesterday, task=task, title_snapshot="Loops"
    )

    body = add(client, node).json()

    old.refresh_from_db()
    assert old.state == "carried_forward"
    assert body["plan_item"]["plan"] != str(yesterday.id)
    assert PlanningEvent.objects.filter(event_type="carried_over").count() == 1


def test_start_focus_starts_the_session_in_the_same_operation(client, node, study):
    session_id = str(uuid.uuid4())

    body = add(client, node, start_focus=True, session_id=session_id).json()

    assert body["session"]["id"] == session_id
    session = FocusSession.objects.get()
    assert (session.area_id, session.task_id, session.roadmap_item_id) == (
        study.id,
        uuid.UUID(body["task"]["id"]),
        node.id,
    )


def test_start_focus_without_a_category_writes_nothing(client, user):
    roadmap = Roadmap.objects.create(user=user, title="No category")
    bare = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Item", node_type="item"
    )

    response = add(client, bare, start_focus=True, session_id=str(uuid.uuid4()))

    assert response.status_code == 400
    assert counts() == (0, 0, 0, 0, 0)


def test_start_focus_failing_rolls_back_the_task_and_plan(client, user, node, study):
    FocusSession.objects.create(
        user=user,
        area=study,
        title="Already running",
        is_deep_work=True,
        started_at=NOW,
        timezone_snapshot="UTC",
        area_label_snapshot="Study",
    )
    before = counts()

    response = add(client, node, start_focus=True, session_id=str(uuid.uuid4()))

    assert response.status_code == 400
    assert counts() == before
    assert not Task.objects.filter(roadmap_item=node).exists()


def test_any_failure_after_the_task_is_created_rolls_everything_back(
    client, node, monkeypatch
):
    def fail(**kwargs):
        raise ValidationError("Injected failure while planning.")

    monkeypatch.setattr(planning_services, "add_plan_item", fail)

    response = add(client, node)

    assert response.status_code == 400
    assert counts() == (0, 0, 0, 0, 0)


def test_archived_or_foreign_items_are_refused(client, user, node, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "password")
    theirs = RoadmapNode.objects.create(
        user=other,
        roadmap=Roadmap.objects.create(user=other, title="T"),
        title="T",
        node_type="item",
    )
    client.post(f"/api/v1/roadmap-nodes/{node.id}/archive")

    assert add(client, node).status_code == 400
    assert add(client, theirs).status_code == 404
    assert counts() == (0, 0, 0, 0, 0)
