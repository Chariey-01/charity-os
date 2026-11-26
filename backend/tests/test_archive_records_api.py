"""Archive instead of delete: roadmaps, records, reflections and health logs."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from execution.models import FocusSession
from health.models import (
    DailyNutritionRating,
    DailyWaterTotal,
    ExerciseLog,
    MealLog,
    SleepLog,
)
from planning.models import Area
from records.models import Accomplishment, Evidence
from reflections.models import DailyReflection, WeeklyReview
from roadmaps.models import (
    Roadmap,
    RoadmapNode,
    RoadmapNodePrerequisite,
    RoadmapResource,
)

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        "records@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def roadmap(user):
    return Roadmap.objects.create(user=user, title="Python")


def node(user, roadmap, title, parent=None, **extra):
    return RoadmapNode.objects.create(
        user=user,
        roadmap=roadmap,
        parent=parent,
        title=title,
        node_type=extra.pop("node_type", "item"),
        **extra,
    )


def make(resource, user, roadmap):
    day = date(2026, 11, 20)
    if resource == "roadmaps":
        return roadmap
    if resource == "roadmap-nodes":
        return node(user, roadmap, "Loops")
    if resource == "roadmap-resources":
        return RoadmapResource.objects.create(
            user=user,
            node=node(user, roadmap, "N"),
            label="Docs",
            url="https://docs.python.org",
        )
    if resource == "evidence":
        return Evidence.objects.create(
            user=user, kind="note", text="t", roadmap_node=node(user, roadmap, "E")
        )
    if resource == "accomplishments":
        return Accomplishment.objects.create(
            user=user, local_date=day, timezone_name="UTC", title="Shipped"
        )
    if resource == "sleep-logs":
        return SleepLog.objects.create(
            user=user,
            started_at=NOW - timedelta(hours=8),
            woke_at=NOW - timedelta(hours=1),
            timezone_name="UTC",
            wake_local_date=NOW.date(),
        )
    if resource == "exercise-logs":
        return ExerciseLog.objects.create(
            user=user,
            started_at=NOW - timedelta(minutes=50),
            ended_at=NOW - timedelta(minutes=20),
            activity="Run",
        )
    if resource == "meal-logs":
        return MealLog.objects.create(
            user=user,
            local_date=day,
            timezone_name="UTC",
            meal_type="lunch",
            description="Rice",
        )
    if resource == "water":
        return DailyWaterTotal.objects.create(
            user=user, local_date=day, timezone_name="UTC", total_ml=900
        )
    if resource == "nutrition":
        return DailyNutritionRating.objects.create(
            user=user, local_date=day, timezone_name="UTC", rating=4
        )
    if resource == "daily-reflections":
        return DailyReflection.objects.create(
            user=user, local_date=day, timezone_name="UTC", went_well="A"
        )
    return WeeklyReview.objects.create(
        user=user,
        week_start_date=date(2026, 11, 16),
        week_end_date=date(2026, 11, 22),
        timezone_name="UTC",
    )


RESOURCES = (
    "roadmaps",
    "roadmap-nodes",
    "roadmap-resources",
    "evidence",
    "accomplishments",
    "sleep-logs",
    "exercise-logs",
    "meal-logs",
    "water",
    "nutrition",
    "daily-reflections",
    "weekly-reviews",
)


@pytest.mark.parametrize("resource", RESOURCES)
def test_archive_not_delete(client, user, roadmap, resource):
    record = make(resource, user, roadmap)
    url = f"/api/v1/{resource}/{record.id}"

    deleted = client.delete(url)
    archived = client.post(f"{url}/archive")
    listed = {row["id"] for row in client.get(f"/api/v1/{resource}").json()}
    included = {
        row["id"] for row in client.get(f"/api/v1/{resource}?archived=include").json()
    }
    restored = client.post(f"{url}/restore")

    assert deleted.status_code == 405
    assert deleted.json()["error"]["code"] == "archive_instead"
    assert type(record).objects.filter(pk=record.pk).exists()
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert str(record.id) not in listed
    assert str(record.id) in included
    assert restored.json()["archived_at"] is None
    patched = client.patch(url, {"archived_at": NOW.isoformat()}, format="json")
    assert patched.status_code == 400


def test_prerequisite_links_stay_deletable(client, user, roadmap):
    first = node(user, roadmap, "Basics")
    second = node(user, roadmap, "Advanced")
    edge = RoadmapNodePrerequisite.objects.create(
        user=user, node=second, prerequisite=first
    )

    response = client.delete(f"/api/v1/roadmap-prerequisites/{edge.id}")

    assert response.status_code == 204
    assert not RoadmapNodePrerequisite.objects.filter(pk=edge.pk).exists()
    assert RoadmapNode.objects.filter(pk__in=(first.pk, second.pk)).count() == 2


def test_archiving_a_node_archives_its_subtree_and_restore_brings_it_back(
    client, user, roadmap, monkeypatch
):
    section = node(user, roadmap, "Section", node_type="section")
    topic = node(user, roadmap, "Topic", parent=section, node_type="topic")
    item = node(user, roadmap, "Item", parent=topic)
    earlier = node(user, roadmap, "Dropped earlier", parent=topic)
    client.post(f"/api/v1/roadmap-nodes/{earlier.id}/archive")
    monkeypatch.setattr(timezone, "now", lambda: NOW + timedelta(minutes=5))

    client.post(f"/api/v1/roadmap-nodes/{section.id}/archive")
    states = dict(
        RoadmapNode.objects.filter(roadmap=roadmap).values_list("title", "archived_at")
    )
    blocked = client.post(f"/api/v1/roadmap-nodes/{item.id}/restore")
    client.post(f"/api/v1/roadmap-nodes/{section.id}/restore")
    after = dict(
        RoadmapNode.objects.filter(roadmap=roadmap).values_list("title", "archived_at")
    )

    later = NOW + timedelta(minutes=5)
    assert states == {
        "Section": later,
        "Topic": later,
        "Item": later,
        "Dropped earlier": NOW,
    }
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "parent_archived"
    assert after == {
        "Section": None,
        "Topic": None,
        "Item": None,
        "Dropped earlier": NOW,
    }


def test_subtree_archive_survives_a_parent_cycle_in_old_data(user, roadmap):
    from roadmaps.services import archive_node

    first = node(user, roadmap, "A")
    second = node(user, roadmap, "B", parent=first)
    RoadmapNode.objects.filter(pk=first.pk).update(parent=second)  # legacy cycle

    archive_node(user=user, node=first)

    assert RoadmapNode.objects.filter(archived_at__isnull=True).count() == 0


def test_tree_progress_and_next_actions_leave_out_archived_items(client, user, roadmap):
    done = node(user, roadmap, "Done", state="completed")
    kept = node(user, roadmap, "Next")
    dropped = node(user, roadmap, "Dropped")
    gate = node(user, roadmap, "Gate")
    blocked = node(user, roadmap, "Blocked by an archived gate")
    RoadmapNodePrerequisite.objects.create(user=user, node=blocked, prerequisite=gate)
    resource = RoadmapResource.objects.create(
        user=user, node=kept, label="Docs", url="https://x.org"
    )
    Evidence.objects.create(user=user, kind="note", text="old", roadmap_node=kept)
    archived_evidence = Evidence.objects.create(
        user=user, kind="note", text="x", roadmap_node=kept
    )
    for path in (
        f"roadmap-nodes/{dropped.id}",
        f"roadmap-nodes/{gate.id}",
        f"roadmap-resources/{resource.id}",
        f"evidence/{archived_evidence.id}",
    ):
        client.post(f"/api/v1/{path}/archive")

    tree = client.get(f"/api/v1/roadmaps/{roadmap.id}/tree").json()["nodes"]
    full = client.get(f"/api/v1/roadmaps/{roadmap.id}/tree?archived=include").json()
    progress = client.get(f"/api/v1/roadmaps/{roadmap.id}/progress").json()
    actions = client.get("/api/v1/roadmaps/next-actions?limit=20").json()

    titles = {row["title"] for row in tree}
    assert titles == {"Done", "Next", "Blocked by an archived gate"}
    next_row = next(row for row in tree if row["title"] == "Next")
    assert next_row["resources"] == []
    assert next_row["evidence_count"] == 1
    assert len(full["nodes"]) == 5
    assert progress["eligible_items"] == 3
    assert progress["completed_eligible_items"] == 1
    assert {row["title"] for row in actions} == {
        "Next",
        "Blocked by an archived gate",
    }
    assert str(done.id) not in {row["node_id"] for row in actions}
    assert (
        client.get(f"/api/v1/roadmaps/{roadmap.id}/tree?archived=x").status_code == 400
    )


def test_archived_roadmaps_leave_metrics_and_next_actions(client, user, roadmap):
    node(user, roadmap, "Next")
    other = Roadmap.objects.create(user=user, title="Kept")

    client.post(f"/api/v1/roadmaps/{roadmap.id}/archive")

    metrics = client.get("/api/v1/analytics/metrics?period=7d").json()
    assert [row["id"] for row in metrics["roadmaps"]] == [str(other.id)]
    assert client.get("/api/v1/roadmaps/next-actions").json() == []


def test_archived_nodes_keep_their_focus_time(client, user, roadmap):
    item = node(user, roadmap, "Item")
    area = Area.objects.create(user=user, name="Study", slug="study")
    FocusSession.objects.create(
        user=user,
        area=area,
        roadmap_item=item,
        title="Focus",
        is_deep_work=True,
        started_at=NOW - timedelta(hours=2),
        ended_at=NOW - timedelta(hours=1),
        duration_seconds=3600,
        status="completed",
        timezone_snapshot="UTC",
        area_label_snapshot="Study",
    )

    client.post(f"/api/v1/roadmap-nodes/{item.id}/archive")

    tree = client.get(f"/api/v1/roadmaps/{roadmap.id}/tree?archived=include").json()
    assert tree["nodes"][0]["time_invested_seconds"] == 3600
    assert tree["nodes"][0]["archived_at"] is not None


def test_archived_health_logs_still_count_in_insights(client, user, roadmap):
    sleep = make("sleep-logs", user, roadmap)
    exercise = make("exercise-logs", user, roadmap)
    views = ("/api/v1/insights?period=7d", "/api/v1/analytics/metrics?period=7d")
    before = [client.get(path).json() for path in views]

    client.post(f"/api/v1/sleep-logs/{sleep.id}/archive")
    client.post(f"/api/v1/exercise-logs/{exercise.id}/archive")

    assert [client.get(path).json() for path in views] == before
    assert any(row["hours"] for row in before[1]["sleep_trend"])
