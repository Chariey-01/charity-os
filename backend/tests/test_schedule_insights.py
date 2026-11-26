import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from challenges.models import Challenge
from execution.models import FocusSession
from health.models import ExerciseLog
from planning.categories import DEFAULT_CATEGORIES, ensure_default_categories
from planning.models import Area, DailyCapacity, DailyPlan, Task
from planning.services import add_plan_item

pytestmark = pytest.mark.django_db

NAIROBI = "Africa/Nairobi"
TODAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    # 2026-11-24 18:00 in Nairobi.
    monkeypatch.setattr(
        timezone, "now", lambda: datetime(2026, 11, 24, 15, 0, tzinfo=UTC)
    )


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        "insights@example.com", "password", timezone=NAIROBI
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def areas(user):
    ensure_default_categories(user)
    return {area.name: area for area in Area.objects.filter(user=user)}


def add(client, title, start, end, **extra):
    response = client.post(
        "/api/v1/schedule-entries",
        {"title": title, "start_local": start, "end_local": end, **extra},
        format="json",
    )
    assert response.status_code == 201, response.json()
    return response.json()


def session(user, area, minutes, started_at, **extra):
    return FocusSession.objects.create(
        user=user,
        area=area,
        title=extra.pop("title", "Focus"),
        is_deep_work=True,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=minutes),
        duration_seconds=minutes * 60,
        status=extra.pop("status", "completed"),
        timezone_snapshot=NAIROBI,
        area_label_snapshot=area.name,
    )


# --------------------------------------------------------------------------
# Today payload


def test_day_payload_progress_capacity_and_unscheduled_tasks(client, user, areas):
    DailyCapacity.objects.create(
        user=user,
        local_date=TODAY,
        timezone_name=NAIROBI,
        available_minutes=480,
        deep_work_minutes=180,
    )
    study = add(
        client,
        "Study",
        "2026-11-24T08:00",
        "2026-11-24T10:00",
        area=str(areas["Learning"].id),
    )
    shop = add(client, "Shopping", "2026-11-24T14:00", "2026-11-24T15:00")
    add(
        client,
        "Sleep",
        "2026-11-24T22:30",
        "2026-11-25T06:30",
        area=str(areas["Sleep"].id),
    )
    client.post(f"/api/v1/schedule-entries/{study['id']}/complete")
    client.post(f"/api/v1/schedule-entries/{shop['id']}/skip")
    scheduled_task = Task.objects.create(user=user, title="Has a slot")
    add(
        client,
        "Slot",
        "2026-11-24T16:00",
        "2026-11-24T17:00",
        task=str(scheduled_task.id),
    )
    plan = DailyPlan.objects.create(user=user, local_date=TODAY, timezone_name=NAIROBI)
    primary = Task.objects.create(user=user, title="Primary outcome")
    add_plan_item(user=user, plan=plan, task=primary, kind="primary", position=0)
    Task.objects.create(user=user, title="Backlog item")

    body = client.get("/api/v1/schedule/day").json()

    assert body["date"] == "2026-11-24"
    assert body["progress"]["planned"] == 4
    assert body["progress"]["completed"] == 1
    assert body["progress"]["skipped"] == 1
    assert body["progress"]["remaining"] == 2
    # Sleep and skipped entries do not consume working capacity.
    assert body["capacity"]["scheduled_minutes"] == 120 + 60
    assert body["capacity"]["remaining_minutes"] == 480 - 180
    titles = [task["title"] for task in body["unscheduled_tasks"]]
    assert titles[0] == "Primary outcome"
    assert "Backlog item" in titles
    assert "Has a slot" not in titles
    assert body["unscheduled_tasks"][0]["plan_kind"] == "primary"
    assert body["week"]["completed"] == 1
    assert body["week"]["next_milestone"] == 3


def test_day_payload_includes_active_challenge(client, user):
    Challenge.objects.create(
        user=user,
        name="Road to 2027",
        start_date=date(2026, 9, 27),
        end_date=date(2026, 12, 31),
        status="active",
        is_primary=True,
    )

    challenge = client.get("/api/v1/schedule/day").json()["challenge"]

    assert challenge["name"] == "Road to 2027"
    assert challenge["current_day"] == 59
    assert challenge["total_days"] == 96


def test_daily_plan_today_uses_user_timezone(client, monkeypatch):
    # 22:30 UTC on the 24th is already the 25th in Nairobi.
    monkeypatch.setattr(
        timezone, "now", lambda: datetime(2026, 11, 24, 22, 30, tzinfo=UTC)
    )
    body = client.get("/api/v1/daily-plans/today").json()
    assert body["plan"]["local_date"] == "2026-11-25"
    day = client.get("/api/v1/schedule/day").json()
    assert day["date"] == "2026-11-25"


# --------------------------------------------------------------------------
# Insights


def test_planned_versus_completed_and_no_fabricated_time(client, areas):
    done = add(client, "Errand", "2026-11-24T08:00", "2026-11-24T09:00")
    timed = add(
        client,
        "Gym",
        "2026-11-24T10:00",
        "2026-11-24T11:00",
        area=str(areas["Exercise"].id),
    )
    skipped = add(client, "Call", "2026-11-23T10:00", "2026-11-23T10:30")
    moved = add(client, "Read", "2026-11-23T12:00", "2026-11-23T13:00")
    client.post(f"/api/v1/schedule-entries/{done['id']}/complete")
    client.post(
        f"/api/v1/schedule-entries/{timed['id']}/complete",
        {"actual_minutes": 45},
        format="json",
    )
    client.post(f"/api/v1/schedule-entries/{skipped['id']}/skip")
    client.post(
        f"/api/v1/schedule-entries/{moved['id']}/reschedule",
        {"start_local": "2026-11-24T12:00", "end_local": "2026-11-24T13:00"},
        format="json",
    )

    data = client.get("/api/v1/insights?period=7d").json()

    days = {row["date"]: row for row in data["schedule_daily"]}
    assert days["2026-11-24"]["planned"] == 3
    assert days["2026-11-24"]["completed"] == 2
    assert days["2026-11-23"]["planned"] == 1
    assert days["2026-11-23"]["skipped"] == 1
    assert days["2026-11-23"]["rescheduled"] == 1
    assert data["totals"]["completed"] == 2
    # Only the 45 recorded minutes count; the untimed errand adds nothing.
    assert data["totals"]["tracked_minutes"] == 45
    exercise = next(row for row in data["category_time"] if row["label"] == "Exercise")
    assert exercise["actual_minutes"] == 45
    assert exercise["planned_minutes"] == 60
    assert len(data["schedule_daily"]) == 7


def test_linked_focus_time_is_counted_once(client, user, areas):
    learning = areas["Learning"]
    entry = add(
        client,
        "Study",
        "2026-11-24T08:00",
        "2026-11-24T09:00",
        area=str(learning.id),
        tracking="focus",
    )
    client.post(f"/api/v1/schedule-entries/{entry['id']}/start")
    linked = FocusSession.objects.get(schedule_entry__id=entry["id"])
    # Started an hour before the frozen clock (14:00 UTC = 17:00 Nairobi).
    FocusSession.objects.filter(pk=linked.pk).update(
        started_at=datetime(2026, 11, 24, 14, 0, tzinfo=UTC)
    )
    client.post(f"/api/v1/schedule-entries/{entry['id']}/complete")
    linked.refresh_from_db()
    assert linked.duration_seconds == 60 * 60
    session(user, learning, 30, datetime(2026, 11, 24, 12, 0, tzinfo=UTC))
    session(
        user,
        learning,
        99,
        datetime(2026, 11, 24, 13, 0, tzinfo=UTC),
        status="cancelled",
    )

    data = client.get("/api/v1/insights?period=7d").json()

    row = next(item for item in data["category_time"] if item["label"] == "Learning")
    assert row["actual_minutes"] == 60 + 30
    assert data["totals"]["focus_minutes"] == 90
    focus = {item["date"]: item["minutes"] for item in data["focus_daily"]}
    assert focus["2026-11-24"] == 90


def test_daily_grouping_uses_user_timezone(client, user, areas):
    # 21:30 UTC on the 23rd is 00:30 on the 24th in Nairobi.
    session(user, areas["Learning"], 20, datetime(2026, 11, 23, 21, 30, tzinfo=UTC))
    add(client, "Late", "2026-11-24T00:30", "2026-11-24T01:00")

    data = client.get("/api/v1/insights?period=7d").json()

    focus = {item["date"]: item["minutes"] for item in data["focus_daily"]}
    assert focus["2026-11-24"] == 20
    assert focus["2026-11-23"] == 0
    days = {row["date"]: row["planned"] for row in data["schedule_daily"]}
    assert days["2026-11-24"] == 1


def test_health_section_is_separate_and_deduplicated(client, user, areas):
    gym = add(
        client,
        "Gym",
        "2026-11-24T06:00",
        "2026-11-24T07:00",
        area=str(areas["Exercise"].id),
    )
    client.post(
        f"/api/v1/schedule-entries/{gym['id']}/complete",
        {"actual_minutes": 50},
        format="json",
    )
    run = add(
        client,
        "Run",
        "2026-11-23T06:00",
        "2026-11-23T06:30",
        area=str(areas["Exercise"].id),
    )
    client.post(
        f"/api/v1/schedule-entries/{run['id']}/complete",
        {"actual_minutes": 30},
        format="json",
    )
    # The same run was also logged in the health log: count it once.
    ExerciseLog.objects.create(
        user=user,
        activity="Run",
        started_at=datetime(2026, 11, 23, 3, 0, tzinfo=UTC),
        ended_at=datetime(2026, 11, 23, 3, 40, tzinfo=UTC),
    )
    sleep = add(
        client,
        "Sleep",
        "2026-11-23T22:00",
        "2026-11-24T06:00",
        area=str(areas["Sleep"].id),
        allow_overlap=True,
    )
    client.post(
        f"/api/v1/schedule-entries/{sleep['id']}/complete",
        {"actual_minutes": 450},
        format="json",
    )

    data = client.get("/api/v1/insights?period=7d").json()

    exercise = {row["date"]: row["minutes"] for row in data["health"]["exercise_daily"]}
    sleep_hours = {row["date"]: row["hours"] for row in data["health"]["sleep_daily"]}
    assert exercise["2026-11-24"] == 50
    assert exercise["2026-11-23"] == 40  # the log, not log + entry
    assert sleep_hours["2026-11-24"] == 7.5
    assert "exercise_daily" not in data  # health stays in its own section


def test_period_filters(client, user):
    Challenge.objects.create(
        user=user,
        name="Sprint",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 12, 31),
        status="active",
        is_primary=True,
    )
    add(client, "Old", "2026-01-05T09:00", "2026-01-05T10:00")

    lengths = {
        period: client.get(f"/api/v1/insights?period={period}").json()["period"]["days"]
        for period in ("7d", "30d", "90d", "challenge", "year", "all")
    }

    assert lengths["7d"] == 7
    assert lengths["30d"] == 30
    assert lengths["90d"] == 90
    assert lengths["challenge"] == 24
    assert lengths["year"] == (TODAY - date(2026, 1, 1)).days + 1
    assert lengths["all"] == (TODAY - date(2026, 1, 5)).days + 1
    assert client.get("/api/v1/insights?period=forever").status_code == 400


def test_weekly_consistency_and_gentle_gamification(client, user, areas):
    client.patch("/api/v1/preferences", {"show_streaks": True}, format="json")
    for offset in range(4):
        day = date(2026, 11, 23) + timedelta(days=offset - 7)
        entry = add(
            client,
            f"Walk {offset}",
            f"{day}T07:00",
            f"{day}T07:30",
            area=str(areas["Exercise"].id),
        )
        client.post(f"/api/v1/schedule-entries/{entry['id']}/complete")
    this_week = (
        ("2026-11-23T07:00", "2026-11-23T08:00", "Learning"),
        ("2026-11-24T07:00", "2026-11-24T08:00", "Social"),
        ("2026-11-24T09:00", "2026-11-24T10:00", "Exercise"),
    )
    for index, (start, end, area) in enumerate(this_week):
        entry = add(client, f"This week {index}", start, end, area=str(areas[area].id))
        client.post(f"/api/v1/schedule-entries/{entry['id']}/complete")

    week = client.get("/api/v1/insights?period=30d").json()["week"]

    assert week["week_start"] == "2026-11-23"
    assert week["completed"] == 3
    assert week["milestones"][0] == {"target": 3, "reached": True}
    assert week["next_milestone"] == 7
    badges = {badge["key"]: badge["earned"] for badge in week["badges"]}
    assert badges["first_step"] is True
    assert badges["well_rounded"] is True
    assert badges["steady"] is False
    assert week["active_days"] == 2
    # Last week had 4 active days. This unfinished week (2 so far) neither
    # adds to the streak yet nor breaks it.
    assert week["streak_weeks"] == 1
    assert not any("hour" in badge["title"].lower() for badge in week["badges"])


def test_streaks_are_hidden_unless_enabled(client):
    assert client.get("/api/v1/insights").json()["week"]["streak_weeks"] is None


# --------------------------------------------------------------------------
# Preferences and categories


def test_preferences_round_trip_and_validation(client):
    defaults = client.get("/api/v1/preferences").json()
    assert defaults["reminders_enabled"] is False
    assert defaults["show_streaks"] is False

    updated = client.patch(
        "/api/v1/preferences",
        {
            "reminders_enabled": True,
            "reminder_lead_minutes": 15,
            "default_today_view": "timeline",
        },
        format="json",
    )
    invalid = client.patch(
        "/api/v1/preferences", {"reminder_lead_minutes": 500}, format="json"
    )

    assert updated.status_code == 200
    assert updated.json()["reminder_lead_minutes"] == 15
    assert invalid.status_code == 400


def test_default_categories_are_idempotent_and_respect_choices(client, user):
    Area.objects.create(user=user, name="exercise", slug="exercise", color="#123456")

    first = client.post("/api/v1/areas/ensure-defaults").json()
    second = client.post("/api/v1/areas/ensure-defaults").json()

    assert first["created"] == len(DEFAULT_CATEGORIES) - 1
    assert second["created"] == 0
    names = [area["name"] for area in second["areas"]]
    assert names.count("exercise") == 1 and "Exercise" not in names
    kept = Area.objects.get(user=user, slug="exercise")
    assert kept.color == "#123456"  # user's colour is kept
    assert kept.health_kind == "exercise"  # health kind is filled in
    listed = client.get("/api/v1/areas").json()
    assert [area["name"] for area in listed][:2] == ["exercise", "Software Engineering"]


def test_service_validation_errors_are_400_not_500(client, user, areas):
    payload = {
        "title": "Focus",
        "area": str(areas["Learning"].id),
        "is_deep_work": True,
    }
    first = client.post(
        "/api/v1/sessions/start", {**payload, "id": str(uuid.uuid4())}, format="json"
    )
    second = client.post(
        "/api/v1/sessions/start", {**payload, "id": str(uuid.uuid4())}, format="json"
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.json()["error"]["message"] == "A focus session is already open."
