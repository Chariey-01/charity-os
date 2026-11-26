"""api.0001: the idempotency-key table, forward and back, touching nothing else."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def apply(targets):
    MigrationExecutor(connection).migrate(targets)


def tables():
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


def test_the_migration_only_creates_its_own_table():
    out = StringIO()
    call_command("sqlmigrate", "api", "0001", stdout=out)
    statements = [
        line
        for line in out.getvalue().splitlines()
        if line.strip() and not line.startswith("--")
    ]

    created = [line for line in statements if line.startswith("CREATE TABLE")]
    assert created == [line for line in created if '"api_idempotencykey"' in line]
    assert len(created) == 1
    assert not [
        line
        for line in statements
        if line.startswith(("UPDATE", "DELETE", "DROP", "INSERT"))
    ]
    assert not [
        line
        for line in statements
        if line.startswith("ALTER TABLE") and '"api_idempotencykey"' not in line
    ]


def test_forward_back_and_forward_keep_every_other_row(django_user_model):
    django_user_model.objects.create_user("owner@example.com", "pw-123456")
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    # django_migrations records the unapply itself; every other table is data.
    other_tables = sorted(tables() - {"api_idempotencykey", "django_migrations"})

    def counts():
        with connection.cursor() as cursor:
            result = {}
            for table in other_tables:
                cursor.execute(f'SELECT count(*) FROM "{table}"')
                result[table] = cursor.fetchone()[0]
            return result

    before = counts()
    apply([("api", None)])
    assert "api_idempotencykey" not in tables()
    assert counts() == before
    apply(leaves)
    assert "api_idempotencykey" in tables()
    assert counts() == before
