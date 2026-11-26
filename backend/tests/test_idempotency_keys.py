"""Retried creates are safe with an Idempotency-Key (Phase 0C review, B-item).

The 0B review (Medium) and the 0C report recorded that tasks, evidence,
accomplishments and meal logs are created twice when a client resends a
create whose answer it never saw. The 0C review reproduced it: three
identical task creates sent at once with the same Idempotency-Key header
stored three tasks.

Contract (api/idempotency.py):
* same user, same key, same endpoint and body -> the first successful
  response is replayed, with ``Idempotent-Replayed: true``; nothing new;
* same key, different body or endpoint -> 422 ``idempotency_key_reused``;
* failed creates store nothing, so the same key can be retried;
* keys are per user and expire after 24 hours;
* no key -> unchanged behaviour: separate actions create separate records.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from api.idempotency import TTL
from api.models import IdempotencyKey
from planning.models import Task
from records.models import Accomplishment, Evidence

PASSWORD = "pw-123456-abc"


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", PASSWORD)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def create_task(client, title="Buy milk", key=None, **extra):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
    return client.post(
        "/api/v1/tasks", {"title": title, **extra}, format="json", **headers
    )


@pytest.mark.django_db
def test_a_retry_with_the_same_key_replays_the_first_answer(user):
    client = client_for(user)

    first = create_task(client, key="action-1")
    retry = create_task(client, key="action-1")

    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json()
    assert retry["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first
    assert Task.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_separate_actions_still_create_separate_records(user):
    client = client_for(user)

    without_keys = [create_task(client).status_code for _ in range(2)]
    with_new_keys = [create_task(client, key=f"a-{n}").status_code for n in range(2)]

    assert without_keys == with_new_keys == [201, 201]
    assert Task.objects.filter(user=user, title="Buy milk").count() == 4


@pytest.mark.django_db
def test_reusing_a_key_for_a_different_request_is_refused(user):
    client = client_for(user)
    create_task(client, "Buy milk", key="action-1")

    other_body = create_task(client, "Buy bread", key="action-1")
    other_endpoint = client.post(
        "/api/v1/accomplishments",
        {"title": "Shipped", "local_date": "2026-11-24", "timezone_name": "UTC"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="action-1",
    )

    for response in (other_body, other_endpoint):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "idempotency_key_reused"
    assert list(Task.objects.filter(user=user).values_list("title", flat=True)) == [
        "Buy milk"
    ]
    assert not Accomplishment.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_a_failed_create_stores_nothing_and_can_be_retried(user):
    client = client_for(user)

    failed = create_task(client, title="", key="action-1")
    fixed = create_task(client, title="Buy milk", key="action-1")

    assert failed.status_code == 400
    assert fixed.status_code == 201
    assert Task.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_keys_belong_to_one_user(user, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", PASSWORD)

    mine = create_task(client_for(user), key="shared-key")
    theirs = create_task(client_for(other), key="shared-key")

    assert mine.status_code == theirs.status_code == 201
    assert "Idempotent-Replayed" not in theirs
    assert mine.json()["id"] != theirs.json()["id"]


@pytest.mark.django_db
def test_a_key_expires_after_24_hours(user):
    client = client_for(user)
    create_task(client, key="action-1")
    IdempotencyKey.objects.update(
        created_at=timezone.now() - TTL - timedelta(seconds=1)
    )

    later = create_task(client, key="action-1")

    assert later.status_code == 201
    assert "Idempotent-Replayed" not in later
    assert Task.objects.filter(user=user).count() == 2
    assert IdempotencyKey.objects.count() == 1  # the expired key was purged


@pytest.mark.django_db
def test_a_key_is_still_honoured_just_before_it_expires(user):
    client = client_for(user)
    create_task(client, key="action-1")
    IdempotencyKey.objects.update(
        created_at=timezone.now() - TTL + timedelta(minutes=1)
    )

    retry = create_task(client, key="action-1")

    assert retry["Idempotent-Replayed"] == "true"
    assert Task.objects.filter(user=user).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["", " ", "x" * 256, "naïve", "tab\there"])
def test_malformed_keys_are_refused_before_anything_is_created(user, key):
    response = create_task(client_for(user), key=key)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"
    assert not Task.objects.exists()


@pytest.mark.django_db
def test_evidence_and_accomplishments_are_protected_too(user):
    client = client_for(user)

    def twice(path, body):
        return [
            client.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY=path)
            for _ in range(2)
        ]

    made = twice(
        "/api/v1/accomplishments",
        {"title": "Shipped", "local_date": "2026-11-24", "timezone_name": "UTC"},
    )
    noted = twice(
        "/api/v1/evidence",
        {"kind": "note", "text": "Notes", "accomplishment": made[0].json()["id"]},
    )

    assert [r.status_code for r in made + noted] == [201] * 4
    assert [r.get("Idempotent-Replayed") for r in made + noted] == [
        None,
        "true",
        None,
        "true",
    ]
    assert Evidence.objects.filter(user=user).count() == 1
    assert Accomplishment.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_an_erased_user_s_keys_go_with_the_account(user):
    from io import StringIO

    from django.core.management import call_command

    create_task(client_for(user), key="action-1")
    call_command("erase_user", user.email, "--confirm", user.email, stdout=StringIO())

    assert not IdempotencyKey.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_retries_with_one_key_create_once(user):
    def send(_):
        try:
            response = create_task(client_for(user), key="action-1")
            return response.status_code, response.json()["id"]
        finally:
            connection.close()

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(send, range(4)))

    assert [status for status, _ in results] == [201] * 4
    assert len({task_id for _, task_id in results}) == 1
    assert Task.objects.filter(user=user).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_separate_actions_all_create(user):
    def send(n):
        try:
            return create_task(client_for(user), key=f"action-{n}").status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(4) as pool:
        statuses = list(pool.map(send, range(4)))

    assert statuses == [201] * 4
    assert Task.objects.filter(user=user).count() == 4
