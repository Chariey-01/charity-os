from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from challenges.models import Challenge

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user("owner@example.com", "password")


def challenge_data(user, **overrides):
    data = {
        "user": user,
        "name": "Road to 2027",
        "description": "A 96-day challenge",
        "start_date": date(2026, 9, 27),
        "end_date": date(2026, 12, 31),
        "status": Challenge.Status.ACTIVE,
    }
    data.update(overrides)
    return data


def test_valid_challenge_creation(user):
    challenge = Challenge.objects.create(**challenge_data(user, is_primary=True))

    assert challenge.user == user
    assert challenge.is_primary is True
    assert challenge.description == "A 96-day challenge"


def test_end_date_cannot_precede_start_date(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Challenge.objects.create(
            **challenge_data(
                user,
                start_date=date(2026, 12, 31),
                end_date=date(2026, 9, 27),
            )
        )


def test_only_one_non_archived_primary_challenge_per_user(user):
    Challenge.objects.create(**challenge_data(user, is_primary=True))

    with pytest.raises(IntegrityError), transaction.atomic():
        Challenge.objects.create(
            **challenge_data(user, name="Another challenge", is_primary=True)
        )


def test_archived_challenge_cannot_be_primary(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Challenge.objects.create(
            **challenge_data(user, is_primary=True, archived_at=timezone.now())
        )


def test_uniqueness_rules_are_isolated_per_user(user):
    other_user = get_user_model().objects.create_user("other@example.com", "password")
    Challenge.objects.create(**challenge_data(user, is_primary=True))

    other = Challenge.objects.create(**challenge_data(other_user, is_primary=True))

    assert other.user == other_user


def test_active_challenge_names_are_case_insensitively_unique(user):
    Challenge.objects.create(**challenge_data(user))

    with pytest.raises(IntegrityError), transaction.atomic():
        Challenge.objects.create(**challenge_data(user, name="ROAD TO 2027"))


def test_invalid_status_is_rejected_by_database(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Challenge.objects.create(**challenge_data(user, status="unknown"))


def test_model_validation_rejects_invalid_dates(user):
    challenge = Challenge(
        **challenge_data(
            user,
            start_date=date(2026, 12, 31),
            end_date=date(2026, 9, 27),
        )
    )

    with pytest.raises(ValidationError) as error:
        challenge.full_clean()

    assert "end_date" in error.value.message_dict


def test_model_validation_rejects_archived_primary(user):
    challenge = Challenge(
        **challenge_data(user, is_primary=True, archived_at=timezone.now())
    )

    with pytest.raises(ValidationError) as error:
        challenge.full_clean()

    assert "is_primary" in error.value.message_dict
