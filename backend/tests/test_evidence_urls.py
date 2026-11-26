"""Phase 0C, S10: evidence URL rules hold on create and on every update."""

import pytest
from rest_framework.test import APIClient

from planning.models import Task
from records.models import Evidence

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("evidence@example.com", "password")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def task(user):
    return Task.objects.create(user=user, title="Ship")


def create(client, task, **body):
    return client.post(
        "/api/v1/evidence", {"task": str(task.id), **body}, format="json"
    )


@pytest.mark.parametrize(
    "body, field",
    [
        ({"kind": "url", "url": "http://example.com"}, "url"),
        ({"kind": "url", "url": "ftp://example.com/file"}, "url"),
        ({"kind": "url", "url": "javascript:alert(1)"}, "url"),
        ({"kind": "url", "url": "not a url"}, "url"),
        ({"kind": "url", "url": ""}, "url"),
        ({"kind": "github", "url": "https://gitlab.com/me/repo"}, "url"),
        ({"kind": "note", "text": "   "}, "text"),
    ],
)
def test_invalid_evidence_is_refused_on_create(client, task, body, field):
    response = create(client, task, **body)

    assert response.status_code == 400
    assert field in response.json()
    assert not Evidence.objects.exists()


def test_audit_probe_an_update_cannot_downgrade_to_http(client, task):
    """2026-11-24 audit: PATCH url to http:// answered 200."""
    evidence = create(client, task, kind="url", url="https://ok.example").json()

    response = client.patch(
        f"/api/v1/evidence/{evidence['id']}",
        {"url": "http://insecure.example"},
        format="json",
    )

    assert response.status_code == 400
    assert "url" in response.json()
    assert Evidence.objects.get().url == "https://ok.example"


@pytest.mark.parametrize(
    "start, change, field",
    [
        (
            {"kind": "github", "url": "https://github.com/me/repo"},
            {"url": "https://example.com"},
            "url",
        ),
        ({"kind": "note", "text": "Done"}, {"kind": "url"}, "url"),
        ({"kind": "note", "text": "Done"}, {"text": ""}, "text"),
        ({"kind": "url", "url": "https://ok.example"}, {"kind": "note"}, "text"),
    ],
)
def test_updates_are_checked_against_the_merged_record(
    client, task, start, change, field
):
    evidence = create(client, task, **start).json()

    response = client.patch(f"/api/v1/evidence/{evidence['id']}", change, format="json")

    assert response.status_code == 400, response.content
    assert field in response.json()


def test_valid_updates_still_work(client, task):
    evidence = create(client, task, kind="url", url="https://a.example").json()

    response = client.patch(
        f"/api/v1/evidence/{evidence['id']}",
        {"url": "https://b.example/path?q=1"},
        format="json",
    )

    assert response.status_code == 200
    assert Evidence.objects.get().url == "https://b.example/path?q=1"


def test_another_users_evidence_cannot_be_changed(client, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "password")
    theirs = Evidence.objects.create(
        user=other,
        kind="url",
        url="https://x.example",
        task=Task.objects.create(user=other, title="T"),
    )

    response = client.patch(
        f"/api/v1/evidence/{theirs.id}", {"url": "https://y.example"}, format="json"
    )

    assert response.status_code == 404
