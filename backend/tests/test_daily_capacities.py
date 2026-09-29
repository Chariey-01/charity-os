from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from planning.models import DailyCapacity

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user("owner@example.com", "password")


def capacity_data(user, **overrides):
    data = {
        "user": user,
        "local_date": date(2026, 9, 29),
        "timezone_name": "Africa/Nairobi",
        "available_minutes": 480,
        "deep_work_minutes": 240,
        "fixed_commitments": "Team meeting at 10:00",
    }
    data.update(overrides)
    return data


def test_valid_daily_capacity_creation(user):
    capacity = DailyCapacity.objects.create(**capacity_data(user))

    assert capacity.user == user
    assert capacity.timezone_name == "Africa/Nairobi"
    assert capacity.fixed_commitments == "Team meeting at 10:00"


def test_only_one_capacity_exists_per_user_and_local_date(user):
    DailyCapacity.objects.create(**capacity_data(user))

    with pytest.raises(IntegrityError), transaction.atomic():
        DailyCapacity.objects.create(**capacity_data(user, timezone_name="UTC"))


def test_same_local_date_is_allowed_for_different_users(user):
    other_user = get_user_model().objects.create_user("other@example.com", "password")
    DailyCapacity.objects.create(**capacity_data(user))

    other = DailyCapacity.objects.create(**capacity_data(other_user))

    assert other.user == other_user


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("available_minutes", -1),
        ("available_minutes", 1441),
        ("deep_work_minutes", -1),
        ("deep_work_minutes", 1441),
    ],
)
def test_minutes_outside_daily_bounds_are_rejected_by_database(user, field_name, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        DailyCapacity.objects.create(**capacity_data(user, **{field_name: value}))


def test_deep_work_cannot_exceed_available_capacity_in_database(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        DailyCapacity.objects.create(
            **capacity_data(user, available_minutes=120, deep_work_minutes=121)
        )


def test_zero_capacity_is_valid(user):
    capacity = DailyCapacity.objects.create(
        **capacity_data(user, available_minutes=0, deep_work_minutes=0)
    )

    assert capacity.available_minutes == 0


def test_full_day_capacity_is_valid(user):
    capacity = DailyCapacity.objects.create(
        **capacity_data(user, available_minutes=1440, deep_work_minutes=1440)
    )

    assert capacity.deep_work_minutes == 1440


def test_model_validation_rejects_deep_work_above_available(user):
    capacity = DailyCapacity(
        **capacity_data(user, available_minutes=120, deep_work_minutes=121)
    )

    with pytest.raises(ValidationError) as error:
        capacity.full_clean()

    assert "deep_work_minutes" in error.value.message_dict


def test_model_validation_rejects_unknown_timezone(user):
    capacity = DailyCapacity(**capacity_data(user, timezone_name="Mars/Olympus"))

    with pytest.raises(ValidationError) as error:
        capacity.full_clean()

    assert "timezone_name" in error.value.message_dict
