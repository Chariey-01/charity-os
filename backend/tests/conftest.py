import sys

import pytest
from django.conf import settings
from django.db import connection

from tests.opsdb import major, psql


@pytest.fixture
def pg_env(django_db_blocker):
    """libpq settings for running ops/db scripts against this run's database.

    Skips when the client tools are older than the server: backup.sh refuses
    that combination by design.
    """
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        server = int(cursor.fetchone()[0]) // 10000
    if min(major("pg_dump"), major("pg_restore")) < server:
        pytest.skip(f"PostgreSQL client tools are older than server {server}")
    db = settings.DATABASES["default"]
    return {
        "PGHOST": db["HOST"] or "localhost",
        "PGPORT": str(db["PORT"] or 5432),
        "PGUSER": db["USER"],
        "PGPASSWORD": db["PASSWORD"],
        "CHARITYOS_PYTHON": sys.executable,
    }


@pytest.fixture
def restored_databases(pg_env):
    """Databases a test restores into, as (name, owner token) pairs.

    Afterwards each is dropped, but only if its COMMENT carries the token the
    test generated, i.e. only databases the test itself created.
    """
    created = []
    yield created
    for target, token in created:
        comment = psql(
            pg_env,
            "SELECT coalesce(shobj_description(oid, 'pg_database'), '') "
            f"FROM pg_database WHERE datname = '{target}'",
        )
        if f"owner-token={token}" in comment:
            psql(pg_env, f'DROP DATABASE "{target}"')
