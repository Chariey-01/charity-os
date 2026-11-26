"""The six suggested workstreams (planning.categories.WORKSTREAMS).

Opt-in, never forced: added from Profile or by bootstrap_charityos
--with-workstreams. Existing names, active or archived, are left alone.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from planning.categories import WORKSTREAMS, ensure_workstreams
from planning.models import Area

NAMES = [name for name, _ in WORKSTREAMS]


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("owner@example.com", "pw-123456-abc")


@pytest.mark.django_db
def test_adds_the_six_once(user):
    first = ensure_workstreams(user)
    second = ensure_workstreams(user)

    assert [area.name for area in first] == NAMES
    assert second == []
    assert Area.objects.filter(user=user).count() == 6


@pytest.mark.django_db
def test_never_touches_existing_names(user):
    mine = Area.objects.create(
        user=user, name="client work and income", slug="cw", color="#123456"
    )
    gone = Area.objects.create(
        user=user, name="Personal Administration", slug="pa", archived_at=timezone.now()
    )

    created = ensure_workstreams(user)

    assert len(created) == 4
    mine.refresh_from_db()
    gone.refresh_from_db()
    assert (mine.name, mine.color) == ("client work and income", "#123456")
    assert gone.archived_at is not None
    assert not Area.objects.filter(
        user=user, name="Personal Administration", archived_at__isnull=True
    ).exists()


@pytest.mark.django_db
def test_the_endpoint_and_another_users_data(user, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "pw-123456-abc")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post("/api/v1/areas/ensure-workstreams")

    assert response.status_code == 200
    assert response.json()["created"] == 6
    assert {row["name"] for row in response.json()["areas"]} >= set(NAMES)
    assert not Area.objects.filter(user=other).exists()


@pytest.mark.django_db
def test_bootstrap_can_add_them(monkeypatch):
    monkeypatch.setenv("BOOT_PW", "pw-123456-abc")
    call_command(
        "bootstrap_charityos",
        "--email",
        "new@example.com",
        "--password-env",
        "BOOT_PW",
        "--with-workstreams",
        stdout=StringIO(),
    )

    names = set(
        Area.objects.filter(user__email="new@example.com").values_list(
            "name", flat=True
        )
    )
    assert names >= set(NAMES)
