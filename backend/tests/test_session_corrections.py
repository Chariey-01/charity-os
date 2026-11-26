"""Phase 0B, B2: audited corrections of completed focus sessions (decision 4.5)."""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import scheduling.services as scheduling_services
from execution.models import FocusSession, FocusSessionCorrection, SessionPause
from planning.models import Area, Task
from roadmaps.models import Roadmap, RoadmapNode
from scheduling.models import ScheduleEntry

pytestmark = pytest.mark.django_db
T0 = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)  # 09:00 in Nairobi


@pytest.fixture
def clock(monkeypatch):
    now = [T0]
    monkeypatch.setattr(timezone, "now", lambda: now[0])
    return now


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        "corrections@example.com", "password", timezone="Africa/Nairobi"
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
def work(user):
    return Area.objects.create(user=user, name="Work", slug="work")


def completed(user, area, minutes=60, **extra):
    return FocusSession.objects.create(
        user=user,
        area=area,
        title="Read",
        is_deep_work=True,
        started_at=T0,
        ended_at=T0 + timedelta(minutes=minutes),
        duration_seconds=minutes * 60,
        status="completed",
        timezone_snapshot="Africa/Nairobi",
        area_label_snapshot=area.name,
        **extra,
    )


def correct(client, session, **body):
    body.setdefault("reason", "Fixing my log")
    body.setdefault("expected_version", session.version)
    return client.post(
        f"/api/v1/sessions/{session.id}/corrections", body, format="json"
    )


def test_time_correction_is_recorded_before_and_after(client, user, study, clock):
    clock[0] = T0 + timedelta(hours=3)
    session = completed(user, study)

    response = correct(
        client, session, ended_at=(T0 + timedelta(minutes=45)).isoformat()
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert (session.duration_seconds, session.version) == (45 * 60, 2)
    record = FocusSessionCorrection.objects.get(session=session)
    assert record.reason == "Fixing my log"
    assert record.before["duration_seconds"] == 3600
    assert record.after["duration_seconds"] == 2700


def test_corrections_need_the_current_version(client, user, study, clock):
    clock[0] = T0 + timedelta(hours=3)
    session = completed(user, study)
    end = (T0 + timedelta(minutes=45)).isoformat()

    missing = client.post(
        f"/api/v1/sessions/{session.id}/corrections",
        {"reason": "x", "ended_at": end},
        format="json",
    )
    stale = correct(client, session, ended_at=end, expected_version=5)

    assert missing.status_code == 400
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert not FocusSessionCorrection.objects.exists()


@pytest.mark.parametrize(
    "start_offset, end_offset, field",
    [
        (0, 60 * 3 + 6, "ended_at"),  # ends 6 minutes in the future
        (-60 * 22, 60 * 3, "ended_at"),  # 25 hours long
    ],
)
def test_impossible_times_are_refused(
    client, user, study, clock, start_offset, end_offset, field
):
    clock[0] = T0 + timedelta(hours=3)
    session = completed(user, study)

    response = correct(
        client,
        session,
        started_at=(T0 + timedelta(minutes=start_offset)).isoformat(),
        ended_at=(T0 + timedelta(minutes=end_offset)).isoformat(),
    )

    assert response.status_code == 400
    assert field in response.json()["error"]["fields"]
    session.refresh_from_db()
    assert session.duration_seconds == 3600


def test_an_end_within_five_minutes_of_now_is_accepted(client, user, study, clock):
    clock[0] = T0 + timedelta(hours=3)
    session = completed(user, study)

    response = correct(
        client, session, ended_at=(clock[0] + timedelta(minutes=4)).isoformat()
    )

    assert response.status_code == 200


def test_pauses_outside_the_corrected_window_no_longer_count(
    client, user, study, clock
):
    clock[0] = T0 + timedelta(hours=3)
    session = completed(user, study, minutes=60)
    SessionPause.objects.create(
        user=user,
        session=session,
        started_at=T0 + timedelta(minutes=10),
        ended_at=T0 + timedelta(minutes=20),
    )
    FocusSession.objects.filter(pk=session.pk).update(duration_seconds=50 * 60)
    session.refresh_from_db()

    # Start 15 minutes in: only the last 5 minutes of the pause fall inside.
    response = correct(
        client, session, started_at=(T0 + timedelta(minutes=15)).isoformat()
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.duration_seconds == (45 - 5) * 60


def test_a_correction_must_change_something_and_give_a_reason(
    client, user, study, clock
):
    clock[0] = T0 + timedelta(hours=3)
    session = completed(user, study)

    unchanged = correct(client, session, ended_at=session.ended_at.isoformat())
    no_reason = correct(client, session, reason=" ", is_deep_work=False)

    assert unchanged.status_code == no_reason.status_code == 400
    assert not FocusSessionCorrection.objects.exists()


def test_open_sessions_cannot_be_corrected(client, user, study):
    session = FocusSession.objects.create(
        user=user,
        area=study,
        title="Live",
        is_deep_work=True,
        started_at=T0,
        timezone_snapshot="UTC",
        area_label_snapshot="Study",
    )

    assert correct(client, session, is_deep_work=False).status_code == 400


def test_attribution_correction_updates_snapshots_and_the_audit(
    client, user, study, work, clock
):
    clock[0] = T0 + timedelta(hours=3)
    roadmap = Roadmap.objects.create(user=user, title="Python")
    section = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Basics", node_type="section"
    )
    node = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, parent=section, title="Loops", node_type="item"
    )
    task = Task.objects.create(user=user, title="Practise", task_type="practice")
    session = completed(user, study)

    response = correct(
        client,
        session,
        area=str(work.id),
        task=str(task.id),
        roadmap_item=str(node.id),
        is_deep_work=False,
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert (session.area_id, session.area_label_snapshot) == (work.id, "Work")
    assert (session.task_id, session.task_type_snapshot) == (task.id, "practice")
    assert [step["title"] for step in session.roadmap_ancestry_snapshot] == [
        "Basics",
        "Loops",
    ]
    assert session.is_deep_work is False
    record = FocusSessionCorrection.objects.get(session=session)
    assert (record.before["area"], record.after["area"]) == (
        str(study.id),
        str(work.id),
    )
    assert record.before["task"] is None and record.after["task"] == str(task.id)


def test_attribution_must_be_the_users_own_and_active(
    client, user, study, work, clock, django_user_model
):
    clock[0] = T0 + timedelta(hours=3)
    other = django_user_model.objects.create_user("other@example.com", "password")
    theirs = Area.objects.create(user=other, name="Theirs", slug="theirs")
    their_task = Task.objects.create(user=other, title="Theirs")
    Area.objects.filter(pk=work.pk).update(archived_at=T0)
    session = completed(user, study)

    for body in (
        {"area": str(theirs.id)},
        {"task": str(their_task.id)},
        {"area": str(work.id)},
        {"area": None},
        {"area": "not-a-uuid"},
    ):
        response = correct(client, session, **body)
        assert response.status_code == 400, body

    session.refresh_from_db()
    assert (session.area_id, session.version) == (study.id, 1)


def linked_session(client, area, clock):
    entry = client.post(
        "/api/v1/schedule-entries",
        {
            "title": "Read",
            "start_local": "2026-11-24T09:00",
            "end_local": "2026-11-24T10:00",
            "area": str(area.id),
            "tracking": "focus",
        },
        format="json",
    ).json()
    started = client.post(f"/api/v1/schedule-entries/{entry['id']}/start").json()
    session = FocusSession.objects.get(pk=started["focus_session"])
    clock[0] = T0 + timedelta(minutes=60)
    client.post(f"/api/v1/sessions/{session.id}/finish", {"expected_version": 1})
    clock[0] = T0 + timedelta(hours=3)
    session.refresh_from_db()
    return session, ScheduleEntry.objects.get(pk=entry["id"])


def test_correcting_a_linked_session_corrects_its_entry_and_insights_once(
    client, user, study, work, clock
):
    session, entry = linked_session(client, study, clock)
    assert entry.status == "completed"
    before = client.get("/api/v1/insights?period=7d").json()

    response = correct(
        client,
        session,
        area=str(work.id),
        ended_at=(T0 + timedelta(minutes=40)).isoformat(),
    )

    assert response.status_code == 200
    entry.refresh_from_db()
    assert (entry.area_id, entry.area_label_snapshot) == (work.id, "Work")
    assert entry.version > 1
    after = client.get("/api/v1/insights?period=7d").json()
    assert before["totals"]["tracked_minutes"] == 60
    assert after["totals"]["tracked_minutes"] == 40
    assert after["totals"]["focus_minutes"] == 40
    minutes = {row["label"]: row["actual_minutes"] for row in after["category_time"]}
    assert minutes.get("Work") == 40
    assert not minutes.get("Study")


def test_a_failed_entry_update_rolls_the_whole_correction_back(
    client, user, study, work, clock, monkeypatch
):
    session, entry = linked_session(client, study, clock)

    def broken(**kwargs):
        raise RuntimeError("entry update failed")

    monkeypatch.setattr(scheduling_services, "sync_entry_attribution", broken)
    client.raise_request_exception = False

    response = correct(client, session, area=str(work.id))

    assert response.status_code == 500
    session.refresh_from_db()
    entry.refresh_from_db()
    assert (session.area_id, session.version) == (study.id, 2)
    assert entry.area_id == study.id
    assert not FocusSessionCorrection.objects.exists()
