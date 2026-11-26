"""Each checkout runs its tests in its own database (config/testdb.py)."""

import os
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from config import testdb

CHECKOUT = Path(settings.BASE_DIR).parent


def test_default_name_is_derived_from_the_checkout_path(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()

    name = testdb.default_test_database_name(first)

    assert name.startswith("test_charityos_")
    assert len(name) == len("test_charityos_") + 10
    assert testdb.default_test_database_name(first) == name
    assert testdb.default_test_database_name(second) != name


def test_symlinked_checkouts_share_their_real_path(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)

    assert testdb.default_test_database_name(link) == testdb.default_test_database_name(
        real
    )


def test_override_wins_when_it_is_safe(tmp_path):
    env = {"CHARITYOS_TEST_DB": "test_second_run"}

    assert testdb.test_database_name(tmp_path, env, "charityos") == "test_second_run"


@pytest.mark.parametrize(
    "unsafe",
    [
        "charityos",  # no test_ prefix: could be a real database
        "test_charityos",  # the old shared database
        "test_charityos_p2",  # created by another session
        "test_charityos_f794a3f543",  # another checkout's automatic name
        "test_Upper",
        "test_with-dash",
        "test_" + "x" * 59,  # longer than PostgreSQL's 63-character limit
    ],
)
def test_unsafe_overrides_are_refused(tmp_path, unsafe):
    with pytest.raises(ImproperlyConfigured):
        testdb.test_database_name(tmp_path, {"CHARITYOS_TEST_DB": unsafe}, "charityos")


def test_the_application_database_is_never_used_for_tests(tmp_path):
    env = {"CHARITYOS_TEST_DB": "test_app"}

    with pytest.raises(ImproperlyConfigured, match="would drop it"):
        testdb.test_database_name(tmp_path, env, "test_app")


@pytest.mark.django_db
def test_this_run_uses_this_checkouts_database():
    expected = os.environ.get("CHARITYOS_TEST_DB") or testdb.default_test_database_name(
        CHECKOUT
    )

    assert settings.DATABASES["default"]["TEST"]["NAME"] == expected
    assert connection.settings_dict["NAME"] == expected
    assert connection.settings_dict["NAME"] not in testdb.PROTECTED_NAMES
