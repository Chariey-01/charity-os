"""Django admin cannot hard-delete anything (owner decision 4.3)."""

from datetime import date

import pytest
from django.contrib import admin
from django.test import RequestFactory

from challenges.models import Challenge
from planning.models import Area, DailyCapacity

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser("admin@example.com", "password")


@pytest.fixture
def admin_client(client, superuser):
    client.force_login(superuser)
    return client


def test_no_registered_model_can_be_deleted_from_admin(superuser):
    request = RequestFactory().get("/admin/")
    request.user = superuser

    for model, model_admin in admin.site._registry.items():
        if model._meta.app_label in {"auth"}:
            continue  # Django's own groups; they hold no CharityOS records
        assert model_admin.has_delete_permission(request) is False, model
        assert "delete_selected" not in model_admin.get_actions(request), model


def records(owner):
    return {
        "users/user": owner,
        "planning/area": Area.objects.create(user=owner, name="Study", slug="study"),
        "planning/dailycapacity": DailyCapacity.objects.create(
            user=owner, local_date=date(2026, 11, 24), timezone_name="UTC"
        ),
        "challenges/challenge": Challenge.objects.create(
            user=owner,
            name="Road",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 5),
        ),
    }


def test_delete_pages_and_bulk_delete_are_refused(admin_client, django_user_model):
    owner = django_user_model.objects.create_user("owner@example.com", "password")

    for path, record in records(owner).items():
        page = admin_client.get(f"/admin/{path}/{record.pk}/delete/")
        posted = admin_client.post(
            f"/admin/{path}/{record.pk}/delete/", {"post": "yes"}
        )
        bulk = admin_client.post(
            f"/admin/{path}/",
            {
                "action": "delete_selected",
                "_selected_action": [record.pk],
                "post": "yes",
            },
        )

        assert page.status_code == 403, path
        assert posted.status_code == 403, path
        assert bulk.status_code in (200, 302), path
        assert type(record).objects.filter(pk=record.pk).exists(), path


def test_records_stay_editable_in_admin(admin_client, django_user_model):
    owner = django_user_model.objects.create_user("owner@example.com", "password")
    area = Area.objects.create(user=owner, name="Study", slug="study")

    page = admin_client.get(f"/admin/planning/area/{area.pk}/change/")

    assert page.status_code == 200
    assert b"deletelink" not in page.content
