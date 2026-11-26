"""ops/db/migrate-with-backup.sh: no migration without a verified backup first."""

from pathlib import Path

import pytest
from django.db import connection

from tests.opsdb import result_value, run


def test_migrations_never_run_when_the_backup_fails(tmp_path):
    marker = tmp_path / "migrate-ran"
    fake_python = tmp_path / "python"
    fake_python.write_text(f"#!/bin/sh\ntouch {marker}\n")
    fake_python.chmod(0o755)

    result = run(
        "migrate-with-backup.sh",
        "--database",
        "charityos_unreachable",
        "--root",
        str(tmp_path / "backups"),
        env={
            "PGHOST": str(tmp_path / "no-server"),
            "PGPORT": "1",
            "CHARITYOS_PYTHON": str(fake_python),
        },
    )

    assert result.returncode != 0
    assert "NOT migrating" in result.stderr
    assert not marker.exists()


def test_the_database_must_be_named_explicitly(tmp_path):
    """No default target: POSTGRES_DB (here, or the personal database named
    in .env) is never migrated by a bare run."""
    marker = tmp_path / "python-ran"
    fake_python = tmp_path / "python"
    fake_python.write_text(f"#!/bin/sh\ntouch {marker}\n")
    fake_python.chmod(0o755)

    result = run(
        "migrate-with-backup.sh",
        "--root",
        str(tmp_path / "backups"),
        env={
            "POSTGRES_DB": "charityos_default_probe",
            "CHARITYOS_PYTHON": str(fake_python),
        },
    )

    assert result.returncode == 2
    assert "name the database to migrate with --database" in result.stderr
    assert not (tmp_path / "backups").exists()
    assert not marker.exists()


@pytest.mark.django_db(transaction=True)
def test_backs_up_then_migrates(tmp_path, pg_env):
    database = connection.settings_dict["NAME"]

    result = run(
        "migrate-with-backup.sh",
        "--database",
        database,
        "--root",
        str(tmp_path / "backups"),
        env={**pg_env, "DJANGO_SETTINGS_MODULE": "config.settings.development"},
    )

    assert result.returncode == 0, result.stderr
    backup = Path(result_value(result, "BACKUP"))
    assert backup.parent == tmp_path / "backups" / database
    assert backup.name.endswith("_pre-migrate")
    assert (backup / "SHA256SUMS").exists()
    assert "step 1/2" in result.stderr
    assert result.stderr.index("step 1/2") < result.stderr.index("step 2/2")
    assert "No migrations to apply." in result.stdout


@pytest.mark.django_db(transaction=True)
def test_backup_and_migrate_always_reach_the_same_server(tmp_path, pg_env):
    """PG* settings (documented as taking precedence) must also steer Django.

    Before this was enforced, pg_dump followed PG* while manage.py followed
    POSTGRES_*, so a backup of one server could precede a migration of another.
    """
    database = connection.settings_dict["NAME"]

    result = run(
        "migrate-with-backup.sh",
        "--database",
        database,
        "--root",
        str(tmp_path / "backups"),
        env={
            **pg_env,
            "DJANGO_SETTINGS_MODULE": "config.settings.development",
            # A different, unreachable server for Django unless PG* wins.
            "POSTGRES_HOST": str(tmp_path / "other-server"),
            "POSTGRES_PORT": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "No migrations to apply." in result.stdout


@pytest.mark.django_db(transaction=True)
def test_a_different_postgres_port_cannot_split_backup_and_migrate(tmp_path, pg_env):
    database = connection.settings_dict["NAME"]
    result = run(
        "migrate-with-backup.sh",
        "--database",
        database,
        "--root",
        str(tmp_path / "backups"),
        env={
            **pg_env,
            "DJANGO_SETTINGS_MODULE": "config.settings.development",
            "POSTGRES_HOST": pg_env["PGHOST"],
            "POSTGRES_PORT": "1",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "target confirmed" in result.stderr


@pytest.mark.django_db(transaction=True)
def test_postgres_db_naming_another_database_does_not_redirect_the_migration(
    tmp_path, pg_env
):
    database = connection.settings_dict["NAME"]
    result = run(
        "migrate-with-backup.sh",
        "--database",
        database,
        "--root",
        str(tmp_path / "backups"),
        env={
            **pg_env,
            "DJANGO_SETTINGS_MODULE": "config.settings.development",
            "POSTGRES_DB": "charityos_some_other_database",
        },
    )
    assert result.returncode == 0, result.stderr
    assert f"target confirmed: Django and the backup both reach {database}|" in (
        result.stderr
    )


def test_database_url_is_refused_before_anything_runs(tmp_path):
    marker = tmp_path / "python-ran"
    fake_python = tmp_path / "python"
    fake_python.write_text(f"#!/bin/sh\ntouch {marker}\n")
    fake_python.chmod(0o755)
    result = run(
        "migrate-with-backup.sh",
        "--database",
        "charityos_whatever",
        "--root",
        str(tmp_path / "backups"),
        env={
            "DATABASE_URL": "postgres://u:p@elsewhere:5432/charityos_whatever",
            "CHARITYOS_PYTHON": str(fake_python),
        },
    )
    assert result.returncode == 2
    assert "DATABASE_URL is set" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "backups").exists()


@pytest.mark.django_db(transaction=True)
def test_migration_is_refused_when_django_reaches_another_database(tmp_path, pg_env):
    """Even with matching settings, a different identity stops the migration."""
    database = connection.settings_dict["NAME"]
    marker = tmp_path / "migrate-ran"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *migrate*) touch " + str(marker) + " ;;\n"
        "  *shell*) echo 'IDENTITY=impostor|1|1.0' ;;\n"
        "esac\n"
    )
    fake_python.chmod(0o755)
    result = run(
        "migrate-with-backup.sh",
        "--database",
        database,
        "--root",
        str(tmp_path / "backups"),
        env={**pg_env, "CHARITYOS_PYTHON": str(fake_python)},
    )
    assert result.returncode == 2, result.stderr
    assert "Django would migrate 'impostor|1|1.0'" in result.stderr
    assert "NOT migrating" in result.stderr
    assert not marker.exists()
    # The verified backup still exists for inspection.
    assert list((tmp_path / "backups" / database).glob("*_pre-migrate"))
