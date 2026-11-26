"""A retried reflection create that races the original gets the same answer.

Review of Phase 0C (26 Nov 2026): four identical daily-reflection creates
sent at once answered one 201 and three generic 409 "conflict" errors.
The contract (S8) is that an identical retry returns the stored record
(200) and different words are a 409 "already_exists" with the existing id;
a retry must not depend on whether it arrives during or after the original.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from api.reflections import ReflectionMixin
from reflections.models import DailyReflection

DAY = {"local_date": "2026-11-24", "timezone_name": "UTC"}


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", "pw-123456")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def lost_race(monkeypatch):
    """The first lookup misses a row another request has just committed."""
    real = ReflectionMixin._existing
    calls = []

    def first_lookup_misses(self, value):
        calls.append(value)
        return None if len(calls) == 1 else real(self, value)

    monkeypatch.setattr(ReflectionMixin, "_existing", first_lookup_misses)
    return calls


@pytest.mark.django_db
def test_an_identical_create_that_lost_the_race_returns_the_record(user, lost_race):
    stored = DailyReflection.objects.create(user=user, went_well="Same words", **DAY)

    response = client_for(user).post(
        "/api/v1/daily-reflections", {**DAY, "went_well": "Same words"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(stored.pk)
    assert DailyReflection.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_different_words_that_lost_the_race_are_already_exists(user, lost_race):
    stored = DailyReflection.objects.create(user=user, went_well="First", **DAY)

    response = client_for(user).post(
        "/api/v1/daily-reflections", {**DAY, "went_well": "Second"}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_exists"
    assert response.json()["error"]["existing_id"] == str(stored.pk)
    stored.refresh_from_db()
    assert stored.went_well == "First"


@pytest.mark.django_db(transaction=True)
def test_concurrent_identical_creates_store_one_and_answer_alike(user):
    def create(_):
        try:
            response = client_for(user).post(
                "/api/v1/daily-reflections",
                {**DAY, "went_well": "Same words"},
                format="json",
            )
            return response.status_code, response.json()["id"]
        finally:
            connection.close()

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(create, range(4)))

    assert sorted(status for status, _ in results) == [200, 200, 200, 201]
    assert len({record_id for _, record_id in results}) == 1
    assert DailyReflection.objects.filter(user=user).count() == 1
