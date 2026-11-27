"""History-bearing records cannot disappear with their parents (Phase 0, S4)."""

from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.models import RestrictedError

from planning.models import Task
from roadmaps.models import RoadmapNodePrerequisite
from tests.history_graph import (
    OWNED_MODELS,
    added_columns,
    build_history,
    owned_counts,
    table_rows,
)

pytestmark = pytest.mark.django_db

# Pure structure with no history of its own: deleting a node may remove these.
STRUCTURAL = {
    ("roadmaps.RoadmapNodePrerequisite", "node"),
    ("roadmaps.RoadmapNodePrerequisite", "prerequisite"),
    # A cheer exists only inside its partnership; partnerships are never
    # deleted except when one of the two people is erased.
    ("community.Cheer", "partnership"),
}
RESTRICT_MIGRATIONS = (
    ("planning", "0010"),
    ("roadmaps", "0003"),
    ("execution", "0003"),
    ("records", "0003"),
    ("health", "0003"),
    ("scheduling", "0002"),
)
BEFORE_RESTRICT = {
    "planning": "0009_planningevent_archive_events",
    "roadmaps": "0002_archived_at",
    "execution": "0002_initial",
    "records": "0002_archived_at",
    "health": "0002_archived_at",
    "scheduling": "0001_initial",
}


def test_history_links_restrict_and_only_user_links_cascade():
    for model in apps.get_models():
        # Django's and django-axes' own tables hold no CharityOS history.
        if model._meta.app_label in {
            "admin",
            "auth",
            "contenttypes",
            "sessions",
            "axes",
        }:
            continue
        for field in model._meta.get_fields():
            if not isinstance(field, models.ForeignKey):  # includes OneToOneField
                continue
            key = (model._meta.label, field.name)
            rule = field.remote_field.on_delete
            if field.related_model._meta.label == "users.User":
                assert rule is models.CASCADE, key  # the user-erasure path
            elif key in STRUCTURAL:
                assert rule is models.CASCADE, key
            else:
                assert rule is models.RESTRICT, key


@pytest.mark.parametrize("app, migration", RESTRICT_MIGRATIONS)
def test_restrict_migrations_emit_no_sql(app, migration):
    out = StringIO()
    call_command("sqlmigrate", app, migration, stdout=out)

    statements = [
        line
        for line in out.getvalue().splitlines()
        if line.strip() and not line.startswith("--")
    ]
    assert statements == ["BEGIN;", "COMMIT;"]


@pytest.mark.parametrize(
    "parent",
    [
        "area",
        "challenge",
        "roadmap",
        "section",
        "node",
        "task",
        "plan",
        "session",
        "win",
    ],
)
def test_deleting_a_parent_of_history_is_refused(django_user_model, parent):
    user = django_user_model.objects.create_user("owner@example.com", "password")
    graph = build_history(user)
    before = owned_counts(user)

    with pytest.raises(RestrictedError):
        graph[parent].delete()

    assert owned_counts(user) == before


def test_history_free_records_can_still_be_deleted(django_user_model):
    user = django_user_model.objects.create_user("owner@example.com", "password")
    build_history(user)
    typo = Task.objects.create(user=user, title="Typo, never used")

    RoadmapNodePrerequisite.objects.get(user=user).delete()
    typo.delete()

    assert not RoadmapNodePrerequisite.objects.filter(user=user).exists()
    assert not Task.objects.filter(pk=typo.pk).exists()


def rows_of(user_id):
    snapshot = {}
    for name in OWNED_MODELS:
        model = apps.get_model(name)
        columns = [field.attname for field in model._meta.concrete_fields]
        snapshot[name] = list(
            model.objects.filter(user_id=user_id).order_by("pk").values_list(*columns)
        )
    return snapshot


def test_erasing_a_user_removes_their_history_and_nothing_else(django_user_model):
    """Before Phase 0 this raised ProtectedError (FocusSession.area was
    PROTECT), so no user with a focus session could be erased at all."""
    keep = django_user_model.objects.create_user("keep@example.com", "password")
    gone = django_user_model.objects.create_user("gone@example.com", "password")
    build_history(keep, label="k")
    build_history(gone, label="g")
    kept_before = rows_of(keep.pk)
    gone_id = gone.pk
    assert all(owned_counts(gone_id).values())

    gone.delete()

    assert set(owned_counts(gone_id).values()) == {0}
    assert not django_user_model.objects.filter(pk=gone_id).exists()
    assert rows_of(keep.pk) == kept_before


def apply(targets):
    MigrationExecutor(connection).migrate(targets)
    return (
        MigrationExecutor(connection)
        ._create_project_state(with_applied_migrations=True)
        .apps
    )


def all_forward():
    return apply(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_restrict_migrations_keep_old_shape_data_both_ways():
    try:
        for app, target in BEFORE_RESTRICT.items():
            old = apply([(app, target)])
        owner = old.get_model("users", "User").objects.create(
            email="old-shape@example.com", password="x"
        )
        build_history(owner, registry=old)
        before = table_rows(old)

        forward = all_forward()
        assert table_rows(forward, columns_from=old) == before
        # Columns added since hold nothing yet: planning.0011's due_date, then
        # planning.0012 (checklist, goal, milestone, notes, project) and
        # roadmaps.0004 (purpose, notes, dates, goal; criteria; resource kind).
        assert added_columns(forward, columns_from=old) == {
            "planning.Task": {(None, "[]", None, None, "", None)},
            "roadmaps.Roadmap": {(None, "", "", None, None)},
            "roadmaps.RoadmapNode": {("", "")},
            "roadmaps.RoadmapResource": {("other", "")},
        }
        for app, target in BEFORE_RESTRICT.items():
            reverted = apply([(app, target)])
        assert table_rows(reverted) == before
    finally:
        all_forward()
