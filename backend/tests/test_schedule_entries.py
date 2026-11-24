import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from execution.models import FocusSession
from planning.models import Area, Task
from scheduling.models import ScheduleEntry

pytestmark = pytest.mark.django_db

NAIROBI = "Africa/Nairobi"


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        "planner@example.com", "password", timezone=NAIROBI
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def study(user):
    return Area.objects.create(
        user=user, name="Learning", slug="learning", color="#1D4ED8"
    )


@pytest.fixture
def exercise(user):
    return Area.objects.create(
        user=user,
        name="Exercise",
        slug="exercise",
        color="#C2410C",
        health_kind="exercise",
    )


@pytest.fixture
def clock(monkeypatch):
    """Controllable server clock for timing tests."""

    state = {"now": datetime(2026, 11, 24, 6, 0, tzinfo=UTC)}

    def now():
        return state["now"]

    monkeypatch.setattr(timezone, "now", now)

    def advance(**delta):
        state["now"] += timedelta(**delta)
        return state["now"]

    state["advance"] = advance
    return state


def create(client, **overrides):
    payload = {
        "title": "Study algorithms",
        "start_local": "2026-11-24T09:00",
        "end_local": "2026-11-24T10:30",
        **overrides,
    }
    return client.post("/api/v1/schedule-entries", payload, format="json")


# --------------------------------------------------------------------------
# Creating, updating and time validation


def test_create_converts_local_time_with_user_timezone(client, study):
    response = create(client, area=str(study.id))

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["timezone_name"] == NAIROBI
    assert body["start_at"].startswith("2026-11-24T06:00:00")  # UTC+3
    assert body["start_local"] == "2026-11-24T09:00"
    assert body["end_local"] == "2026-11-24T10:30"
    assert body["local_date"] == "2026-11-24"
    assert body["planned_minutes"] == 90
    assert body["status"] == "scheduled"
    assert body["color"] == "#1D4ED8"
    assert body["area_label"] == "Learning"
    assert body["actual_seconds"] is None


def test_quick_add_needs_only_title_and_times(client):
    response = create(client, title="Buy groceries")
    assert response.status_code == 201
    assert response.json()["area"] is None


def test_create_with_client_id_is_idempotent(client):
    entry_id = str(uuid.uuid4())
    first = create(client, id=entry_id)
    replay = create(client, id=entry_id, title="Different title")

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["title"] == "Study algorithms"
    assert ScheduleEntry.objects.count() == 1


def test_client_id_owned_by_someone_else_is_rejected(client):
    other = get_user_model().objects.create_user("x@example.com", "password")
    other_client = APIClient()
    other_client.force_authenticate(other)
    entry_id = str(uuid.uuid4())
    assert create(other_client, id=entry_id).status_code == 201

    response = create(client, id=entry_id)

    assert response.status_code == 400
    assert ScheduleEntry.objects.get(pk=entry_id).user == other


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"end_local": "2026-11-24T08:00"}, "end_local"),
        ({"end_local": "2026-11-24T09:00"}, "end_local"),
        ({"end_local": "2026-11-25T09:30"}, "end_local"),
        ({"start_local": "not-a-time"}, "start_local"),
        ({"start_local": "2026-11-24T09:00+03:00"}, "start_local"),
        ({"timezone_name": "Mars/Olympus"}, "timezone_name"),
        ({"title": "   "}, "title"),
    ],
)
def test_time_and_field_validation(client, overrides, field):
    response = create(client, **overrides)

    assert response.status_code == 400
    body = response.json()
    assert field in body.get("error", {}).get("fields", body)


def test_nonexistent_dst_wall_clock_time_is_rejected(client):
    response = create(
        client,
        timezone_name="America/New_York",
        start_local="2026-03-08T02:30",
        end_local="2026-03-08T03:30",
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_planned_duration_is_computed_across_dst_change(client):
    response = create(
        client,
        title="Night shift",
        timezone_name="America/New_York",
        start_local="2026-11-01T00:00",
        end_local="2026-11-01T03:00",
    )
    assert response.status_code == 201
    # Clocks fall back at 02:00 so three wall-clock hours are four real hours.
    assert response.json()["planned_minutes"] == 240


def test_explicit_timezone_is_preserved(client):
    response = create(client, timezone_name="Europe/London")
    body = response.json()
    assert body["timezone_name"] == "Europe/London"
    assert body["start_at"].startswith("2026-11-24T09:00:00")


def test_cross_midnight_entry_appears_on_both_days(client):
    create(
        client,
        title="Sleep",
        start_local="2026-11-24T22:30",
        end_local="2026-11-25T06:30",
    )

    first = client.get("/api/v1/schedule-entries?start=2026-11-24").json()
    second = client.get("/api/v1/schedule-entries?start=2026-11-25").json()
    third = client.get("/api/v1/schedule-entries?start=2026-11-26").json()

    assert [entry["title"] for entry in first] == ["Sleep"]
    assert [entry["title"] for entry in second] == ["Sleep"]
    assert third == []


def test_list_filters_by_user_local_day_range(client):
    create(
        client,
        title="Late",
        start_local="2026-11-24T23:30",
        end_local="2026-11-24T23:59",
    )
    create(
        client,
        title="Next",
        start_local="2026-11-25T00:30",
        end_local="2026-11-25T01:00",
    )

    day = client.get("/api/v1/schedule-entries?start=2026-11-24&end=2026-11-24").json()
    week = client.get("/api/v1/schedule-entries?start=2026-11-23&end=2026-11-29").json()

    assert [entry["title"] for entry in day] == ["Late"]
    assert [entry["title"] for entry in week] == ["Late", "Next"]
    bad = client.get("/api/v1/schedule-entries?start=2026-11-24&end=2026-11-20")
    assert bad.status_code == 400


def test_update_edits_and_moves_scheduled_entry(client, study):
    entry = create(client).json()

    response = client.patch(
        f"/api/v1/schedule-entries/{entry['id']}",
        {
            "title": "Study graphs",
            "area": str(study.id),
            "start_local": "2026-11-24T14:00",
            "expected_version": entry["version"],
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["title"] == "Study graphs"
    assert body["start_local"] == "2026-11-24T14:00"
    assert body["end_local"] == "2026-11-24T15:30"  # duration preserved
    assert body["area_label"] == "Learning"
    assert body["version"] == entry["version"] + 1


def test_stale_version_is_a_409_conflict(client):
    entry = create(client).json()
    client.patch(
        f"/api/v1/schedule-entries/{entry['id']}", {"title": "A"}, format="json"
    )

    response = client.patch(
        f"/api/v1/schedule-entries/{entry['id']}",
        {"title": "B", "expected_version": entry["version"]},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


def test_moving_a_started_entry_requires_reschedule(client):
    entry = create(client).json()
    client.post(f"/api/v1/schedule-entries/{entry['id']}/start")

    response = client.patch(
        f"/api/v1/schedule-entries/{entry['id']}",
        {"start_local": "2026-11-24T15:00"},
        format="json",
    )

    assert response.status_code == 400
    assert "Reschedule" in response.json()["detail"]


def test_closed_entry_only_accepts_notes(client):
    entry = create(client).json()
    client.post(f"/api/v1/schedule-entries/{entry['id']}/skip")

    notes = client.patch(
        f"/api/v1/schedule-entries/{entry['id']}", {"notes": "Was ill"}, format="json"
    )
    title = client.patch(
        f"/api/v1/schedule-entries/{entry['id']}", {"title": "New"}, format="json"
    )

    assert notes.status_code == 200
    assert notes.json()["notes"] == "Was ill"
    assert title.status_code == 400


def test_delete_is_not_offered(client):
    entry = create(client).json()
    response = client.delete(f"/api/v1/schedule-entries/{entry['id']}")
    assert response.status_code == 405


# --------------------------------------------------------------------------
# Overlaps


def test_overlap_is_rejected_unless_explicitly_allowed(client):
    create(client, title="Lecture")

    blocked = create(
        client,
        title="Gym",
        start_local="2026-11-24T10:00",
        end_local="2026-11-24T11:00",
    )
    allowed = create(
        client,
        title="Podcast",
        start_local="2026-11-24T10:00",
        end_local="2026-11-24T11:00",
        allow_overlap=True,
    )

    assert blocked.status_code == 409
    error = blocked.json()["error"]
    assert error["code"] == "schedule_overlap"
    assert [conflict["title"] for conflict in error["conflicts"]] == ["Lecture"]
    assert allowed.status_code == 201


def test_adjacent_and_closed_entries_do_not_overlap(client):
    first = create(client).json()
    adjacent = create(
        client,
        title="Next",
        start_local="2026-11-24T10:30",
        end_local="2026-11-24T11:00",
    )
    client.post(f"/api/v1/schedule-entries/{first['id']}/skip")
    reuse = create(client, title="Replacement")

    assert adjacent.status_code == 201
    assert reuse.status_code == 201


def test_moving_into_another_entry_is_an_overlap(client):
    create(client, title="Lecture")
    other = create(
        client,
        title="Lunch",
        start_local="2026-11-24T12:00",
        end_local="2026-11-24T13:00",
    ).json()

    response = client.patch(
        f"/api/v1/schedule-entries/{other['id']}",
        {"start_local": "2026-11-24T10:00"},
        format="json",
    )

    assert response.status_code == 409


# --------------------------------------------------------------------------
# Lifecycle and actual duration


def test_manual_start_pause_resume_complete_excludes_paused_time(client, clock):
    entry = create(client, title="Cycling").json()
    url = f"/api/v1/schedule-entries/{entry['id']}"

    assert client.post(f"{url}/start").json()["status"] == "in_progress"
    clock["advance"](minutes=20)
    paused = client.post(f"{url}/pause").json()
    assert paused["status"] == "paused"
    assert paused["actual_seconds"] == 20 * 60
    clock["advance"](minutes=15)
    assert client.post(f"{url}/pause").json()["status"] == "paused"  # idempotent
    assert client.post(f"{url}/resume").json()["status"] == "in_progress"
    clock["advance"](minutes=25)
    done = client.post(
        f"{url}/complete", {"outcome": "Hill loop"}, format="json"
    ).json()

    assert done["status"] == "completed"
    assert done["actual_seconds"] == 45 * 60
    assert done["outcome"] == "Hill loop"
    assert done["closed_at"] is not None


def test_timed_entry_actual_minutes_can_be_corrected(client, clock):
    entry = create(client, title="Run").json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    client.post(f"{url}/start")
    clock["advance"](minutes=70)

    done = client.post(f"{url}/complete", {"actual_minutes": 40}, format="json")

    assert done.json()["actual_minutes"] == 40


def test_completing_unstarted_entry_does_not_fabricate_time(client):
    entry = create(client, title="Shopping").json()

    done = client.post(f"/api/v1/schedule-entries/{entry['id']}/complete").json()

    assert done["status"] == "completed"
    assert done["actual_seconds"] is None


def test_recording_actual_duration_or_times_after_the_fact(client, clock):
    minutes = create(client, title="Exercise").json()
    times = create(
        client,
        title="Errand",
        start_local="2026-11-24T05:00",
        end_local="2026-11-24T05:30",
    ).json()

    by_minutes = client.post(
        f"/api/v1/schedule-entries/{minutes['id']}/complete",
        {"actual_minutes": 35},
        format="json",
    ).json()
    by_times = client.post(
        f"/api/v1/schedule-entries/{times['id']}/complete",
        {
            "actual_started_at": "2026-11-24T02:10:00Z",
            "actual_ended_at": "2026-11-24T02:55:00Z",
        },
        format="json",
    ).json()

    assert by_minutes["actual_seconds"] == 35 * 60
    assert by_times["actual_seconds"] == 45 * 60
    bad = create(
        client,
        title="Bad",
        start_local="2026-11-24T18:00",
        end_local="2026-11-24T19:00",
    ).json()
    response = client.post(
        f"/api/v1/schedule-entries/{bad['id']}/complete",
        {"actual_started_at": "2026-11-24T02:10:00Z"},
        format="json",
    )
    assert response.status_code == 400


def test_partial_completion_and_terminal_states(client):
    entry = create(client).json()
    url = f"/api/v1/schedule-entries/{entry['id']}"

    partial = client.post(
        f"{url}/complete", {"partial": True, "outcome": "Half"}, format="json"
    )
    again = client.post(f"{url}/complete", {"partial": True}, format="json")
    full = client.post(f"{url}/complete")

    assert partial.json()["status"] == "partially_completed"
    assert again.status_code == 200  # same target is idempotent
    assert full.status_code == 400


@pytest.mark.parametrize(
    ("setup", "command", "expected"),
    [
        ([], "pause", 400),
        ([], "resume", 400),
        (["start"], "skip", 400),
        (["skip"], "start", 400),
        (["cancel"], "complete", 400),
        (["complete"], "cancel", 400),
        (["start"], "start", 200),
        (["skip"], "skip", 200),
    ],
)
def test_status_transition_rules(client, setup, command, expected):
    entry = create(client).json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    for step in setup:
        assert client.post(f"{url}/{step}").status_code == 200

    assert client.post(f"{url}/{command}").status_code == expected


def test_past_end_time_never_auto_completes(client, clock):
    entry = create(client).json()
    clock["advance"](days=3)

    listed = client.get("/api/v1/schedule-entries?start=2026-11-24").json()

    assert listed[0]["id"] == entry["id"]
    assert listed[0]["status"] == "scheduled"


def test_cancel_running_manual_entry_keeps_audit_but_no_actual(client, clock):
    entry = create(client).json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    client.post(f"{url}/start")
    clock["advance"](minutes=10)

    cancelled = client.post(
        f"{url}/cancel", {"note": "Called away"}, format="json"
    ).json()

    assert cancelled["status"] == "cancelled"
    assert cancelled["actual_ended_at"] is not None
    assert cancelled["actual_seconds"] is None
    assert cancelled["notes"] == "Called away"


# --------------------------------------------------------------------------
# Rescheduling


def test_reschedule_preserves_original_and_links_replacement(client):
    entry = create(client).json()

    response = client.post(
        f"/api/v1/schedule-entries/{entry['id']}/reschedule",
        {"start_local": "2026-11-25T09:00", "end_local": "2026-11-25T10:30"},
        format="json",
    )

    assert response.status_code == 200, response.json()
    original, replacement = response.json()["original"], response.json()["entry"]
    assert original["status"] == "rescheduled"
    assert original["rescheduled_to"] == replacement["id"]
    assert replacement["rescheduled_from"] == entry["id"]
    assert replacement["status"] == "scheduled"
    assert replacement["local_date"] == "2026-11-25"
    assert ScheduleEntry.objects.count() == 2
    hidden = client.get("/api/v1/schedule-entries?start=2026-11-24").json()
    history = client.get("/api/v1/schedule-entries?start=2026-11-24&include=all").json()
    assert hidden == []
    assert [item["status"] for item in history] == ["rescheduled"]


def test_reschedule_is_idempotent_and_allowed_after_skip(client):
    entry = create(client).json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    client.post(f"{url}/skip")
    payload = {"start_local": "2026-11-26T09:00", "end_local": "2026-11-26T10:00"}

    first = client.post(f"{url}/reschedule", payload, format="json").json()
    second = client.post(f"{url}/reschedule", payload, format="json").json()

    assert first["entry"]["id"] == second["entry"]["id"]
    assert ScheduleEntry.objects.count() == 2


def test_running_entry_cannot_be_rescheduled(client):
    entry = create(client).json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    client.post(f"{url}/start")

    response = client.post(
        f"{url}/reschedule",
        {"start_local": "2026-11-26T09:00", "end_local": "2026-11-26T10:00"},
        format="json",
    )

    assert response.status_code == 400


def test_reschedule_into_its_own_slot_is_not_an_overlap(client):
    entry = create(client).json()
    response = client.post(
        f"/api/v1/schedule-entries/{entry['id']}/reschedule",
        {"start_local": "2026-11-24T09:30", "end_local": "2026-11-24T10:30"},
        format="json",
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Focus sessions and linked tasks


def test_focus_entry_uses_server_authoritative_session(client, study, clock):
    entry = create(client, area=str(study.id), tracking="focus").json()
    url = f"/api/v1/schedule-entries/{entry['id']}"

    started = client.post(f"{url}/start").json()
    session = FocusSession.objects.get(pk=started["focus_session"])
    assert session.area == study
    assert session.title == "Study algorithms"
    assert started["focus_session_status"] == "active"

    clock["advance"](minutes=30)
    assert client.post(f"{url}/pause").json()["focus_session_status"] == "paused"
    clock["advance"](minutes=10)
    assert client.post(f"{url}/resume").json()["focus_session_status"] == "active"
    clock["advance"](minutes=20)
    done = client.post(
        f"{url}/complete",
        {"outcome": "Finished DP set", "learning": "Memo"},
        format="json",
    ).json()

    session.refresh_from_db()
    assert session.status == "completed"
    assert session.duration_seconds == 50 * 60
    assert session.outcome == "Finished DP set"
    assert done["actual_seconds"] == 50 * 60
    entry_row = ScheduleEntry.objects.get(pk=entry["id"])
    assert entry_row.actual_duration_seconds is None  # time lives on the session


def test_active_session_reports_its_linked_entry(client, study):
    entry = create(client, area=str(study.id), tracking="focus").json()
    client.post(f"/api/v1/schedule-entries/{entry['id']}/start")

    active = client.get("/api/v1/sessions/active").json()

    assert active["schedule_entry"] == entry["id"]


def test_focus_entry_rejects_manual_actuals(client, study):
    entry = create(client, area=str(study.id), tracking="focus").json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    client.post(f"{url}/start")

    response = client.post(f"{url}/complete", {"actual_minutes": 90}, format="json")

    assert response.status_code == 400
    assert "timer" in response.json()["detail"]


def test_database_forbids_double_counted_actuals(user, study):
    session = FocusSession.objects.create(
        user=user,
        area=study,
        title="Focus",
        is_deep_work=True,
        started_at=timezone.now(),
        timezone_snapshot=user.timezone,
        area_label_snapshot=study.name,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ScheduleEntry.objects.create(
            user=user,
            title="Linked",
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(hours=1),
            timezone_name=user.timezone,
            local_date=date(2026, 11, 24),
            focus_session=session,
            status="in_progress",
            actual_duration_seconds=600,
        )


def test_focus_entry_requires_category_and_single_open_session(client, study):
    no_area = create(client, tracking="focus").json()
    assert (
        client.post(f"/api/v1/schedule-entries/{no_area['id']}/start").status_code
        == 400
    )

    first = create(
        client,
        area=str(study.id),
        tracking="focus",
        start_local="2026-11-24T11:00",
        end_local="2026-11-24T12:00",
    ).json()
    second = create(
        client,
        area=str(study.id),
        tracking="focus",
        start_local="2026-11-24T13:00",
        end_local="2026-11-24T14:00",
    ).json()
    assert (
        client.post(f"/api/v1/schedule-entries/{first['id']}/start").status_code == 200
    )
    blocked = client.post(f"/api/v1/schedule-entries/{second['id']}/start")
    assert blocked.status_code == 400
    assert ScheduleEntry.objects.get(pk=second["id"]).status == "scheduled"


def test_generic_session_endpoints_keep_linked_entry_in_sync(client, study):
    entry = create(client, area=str(study.id), tracking="focus").json()
    started = client.post(f"/api/v1/schedule-entries/{entry['id']}/start").json()
    session_url = f"/api/v1/sessions/{started['focus_session']}"

    client.post(f"{session_url}/pause", {"id": str(uuid.uuid4())}, format="json")
    assert ScheduleEntry.objects.get(pk=entry["id"]).status == "paused"
    client.post(f"{session_url}/resume", {}, format="json")
    assert ScheduleEntry.objects.get(pk=entry["id"]).status == "in_progress"
    client.post(f"{session_url}/finish", {"outcome": "Shipped"}, format="json")

    row = ScheduleEntry.objects.get(pk=entry["id"])
    assert row.status == "completed"
    assert row.outcome == "Shipped"


def test_cancelling_focus_entry_cancels_session(client, study):
    entry = create(client, area=str(study.id), tracking="focus").json()
    url = f"/api/v1/schedule-entries/{entry['id']}"
    client.post(f"{url}/start")

    cancelled = client.post(f"{url}/cancel").json()

    assert cancelled["focus_session_status"] == "cancelled"
    assert cancelled["actual_seconds"] is None


def test_linked_task_can_be_completed_with_entry(client, user, study):
    task = Task.objects.create(user=user, title="Write essay", area=study)
    entry = create(client, task=str(task.id)).json()
    assert entry["task_title"] == "Write essay"

    client.post(
        f"/api/v1/schedule-entries/{entry['id']}/complete",
        {"complete_task": True},
        format="json",
    )

    task.refresh_from_db()
    assert task.status == "done"


def test_completing_entry_leaves_task_open_by_default(client, user):
    task = Task.objects.create(user=user, title="Long project")
    entry = create(client, task=str(task.id)).json()

    client.post(f"/api/v1/schedule-entries/{entry['id']}/complete")

    task.refresh_from_db()
    assert task.status == "todo"


def test_roadmap_node_link(client, user):
    from roadmaps.models import Roadmap, RoadmapNode

    roadmap = Roadmap.objects.create(user=user, title="Algorithms")
    node = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Graphs", node_type="item"
    )

    entry = create(client, roadmap_node=str(node.id)).json()

    assert entry["roadmap_node_title"] == "Graphs"


# --------------------------------------------------------------------------
# Owner isolation


def test_other_users_cannot_see_or_change_entries(client, user):
    entry = create(client).json()
    intruder = get_user_model().objects.create_user("intruder@example.com", "password")
    other = APIClient()
    other.force_authenticate(intruder)
    url = f"/api/v1/schedule-entries/{entry['id']}"

    assert other.get("/api/v1/schedule-entries?start=2026-11-24").json() == []
    assert other.get(url).status_code == 404
    assert other.patch(url, {"title": "Mine"}, format="json").status_code == 404
    for command in ("start", "skip", "cancel", "complete"):
        assert other.post(f"{url}/{command}").status_code == 404
    reschedule = other.post(
        f"{url}/reschedule",
        {"start_local": "2026-11-25T09:00", "end_local": "2026-11-25T10:00"},
        format="json",
    )
    assert reschedule.status_code == 404
    assert ScheduleEntry.objects.get(pk=entry["id"]).status == "scheduled"


def test_cannot_link_another_users_records(client):
    intruder = get_user_model().objects.create_user("i2@example.com", "password")
    area = Area.objects.create(user=intruder, name="Secret", slug="secret")
    task = Task.objects.create(user=intruder, title="Secret task")

    assert create(client, area=str(area.id)).status_code == 400
    assert create(client, task=str(task.id)).status_code == 400


def test_overlap_check_ignores_other_users(client):
    intruder = get_user_model().objects.create_user("i3@example.com", "password")
    other = APIClient()
    other.force_authenticate(intruder)
    create(other, timezone_name=NAIROBI)

    assert create(client).status_code == 201


def test_unauthenticated_requests_are_rejected():
    response = APIClient().get("/api/v1/schedule-entries")
    assert response.status_code in (401, 403)


def test_unsafe_methods_require_csrf(user):
    client = APIClient(enforce_csrf_checks=True)
    client.login(email=user.email, password="password")

    response = create(client)

    assert response.status_code == 403
