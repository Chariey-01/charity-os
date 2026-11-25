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


def test_the_database_defaults_to_postgres_db(tmp_path):
    result = run(
        "migrate-with-backup.sh",
        "--root",
        str(tmp_path),
        env={
            "POSTGRES_DB": "charityos_default_probe",
            "PGHOST": str(tmp_path / "no-server"),
            "PGPORT": "1",
        },
    )

    assert result.returncode != 0
    assert "backup of charityos_default_probe" in result.stderr
    assert "NOT migrating charityos_default_probe" in result.stderr


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
