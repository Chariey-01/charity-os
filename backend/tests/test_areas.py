import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from planning.models import Area

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user("owner@example.com", "password")


def area_data(user, **overrides):
    data = {
        "user": user,
        "name": "Deep Work",
        "slug": "deep-work",
        "color": "#2563EB",
        "icon": "brain",
        "sort_order": 1,
    }
    data.update(overrides)
    return data


def test_valid_area_creation(user):
    area = Area.objects.create(**area_data(user))

    assert area.user == user
    assert area.icon == "brain"
    assert area.archived_at is None


def test_active_area_names_are_case_insensitively_unique(user):
    Area.objects.create(**area_data(user))

    with pytest.raises(IntegrityError), transaction.atomic():
        Area.objects.create(**area_data(user, name="DEEP WORK", slug="focused"))


def test_archived_area_releases_name_for_reuse(user):
    Area.objects.create(**area_data(user, archived_at=timezone.now()))

    replacement = Area.objects.create(**area_data(user, slug="new-deep-work"))

    assert replacement.archived_at is None


def test_slug_remains_unique_when_area_is_archived(user):
    Area.objects.create(**area_data(user, archived_at=timezone.now()))

    with pytest.raises(IntegrityError), transaction.atomic():
        Area.objects.create(**area_data(user, name="Focused Work"))


def test_uniqueness_rules_are_isolated_per_user(user):
    other_user = get_user_model().objects.create_user("other@example.com", "password")
    Area.objects.create(**area_data(user))

    other = Area.objects.create(**area_data(other_user))

    assert other.user == other_user


@pytest.mark.parametrize("color", ["2563EB", "#12345", "#GGGGGG"])
def test_invalid_color_is_rejected_by_database(user, color):
    with pytest.raises(IntegrityError), transaction.atomic():
        Area.objects.create(**area_data(user, color=color))


def test_negative_sort_order_is_rejected_by_database(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Area.objects.create(**area_data(user, sort_order=-1))


def test_model_validation_rejects_invalid_color(user):
    area = Area(**area_data(user, color="blue"))

    with pytest.raises(ValidationError) as error:
        area.full_clean()

    assert "color" in error.value.message_dict


def test_model_validation_rejects_negative_sort_order(user):
    area = Area(**area_data(user, sort_order=-1))

    with pytest.raises(ValidationError) as error:
        area.full_clean()

    assert "sort_order" in error.value.message_dict
