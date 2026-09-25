import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def test_user_creation_hashes_password_and_applies_defaults():
    user = get_user_model().objects.create_user(
        " Person@Example.COM ", "secret-password"
    )
    assert user.email == "person@example.com"
    assert user.check_password("secret-password")
    assert user.timezone == "UTC"
    assert user.week_starts_on == 1


def test_email_is_unique_case_insensitively():
    users = get_user_model().objects
    users.create_user("person@example.com", "secret-password")
    with pytest.raises(IntegrityError), transaction.atomic():
        users.create_user("PERSON@example.com", "secret-password")
