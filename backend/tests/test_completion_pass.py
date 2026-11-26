from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from api.views import challenge_summary
from challenges.models import Challenge
from planning.models import Area, DailyPlan, Task
from planning.services import add_plan_item

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        "completion@example.com", "password", timezone="Africa/Nairobi"
    )


def challenge(user, start, end, **extra):
    return Challenge.objects.create(
        user=user,
        name=extra.pop("name", f"Challenge {start}"),
        start_date=start,
        end_date=end,
        status="active",
        **extra,
    )


def test_dynamic_challenge_days_for_96_and_365_days(user):
    sprint = challenge(user, date(2026, 9, 27), date(2026, 12, 31))
    year = challenge(user, date(2027, 1, 1), date(2027, 12, 31), name="2027")

    sprint_summary = challenge_summary(sprint, date(2026, 9, 30))
    year_summary = challenge_summary(year, date(2027, 7, 2))

    assert sprint_summary["total_days"] == 96
    assert sprint_summary["current_day"] == 4
    assert year_summary["total_days"] == 365
    assert year_summary["current_day"] == 183


def test_future_and_completed_challenge_phases(user):
    future = challenge(user, date(2027, 1, 1), date(2027, 3, 31))
    completed = challenge(
        user,
        date(2025, 1, 1),
        date(2025, 12, 31),
        name="2025",
    )

    assert challenge_summary(future, date(2026, 12, 1))["phase"] == "upcoming"
    result = challenge_summary(completed, date(2026, 1, 1))
    assert result["phase"] == "completed"
    assert result["progress_percent"] == 100


def test_primary_challenge_action_preserves_historical_challenge(user):
    old = challenge(
        user,
        date(2026, 1, 1),
        date(2026, 12, 31),
        name="2026",
        is_primary=True,
    )
    new = challenge(user, date(2027, 1, 1), date(2027, 12, 31), name="2027")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(f"/api/v1/challenges/{new.id}/set-primary")

    assert response.status_code == 200
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.is_primary is False
    assert new.is_primary is True
    assert Challenge.objects.filter(user=user).count() == 2


def test_fourth_primary_outcome_is_rejected(user):
    plan = DailyPlan.objects.create(
        user=user, local_date=date.today(), timezone_name=user.timezone
    )
    for position in range(3):
        task = Task.objects.create(user=user, title=f"Primary {position}")
        add_plan_item(
            user=user, plan=plan, task=task, kind="primary", position=position
        )
    fourth = Task.objects.create(user=user, title="Fourth")

    with pytest.raises(ValidationError, match="at most three"):
        add_plan_item(user=user, plan=plan, task=fourth, kind="primary", position=3)


def test_invalid_focus_area_returns_structured_400(user):
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/v1/sessions/start",
        {"id": "not-a-uuid", "title": "Focus", "area": "", "is_deep_work": True},
        format="json",
    )

    assert response.status_code == 400
    assert response.accepted_media_type == "application/json"


def test_analytics_zero_fills_requested_date_range(user):
    Area.objects.create(user=user, name="Engineering", slug="engineering")
    client = APIClient()
    client.force_authenticate(user)
    start = date.today() - timedelta(days=6)

    data = client.get(
        f"/api/v1/analytics/metrics?start={start}&end={date.today()}"
    ).json()

    assert len(data["focus_trend"]) == 7
    assert all(point["minutes"] == 0 for point in data["focus_trend"])
