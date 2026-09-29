import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from challenges.models import Challenge
from execution.models import FocusSession
from planning.models import Area, DailyCapacity, DailyPlan, Task
from planning.services import add_plan_item

pytestmark = pytest.mark.django_db


def test_complete_private_alpha_flow_and_isolation():
    User = get_user_model()
    user = User.objects.create_user(
        "alpha@example.com", "password", timezone="Africa/Nairobi"
    )
    stranger = User.objects.create_user("stranger@example.com", "password")
    client = APIClient()
    client.force_authenticate(user)
    today = date.today()
    challenge = Challenge.objects.create(
        user=user,
        name="96 Days",
        start_date=today,
        end_date=today + timedelta(days=95),
        status="active",
        is_primary=True,
    )
    area = Area.objects.create(user=user, name="Engineering", slug="engineering")
    DailyCapacity.objects.create(
        user=user,
        local_date=today,
        timezone_name=user.timezone,
        available_minutes=480,
        deep_work_minutes=240,
    )
    plan = DailyPlan.objects.create(
        user=user, local_date=today, timezone_name=user.timezone, challenge=challenge
    )
    task = Task.objects.create(
        user=user, area=area, title="Ship an outcome", is_deep_work_default=True
    )
    add_plan_item(user=user, plan=plan, task=task, kind="primary", position=0)

    session_id, pause_id = str(uuid.uuid4()), str(uuid.uuid4())
    response = client.post(
        "/api/v1/sessions/start",
        {
            "id": session_id,
            "area": str(area.id),
            "title": task.title,
            "task": str(task.id),
            "is_deep_work": True,
        },
        format="json",
    )
    assert response.status_code == 201
    assert client.get("/api/v1/sessions/active").json()["id"] == session_id
    assert (
        client.post(
            f"/api/v1/sessions/{session_id}/pause",
            {"id": pause_id, "expected_version": 1},
            format="json",
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/sessions/{session_id}/resume",
            {"expected_version": 2},
            format="json",
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/sessions/{session_id}/finish",
            {
                "expected_version": 3,
                "outcome": "Working MVP",
                "learning": "Small verified increments",
            },
            format="json",
        ).status_code
        == 200
    )
    assert FocusSession.objects.get(pk=session_id).status == "completed"

    evidence = client.post(
        "/api/v1/evidence",
        {"kind": "note", "text": "Acceptance evidence", "session": session_id},
        format="json",
    )
    assert evidence.status_code == 201
    accomplishment = client.post(
        "/api/v1/accomplishments",
        {
            "local_date": str(today),
            "timezone_name": user.timezone,
            "title": "Completed acceptance flow",
            "session": session_id,
        },
        format="json",
    )
    assert accomplishment.status_code == 201
    roadmap = client.post(
        "/api/v1/roadmaps",
        {"title": "Engineering", "status": "active", "area": str(area.id)},
        format="json",
    )
    assert roadmap.status_code == 201
    node = client.post(
        "/api/v1/roadmap-nodes",
        {
            "roadmap": roadmap.json()["id"],
            "title": "MVP",
            "node_type": "item",
            "state": "completed",
            "position": 0,
        },
        format="json",
    )
    assert node.status_code == 201
    assert (
        client.get(f"/api/v1/roadmaps/{roadmap.json()['id']}/progress").json()[
            "progress_ratio"
        ]
        == 1
    )

    start = datetime.now(timezone.utc) - timedelta(hours=8)
    assert (
        client.post(
            "/api/v1/sleep-logs",
            {
                "started_at": start.isoformat(),
                "woke_at": (start + timedelta(hours=7)).isoformat(),
                "timezone_name": user.timezone,
                "quality": 4,
            },
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/nutrition",
            {"local_date": str(today), "timezone_name": user.timezone, "rating": 4},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/daily-reflections",
            {
                "local_date": str(today),
                "timezone_name": user.timezone,
                "went_well": "Focus",
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
            format="json",
        ).status_code
        == 201
    )
    metrics = client.get("/api/v1/analytics/metrics").json()
    assert metrics["planned_appearances"] == 1

    client.force_authenticate(stranger)
    assert client.get("/api/v1/tasks").json() == []
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404
