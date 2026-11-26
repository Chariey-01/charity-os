"""Phase 0C, S8: reflections are never silently overwritten; edits keep history."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

KINDS = {
    "daily": {
        "path": "daily-reflections",
        "key": {"local_date": "2026-11-24"},
        "text": ("went_well", "learned", "improve"),
        "fixed": "local_date",
    },
    "weekly": {
        "path": "weekly-reviews",
        "key": {"week_start_date": "2026-11-23", "week_end_date": "2026-11-29"},
        "text": ("wins", "lessons", "next_week"),
        "fixed": "week_start_date",
    },
}


@pytest.fixture(params=KINDS)
def kind(request):
    return KINDS[request.param]


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("reflect@example.com", "password")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def body(kind, words):
    return {**kind["key"], "timezone_name": "UTC", **dict.fromkeys(kind["text"], words)}


def create(client, kind, words="first"):
    return client.post(f"/api/v1/{kind['path']}", body(kind, words), format="json")


def edit(client, kind, record_id, **changes):
    return client.patch(f"/api/v1/{kind['path']}/{record_id}", changes, format="json")


def revisions(client, kind, record_id):
    return client.get(f"/api/v1/{kind['path']}/{record_id}/revisions").json()


def test_a_retried_create_returns_the_same_record(client, kind):
    first = create(client, kind)
    retried = create(client, kind)

    assert (first.status_code, retried.status_code) == (201, 200)
    assert retried.json()["id"] == first.json()["id"]
    assert first.json()["version"] == 1


def test_a_different_second_create_is_a_conflict_not_an_overwrite(client, kind):
    first = create(client, kind, "kept").json()

    clash = create(client, kind, "replacement")

    assert clash.status_code == 409
    error = clash.json()["error"]
    assert error["code"] == "already_exists"
    assert error["existing_id"] == first["id"]
    stored = client.get(f"/api/v1/{kind['path']}/{first['id']}").json()
    assert stored[kind["text"][0]] == "kept"


def test_edits_need_the_current_version_and_keep_the_previous_words(client, kind):
    record = create(client, kind, "first draft").json()
    field = kind["text"][0]

    missing = edit(client, kind, record["id"], **{field: "second"})
    stale = edit(client, kind, record["id"], **{field: "second"}, expected_version=7)
    saved = edit(client, kind, record["id"], **{field: "second"}, expected_version=1)
    again = edit(client, kind, record["id"], **{field: "third"}, expected_version=2)

    assert missing.status_code == 400
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert (saved.status_code, saved.json()["version"]) == (200, 2)
    assert (again.status_code, again.json()[field]) == (200, "third")
    history = revisions(client, kind, record["id"])
    assert [row["version"] for row in history] == [2, 1]
    assert [row["content"][field] for row in history] == ["second", "first draft"]


def test_an_edit_that_changes_nothing_keeps_no_revision(client, kind):
    record = create(client, kind, "same").json()

    response = edit(
        client, kind, record["id"], **{kind["text"][0]: "same"}, expected_version=1
    )

    assert (response.status_code, response.json()["version"]) == (200, 1)
    assert revisions(client, kind, record["id"]) == []


def test_identity_fields_cannot_be_edited(client, kind):
    record = create(client, kind).json()

    for change in (
        {kind["fixed"]: "2026-01-05"},
        {"timezone_name": "Africa/Nairobi"},
        {"version": 9},
    ):
        response = edit(client, kind, record["id"], **change, expected_version=1)
        assert response.status_code == 400, change


def test_archived_reflections_are_restored_before_editing(client, kind):
    record = create(client, kind).json()
    client.post(f"/api/v1/{kind['path']}/{record['id']}/archive")

    response = edit(
        client, kind, record["id"], **{kind["text"][0]: "x"}, expected_version=1
    )

    assert response.status_code == 400


def test_another_users_reflection_and_history_are_hidden(
    client, kind, django_user_model
):
    record = create(client, kind).json()
    other = django_user_model.objects.create_user("other@example.com", "password")
    api = APIClient()
    api.force_authenticate(other)

    assert (
        api.get(f"/api/v1/{kind['path']}/{record['id']}/revisions").status_code == 404
    )
    assert edit(api, kind, record["id"], expected_version=1).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_two_devices_editing_the_same_version_cannot_both_win(user, monkeypatch):
    import reflections.services as reflection_services

    kind = KINDS["daily"]
    api = APIClient()
    api.force_authenticate(user)
    record = create(api, kind).json()
    real = reflection_services.parse_version

    def slow(value):
        time.sleep(0.4)  # both devices have read the row before either writes
        return real(value)

    monkeypatch.setattr(reflection_services, "parse_version", slow)

    def write(words):
        try:
            client = APIClient()
            client.force_authenticate(user)
            return edit(
                client, kind, record["id"], went_well=words, expected_version=1
            ).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(write, ["phone", "laptop"]))

    assert results == [200, 409]
    assert len(revisions(api, kind, record["id"])) == 1
