"""roadmaps/records/reflections/health 0002: archived_at columns.

Forward: nullable columns only, no table rewrite, every existing row kept.
Backward: refused while any archived row exists, because dropping the column
would silently make archived records visible again.
"""

from datetime import UTC, date, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db
T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
APPS = ("roadmaps", "records", "reflections", "health")
MODELS = {
    "roadmaps": ("Roadmap", "RoadmapNode", "RoadmapResource"),
    "records": ("Accomplishment", "Evidence"),
    "reflections": ("DailyReflection", "WeeklyReview"),
    "health": (
        "SleepLog",
        "ExerciseLog",
        "MealLog",
        "DailyWaterTotal",
        "DailyNutritionRating",
    ),
}


def apply(targets):
    MigrationExecutor(connection).migrate(targets)
    return (
        MigrationExecutor(connection)
        ._create_project_state(with_applied_migrations=True)
        .apps
    )


def all_forward():
    return apply(MigrationExecutor(connection).loader.graph.leaf_nodes())


def applied(app):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM django_migrations WHERE app = %s", [app])
        return {row[0] for row in cursor.fetchall()}


def rows(apps):
    """Every column except archived_at, for every model the migrations touch."""
    snapshot = {}
    for app, names in MODELS.items():
        for name in names:
            model = apps.get_model(app, name)
            # Only the columns every compared state has: archived_at arrives in
            # 0002 and version in reflections.0003.
            columns = [
                field.attname
                for field in model._meta.concrete_fields
                if field.name not in ("archived_at", "version")
            ]
            snapshot[name] = list(model.objects.order_by("pk").values_list(*columns))
    return snapshot


def seed(apps):
    User = apps.get_model("users", "User")
    owner = User.objects.create(email="old-shape@example.com", password="x")
    Roadmap = apps.get_model("roadmaps", "Roadmap")
    roadmap = Roadmap.objects.create(user=owner, title="Python", status="active")
    Roadmap.objects.create(user=owner, title="Retired track", status="archived")
    node = apps.get_model("roadmaps", "RoadmapNode").objects.create(
        user=owner, roadmap=roadmap, title="Loops", node_type="item"
    )
    apps.get_model("roadmaps", "RoadmapResource").objects.create(
        user=owner, node=node, label="Docs", url="https://docs.python.org"
    )
    win = apps.get_model("records", "Accomplishment").objects.create(
        user=owner, local_date=date(2026, 11, 20), timezone_name="UTC", title="Shipped"
    )
    Evidence = apps.get_model("records", "Evidence")
    Evidence.objects.create(user=owner, kind="note", text="Notes", roadmap_node=node)
    Evidence.objects.create(user=owner, kind="note", text="Proof", accomplishment=win)
    reflections = "reflections"
    apps.get_model(reflections, "DailyReflection").objects.create(
        user=owner, local_date=date(2026, 11, 20), timezone_name="UTC", went_well="A"
    )
    apps.get_model(reflections, "WeeklyReview").objects.create(
        user=owner,
        week_start_date=date(2026, 11, 16),
        week_end_date=date(2026, 11, 22),
        timezone_name="UTC",
        wins="B",
    )
    apps.get_model("health", "SleepLog").objects.create(
        user=owner,
        started_at=T0 - timedelta(hours=8),
        woke_at=T0,
        timezone_name="UTC",
        wake_local_date=date(2026, 11, 20),
    )
    apps.get_model("health", "ExerciseLog").objects.create(
        user=owner, started_at=T0, ended_at=T0 + timedelta(minutes=30), activity="Run"
    )
    apps.get_model("health", "MealLog").objects.create(
        user=owner,
        local_date=date(2026, 11, 20),
        timezone_name="UTC",
        meal_type="lunch",
        description="Rice",
    )
    apps.get_model("health", "DailyWaterTotal").objects.create(
        user=owner, local_date=date(2026, 11, 20), timezone_name="UTC", total_ml=1500
    )
    apps.get_model("health", "DailyNutritionRating").objects.create(
        user=owner, local_date=date(2026, 11, 20), timezone_name="UTC", rating=4
    )


@pytest.mark.parametrize("app", APPS)
def test_columns_are_added_without_rewriting_tables(app):
    out = StringIO()
    call_command("sqlmigrate", app, "0002", stdout=out)

    statements = [
        line
        for line in out.getvalue().splitlines()
        if line.strip() and not line.startswith("--")
    ]
    adds = [line for line in statements if "ADD COLUMN" in line]
    assert len(adds) == len(MODELS[app])
    assert all(
        line.endswith('"archived_at" timestamp with time zone NULL;') for line in adds
    )
    assert not [line for line in statements if "DEFAULT" in line or "UPDATE" in line]


@pytest.mark.django_db(transaction=True)
def test_existing_rows_round_trip_and_the_legacy_archived_status_converts():
    try:
        for app in APPS:
            apply([(app, "0001_initial")])
        old = apps = (
            MigrationExecutor(connection)
            ._create_project_state(with_applied_migrations=True)
            .apps
        )
        seed(old)
        before = rows(old)
        legacy = old.get_model("roadmaps", "Roadmap").objects.get(title="Retired track")

        new = all_forward()
        converted = new.get_model("roadmaps", "Roadmap").objects.get(pk=legacy.pk)
        assert converted.status == "active"
        assert converted.archived_at == legacy.updated_at
        assert converted.updated_at == legacy.updated_at
        others = {
            name: list(
                new.get_model(app, name)
                .objects.exclude(pk=legacy.pk)
                .values_list("archived_at", flat=True)
            )
            for app, names in MODELS.items()
            for name in names
        }
        assert all(value is None for values in others.values() for value in values)
        after_forward = rows(new)
        after_forward["Roadmap"] = [
            row for row in after_forward["Roadmap"] if row[0] != legacy.pk
        ]
        expected = dict(before)
        expected["Roadmap"] = [row for row in before["Roadmap"] if row[0] != legacy.pk]
        assert after_forward == expected

        # The converted roadmap is archived, so reversing roadmaps is refused...
        with pytest.raises(RuntimeError, match="Refusing to reverse roadmaps.0002"):
            apply([("roadmaps", "0001_initial")])
        assert "0002_archived_at" in applied("roadmaps")

        # ...until it is restored. Then every app reverses and re-applies cleanly.
        new.get_model("roadmaps", "Roadmap").objects.filter(pk=legacy.pk).update(
            archived_at=None
        )
        for app in APPS:
            apps = apply([(app, "0001_initial")])
        reversed_rows = rows(apps)
        assert reversed_rows["RoadmapNode"] == before["RoadmapNode"]
        for name in ("Evidence", "DailyReflection", "SleepLog", "DailyWaterTotal"):
            assert reversed_rows[name] == before[name]
        assert rows(all_forward()) == rows(apps)
    finally:
        all_forward()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "app, model",
    [
        ("roadmaps", "RoadmapResource"),
        ("records", "Evidence"),
        ("reflections", "WeeklyReview"),
        ("health", "DailyWaterTotal"),
    ],
)
def test_reverse_is_refused_while_archived_rows_exist(app, model):
    try:
        apps = all_forward()
        User = apps.get_model("users", "User")
        owner = User.objects.create(email=f"{app}@example.com", password="x")
        node = None
        if app == "roadmaps":
            roadmap = apps.get_model("roadmaps", "Roadmap").objects.create(
                user=owner, title="R"
            )
            node = apps.get_model("roadmaps", "RoadmapNode").objects.create(
                user=owner, roadmap=roadmap, title="N", node_type="item"
            )
        values = {
            "RoadmapResource": {"node": node, "label": "L", "url": "https://x.org"},
            "Evidence": {"kind": "note", "text": "t"},
            "WeeklyReview": {
                "week_start_date": date(2026, 11, 16),
                "week_end_date": date(2026, 11, 22),
                "timezone_name": "UTC",
            },
            "DailyWaterTotal": {
                "local_date": date(2026, 11, 20),
                "timezone_name": "UTC",
            },
        }[model]
        if model == "Evidence":
            values["accomplishment"] = apps.get_model(
                "records", "Accomplishment"
            ).objects.create(
                user=owner,
                local_date=date(2026, 11, 20),
                timezone_name="UTC",
                title="W",
            )
        row = apps.get_model(app, model).objects.create(
            user=owner, archived_at=T0, **values
        )

        with pytest.raises(RuntimeError, match=f"Refusing to reverse {app}.0002"):
            apply([(app, "0001_initial")])

        assert "0002_archived_at" in applied(app)
        # Later migrations of the app may have been reversed before the guard
        # refused, so read only the column under test.
        stored = (
            apps.get_model(app, model)
            .objects.filter(pk=row.pk)
            .values_list("archived_at", flat=True)
            .get()
        )
        assert stored == T0
    finally:
        all_forward()
