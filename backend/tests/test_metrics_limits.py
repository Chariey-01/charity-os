"""Phase 0C, S9: /analytics/metrics has a bounded, validated range and bounded work."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from execution.models import FocusSession
from planning.models import Area

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        "metrics@example.com", "password", timezone="UTC"
    )


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def metrics(client, query):
    return client.get(f"/api/v1/analytics/metrics{query}")


def test_audit_probe_an_unbounded_range_is_refused(client):
    """2026-11-24 audit: start=1900-01-01 answered 200 with 8.4 MB in 1.29 s."""
    response = metrics(client, "?start=1900-01-01")

    assert response.status_code == 400
    assert "start" in response.json()


@pytest.mark.parametrize(
    "query, field",
    [
        ("?start=2025-11-23&end=2026-11-24", "start"),  # 367 days
        ("?start=2026-11-24&end=2026-11-01", "end"),  # end before start
        ("?start=yesterday", "start"),
        ("?end=2026-13-01", "end"),
        ("?period=decade", "period"),
    ],
)
def test_invalid_ranges_are_field_errors(client, query, field):
    response = metrics(client, query)

    assert response.status_code == 400
    assert field in response.json()


@pytest.mark.parametrize(
    "query, days",
    [
        ("?start=2025-11-24&end=2026-11-24", 366),  # the maximum
        ("?start=2026-11-24&end=2026-11-24", 1),
        ("?period=7d", 7),
        ("?period=90d", 90),
        ("?period=year", 328),
        ("", 30),
    ],
)
def test_valid_ranges_are_answered_day_by_day(client, query, days):
    response = metrics(client, query)

    assert response.status_code == 200
    assert len(response.json()["focus_trend"]) == days


def session(user, area, started_at, minutes=30):
    return FocusSession.objects.create(
        user=user,
        area=area,
        title="Focus",
        is_deep_work=True,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=minutes),
        duration_seconds=minutes * 60,
        status="completed",
        timezone_snapshot="UTC",
        area_label_snapshot=area.name,
    )


def test_trends_count_only_the_window_and_totals_stay_all_time(client, user):
    area = Area.objects.create(user=user, name="Study", slug="study")
    session(user, area, NOW - timedelta(days=1))
    session(user, area, NOW - timedelta(days=400))  # outside a 7-day window

    body = metrics(client, "?period=7d").json()

    assert sum(day["minutes"] for day in body["focus_trend"]) == 30
    assert body["area_distribution"] == [{"area": "Study", "minutes": 30}]
    assert body["total_focused_minutes"] == 60  # all-time, aggregated in SQL


def test_history_outside_the_window_is_not_loaded(
    client, user, django_assert_max_num_queries
):
    """The old view loaded every session ever recorded into Python, then
    filtered by date. Count the session rows it actually loads."""
    from django.db.models.signals import post_init

    area = Area.objects.create(user=user, name="Study", slug="study")
    session(user, area, NOW - timedelta(days=1))
    for day in range(2, 700):
        session(user, area, NOW - timedelta(days=day, hours=1), minutes=5)
    loaded = []

    def count(sender, instance, **kwargs):
        loaded.append(instance.pk)

    post_init.connect(count, sender=FocusSession)
    try:
        with django_assert_max_num_queries(20):
            response = metrics(client, "?period=7d")
    finally:
        post_init.disconnect(count, sender=FocusSession)

    assert response.status_code == 200
    assert response.json()["total_focused_minutes"] == 30 + 698 * 5
    assert len(loaded) <= 7  # only the window's sessions, not 699


def test_every_period_the_insights_screen_sends_is_accepted(client):
    """InsightsScreen calls /analytics/metrics for roadmap progress with its own
    period, mapping "all" to "year"."""
    from scheduling.insights import PERIODS

    for period in PERIODS:
        sent = "year" if period == "all" else period
        response = metrics(client, f"?period={sent}")
        assert response.status_code == 200, period


@pytest.mark.parametrize(
    "query, field",
    [
        ("?period=7d&start=2026-01-01", "start"),
        ("?period=30d&start=2026-11-01", "start"),
        ("?period=decade&start=2026-11-01", "start"),
        ("?period=year&end=2026-12-31", "end"),
    ],
)
def test_a_period_with_its_own_dates_is_refused(client, query, field):
    """Review of Phase 0C: the dates were silently ignored (or the period was)."""
    response = metrics(client, query)

    assert response.status_code == 400
    assert field in response.json()
