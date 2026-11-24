import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("planning", "0005_area_health_kind"), ("users", "0002_userpreferences")]
AFTER = [("planning", "0006_default_categories")]


@pytest.mark.django_db(transaction=True)
def test_default_category_migration_only_adds_missing_categories():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    old_apps = executor.loader.project_state(BEFORE).apps
    User = old_apps.get_model("users", "User")
    Area = old_apps.get_model("planning", "Area")
    user = User.objects.create(email="legacy@example.com", timezone="UTC")
    Area.objects.create(user=user, name="Exercise", slug="exercise", color="#123456")
    Area.objects.create(user=user, name="Reading", slug="reading", sort_order=4)
    Area.objects.create(
        user=user, name="Sleep", slug="sleep", archived_at="2026-01-01T00:00:00Z"
    )

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(AFTER)
    new_apps = executor.loader.project_state(AFTER).apps
    Area = new_apps.get_model("planning", "Area")
    areas = {(area.name, area.archived_at is None): area for area in Area.objects.all()}

    exercise = areas[("Exercise", True)]
    assert exercise.color == "#123456"  # a chosen colour is never replaced
    assert exercise.health_kind == "exercise"
    assert areas[("Reading", True)].sort_order == 4  # untouched non-default
    # An archived default stays archived and is not re-created.
    assert ("Sleep", False) in areas and ("Sleep", True) not in areas
    assert ("Social", True) in areas and ("Custom", True) in areas
    assert Area.objects.filter(name__iexact="exercise").count() == 1
    new_ones = [area for area in Area.objects.all() if area.sort_order >= 5]
    assert len(new_ones) == 11  # 13 defaults minus existing Exercise and Sleep

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())
