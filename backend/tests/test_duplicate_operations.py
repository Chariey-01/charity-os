"""Phase 0B, B3: duplicates and invalid combinations are field errors, never 500."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from api import serializers as api_serializers
from api.constraints import MESSAGES
from challenges.models import Challenge
from health.models import DailyNutritionRating, DailyWaterTotal, ExerciseLog, SleepLog
from planning.models import Area, DailyPlan, DailyPlanItem, Task
from reflections.models import DailyReflection
from roadmaps.models import (
    Roadmap,
    RoadmapNode,
    RoadmapNodePrerequisite,
    RoadmapResource,
)

pytestmark = pytest.mark.django_db
T0 = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
DAY = date(2026, 11, 24)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        "dupes@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    api.raise_request_exception = False
    return api


def node(user, title="N"):
    roadmap = Roadmap.objects.create(user=user, title=f"R {title}")
    return RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title=title, node_type="item"
    )


def scenarios(user):
    """(path, body, field, model whose count must not change) per duplicate."""
    Area.objects.create(user=user, name="Study", slug="study")
    Challenge.objects.create(
        user=user,
        name="Road to 2027",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 12, 5),
        is_primary=True,
    )
    DailyPlan.objects.create(user=user, local_date=DAY, timezone_name="UTC")
    resource_node = node(user, "resources")
    RoadmapResource.objects.create(
        user=user, node=resource_node, label="Docs", url="https://x.org", position=0
    )
    first, second = node(user, "a"), node(user, "b")
    RoadmapNodePrerequisite.objects.create(user=user, node=second, prerequisite=first)
    SleepLog.objects.create(
        user=user,
        started_at=T0,
        woke_at=T0 + timedelta(hours=8),
        timezone_name="UTC",
        wake_local_date=date(2026, 11, 21),
    )
    ExerciseLog.objects.create(
        user=user,
        started_at=T0 + timedelta(hours=10),
        ended_at=T0 + timedelta(hours=11),
        activity="Run",
    )
    return [
        ("areas", {"name": "STUDY", "slug": "study-2"}, "name", Area),
        ("areas", {"name": "Other", "slug": "study"}, "slug", Area),
        (
            "challenges",
            {
                "name": "road to 2027",
                "start_date": "2026-09-01",
                "end_date": "2026-12-01",
            },
            "name",
            Challenge,
        ),
        (
            "challenges",
            {
                "name": "Second",
                "start_date": "2026-09-01",
                "end_date": "2026-12-01",
                "is_primary": True,
            },
            "is_primary",
            Challenge,
        ),
        (
            "challenges",
            {"name": "Backwards", "start_date": "2026-09-02", "end_date": "2026-09-01"},
            "end_date",
            Challenge,
        ),
        (
            "daily-plans",
            {"local_date": str(DAY), "timezone_name": "UTC"},
            "local_date",
            DailyPlan,
        ),
        (
            "roadmap-resources",
            {"node": str(resource_node.id), "label": "Again", "url": "https://y.org"},
            "position",
            RoadmapResource,
        ),
        (
            "roadmap-prerequisites",
            {"node": str(second.id), "prerequisite": str(first.id)},
            "prerequisite",
            RoadmapNodePrerequisite,
        ),
        (
            "sleep-logs",
            {
                "started_at": (T0 + timedelta(hours=2)).isoformat(),
                "woke_at": (T0 + timedelta(hours=9)).isoformat(),
                "timezone_name": "UTC",
            },
            "started_at",
            SleepLog,
        ),
        (
            "exercise-logs",
            {
                "started_at": (T0 + timedelta(hours=10, minutes=30)).isoformat(),
                "ended_at": (T0 + timedelta(hours=12)).isoformat(),
                "activity": "Swim",
            },
            "started_at",
            ExerciseLog,
        ),
        (
            "capacities",
            {
                "local_date": "2026-11-30",
                "timezone_name": "UTC",
                "available_minutes": 60,
                "deep_work_minutes": 90,
            },
            "deep_work_minutes",
            None,
        ),
        (
            "nutrition",
            {"local_date": "2026-11-30", "timezone_name": "UTC", "rating": 6},
            "rating",
            DailyNutritionRating,
        ),
    ]


def test_every_duplicate_or_invalid_combination_is_a_field_error(client, user):
    for path, body, field, model in scenarios(user):
        before = model.objects.count() if model else None

        response = client.post(f"/api/v1/{path}", body, format="json")

        assert response.status_code == 400, (
            path,
            response.status_code,
            response.content,
        )
        payload = response.json()
        fields = payload.get("error", {}).get("fields") or payload
        assert field in fields, (path, payload)
        if model:
            assert model.objects.count() == before, path


def test_audit_probe_second_reflection_for_a_day(client):
    """2026-11-24 audit: the second daily reflection for a day answered 500.

    Phase 0C (S8) defines the duplicate contract for reflections: an identical
    retry returns the existing record, different words are a 409 conflict
    (tests/test_reflection_revisions.py). Never a 500, never a second row.
    """
    body = {"local_date": "2026-11-24", "timezone_name": "UTC", "went_well": "x"}

    first = client.post("/api/v1/daily-reflections", body, format="json")
    retried = client.post("/api/v1/daily-reflections", body, format="json")
    different = client.post(
        "/api/v1/daily-reflections", {**body, "went_well": "y"}, format="json"
    )

    assert (first.status_code, retried.status_code, different.status_code) == (
        201,
        200,
        409,
    )
    assert DailyReflection.objects.count() == 1


def test_updates_are_checked_against_other_rows_not_themselves(client, user):
    keep = Area.objects.create(user=user, name="Study", slug="study")
    other = Area.objects.create(user=user, name="Work", slug="work")

    same = client.patch(f"/api/v1/areas/{keep.id}", {"name": "study"}, format="json")
    clash = client.patch(f"/api/v1/areas/{other.id}", {"name": "STUDY"}, format="json")

    assert same.status_code == 200
    assert clash.status_code == 400 and "name" in clash.json()


@pytest.mark.parametrize(
    "path, model, field, first, second",
    [
        ("water", DailyWaterTotal, "total_ml", 500, 1250),
        ("nutrition", DailyNutritionRating, "rating", 3, 4),
    ],
)
def test_daily_totals_saved_twice_update_the_day(
    client, path, model, field, first, second
):
    body = {"local_date": "2026-11-24", "timezone_name": "UTC"}

    created = client.post(f"/api/v1/{path}", {**body, field: first}, format="json")
    updated = client.post(f"/api/v1/{path}", {**body, field: second}, format="json")

    assert (created.status_code, updated.status_code) == (201, 200)
    assert updated.json()["id"] == created.json()["id"]
    assert model.objects.count() == 1
    assert getattr(model.objects.get(), field) == second


def test_an_archived_daily_total_is_not_silently_rewritten(client):
    body = {"local_date": "2026-11-24", "timezone_name": "UTC", "total_ml": 500}
    created = client.post("/api/v1/water", body, format="json").json()
    client.post(f"/api/v1/water/{created['id']}/archive")

    response = client.post("/api/v1/water", {**body, "total_ml": 900}, format="json")

    assert response.status_code == 400
    assert DailyWaterTotal.objects.get().total_ml == 500


def test_plan_items_append_and_never_collide(client, user):
    plan = DailyPlan.objects.create(user=user, local_date=DAY, timezone_name="UTC")
    tasks = [Task.objects.create(user=user, title=f"T{i}") for i in range(3)]

    positions = [
        client.post(
            "/api/v1/daily-plan-items",
            {"plan": str(plan.id), "task": str(task.id)},
            format="json",
        ).json()["position"]
        for task in tasks[:2]
    ]
    taken = client.post(
        "/api/v1/daily-plan-items",
        {"plan": str(plan.id), "task": str(tasks[2].id), "position": 1},
        format="json",
    )
    twice = client.post(
        "/api/v1/daily-plan-items",
        {"plan": str(plan.id), "task": str(tasks[0].id)},
        format="json",
    )

    assert positions == [0, 1]
    assert taken.status_code == 400
    assert twice.status_code == 400 and "task" in twice.json()
    assert DailyPlanItem.objects.count() == 2


def test_carry_over_appends_after_the_last_item(client, user):
    today = DailyPlan.objects.create(user=user, local_date=DAY, timezone_name="UTC")
    tomorrow = DailyPlan.objects.create(
        user=user, local_date=DAY + timedelta(days=1), timezone_name="UTC"
    )
    for position in (0, 2):  # a gap: counting items would give position 2
        task = Task.objects.create(user=user, title=f"there {position}")
        DailyPlanItem.objects.create(
            user=user, plan=tomorrow, task=task, title_snapshot="x", position=position
        )
    moving = Task.objects.create(user=user, title="moving")
    item = DailyPlanItem.objects.create(
        user=user, plan=today, task=moving, title_snapshot="moving"
    )

    response = client.post(
        f"/api/v1/daily-plan-items/{item.id}/carry-over",
        {"destination_date": str(DAY + timedelta(days=1))},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["position"] == 3


def test_a_race_past_validation_is_a_409_not_a_500(client, user, monkeypatch):
    Area.objects.create(user=user, name="Study", slug="study")
    monkeypatch.setattr(
        api_serializers.OwnedModelSerializer,
        "_validate_constraints",
        lambda self, attrs, user: None,
    )

    response = client.post(
        "/api/v1/areas", {"name": "study", "slug": "study-2"}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "name" in response.json()["error"]["fields"]
    assert Area.objects.count() == 1


def test_every_constraint_has_a_user_facing_message():
    owned = [
        model
        for model in apps.get_models()
        if model._meta.app_label
        in {
            "planning",
            "challenges",
            "roadmaps",
            "records",
            "health",
            "reflections",
            "execution",
        }
    ]
    missing = [
        (model._meta.label, constraint.name)
        for model in owned
        for constraint in model._meta.constraints
        if constraint.name not in MESSAGES
    ]

    assert missing == []
