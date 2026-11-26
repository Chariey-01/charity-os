"""reflections.0003: versions and revisions, forward and back, with old-shape data."""

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db
BEFORE = "0002_archived_at"
AFTER = "0003_reflection_revisions"


def apply(targets):
    MigrationExecutor(connection).migrate(targets)
    return (
        MigrationExecutor(connection)
        ._create_project_state(with_applied_migrations=True)
        .apps
    )


def all_forward():
    return apply(MigrationExecutor(connection).loader.graph.leaf_nodes())


def applied():
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM django_migrations WHERE app = 'reflections'")
        return {row[0] for row in cursor.fetchall()}


def test_the_migration_only_adds_columns_and_a_table():
    out = StringIO()
    call_command("sqlmigrate", "reflections", "0003", stdout=out)
    statements = [
        line
        for line in out.getvalue().splitlines()
        if line.strip() and not line.startswith("--")
    ]

    adds = [line for line in statements if 'ADD COLUMN "version"' in line]
    assert len(adds) == 2
    assert all("DEFAULT 1 NOT NULL" in line for line in adds)  # constant: no rewrite
    assert any(
        line.startswith('CREATE TABLE "reflections_reflectionrevision"')
        for line in statements
    )
    assert not [line for line in statements if line.startswith("UPDATE")]


def rows(apps, model, columns):
    return list(
        apps.get_model("reflections", model)
        .objects.order_by("pk")
        .values_list(*columns)
    )


DAILY = (
    "id",
    "user_id",
    "local_date",
    "went_well",
    "learned",
    "improve",
    "mood",
    "closed_at",
    "archived_at",
)
WEEKLY = (
    "id",
    "user_id",
    "week_start_date",
    "wins",
    "lessons",
    "next_week",
    "closed_at",
)


@pytest.mark.django_db(transaction=True)
def test_existing_reflections_round_trip_and_start_at_version_one():
    try:
        old = apply([("reflections", BEFORE)])
        owner = old.get_model("users", "User").objects.create(
            email="r@example.com", password="x"
        )
        old.get_model("reflections", "DailyReflection").objects.create(
            user=owner,
            local_date=date(2026, 11, 20),
            timezone_name="UTC",
            went_well="kept",
            mood=4,
        )
        old.get_model("reflections", "WeeklyReview").objects.create(
            user=owner,
            week_start_date=date(2026, 11, 16),
            week_end_date=date(2026, 11, 22),
            timezone_name="UTC",
            wins="kept",
        )
        before = (
            rows(old, "DailyReflection", DAILY),
            rows(old, "WeeklyReview", WEEKLY),
        )

        new = all_forward()
        after = (rows(new, "DailyReflection", DAILY), rows(new, "WeeklyReview", WEEKLY))
        versions = {
            *new.get_model("reflections", "DailyReflection").objects.values_list(
                "version", flat=True
            ),
            *new.get_model("reflections", "WeeklyReview").objects.values_list(
                "version", flat=True
            ),
        }
        back = apply([("reflections", BEFORE)])

        assert after == before
        assert versions == {1}
        assert (
            rows(back, "DailyReflection", DAILY),
            rows(back, "WeeklyReview", WEEKLY),
        ) == before
    finally:
        all_forward()


@pytest.mark.django_db(transaction=True)
def test_reverse_is_refused_while_revisions_exist():
    try:
        new = all_forward()
        owner = new.get_model("users", "User").objects.create(
            email="r2@example.com", password="x"
        )
        reflection = new.get_model("reflections", "DailyReflection").objects.create(
            user=owner,
            local_date=date(2026, 11, 20),
            timezone_name="UTC",
            went_well="now",
        )
        new.get_model("reflections", "ReflectionRevision").objects.create(
            user=owner,
            daily_reflection=reflection,
            version=1,
            content={"went_well": "before"},
        )

        with pytest.raises(RuntimeError, match="Refusing to reverse reflections.0003"):
            apply([("reflections", BEFORE)])

        assert AFTER in applied()
        assert new.get_model("reflections", "ReflectionRevision").objects.count() == 1
    finally:
        all_forward()
