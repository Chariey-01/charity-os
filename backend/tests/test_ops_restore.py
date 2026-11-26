"""ops/db/restore.sh and ops/db/restore-drill.sh."""

import secrets
import shutil
import subprocess
from pathlib import Path

import pytest
from django.db import connection

from planning.models import Area, DailyPlan, DailyPlanItem, Task
from tests.opsdb import psql, result_value, run


def fake_backup(directory):
    directory.mkdir(parents=True)
    (directory / "database.dump").write_bytes(b"not really a dump")
    for file in (
        "row-counts.tsv",
        "content-fingerprints.tsv",
        "schema-summary.tsv",
        "migrations.tsv",
    ):
        (directory / file).write_text("")
    (directory / "MANIFEST").write_text("format_version=1\ndatabase=charityos\n")
    subprocess.run(
        "sha256sum database.dump MANIFEST row-counts.tsv content-fingerprints.tsv "
        "schema-summary.tsv migrations.tsv > SHA256SUMS",
        shell=True,
        cwd=directory,
        check=True,
    )
    return directory


UNREACHABLE = {"PGHOST": "/nonexistent-charityos-socket", "PGPORT": "1"}


# --- Refusals before any connection -------------------------------------------------


@pytest.mark.parametrize(
    "target, reason",
    [
        ("charityos", "protected"),
        ("charityos_acceptance", "protected"),
        ("postgres", "protected"),
        ("template1", "protected"),
        ("test_charityos", "protected"),
        ("charityos_gate", "charityos_restore"),
        ("restore_me", "charityos_restore"),
        ("Charityos_restore", "not a valid database name"),
    ],
)
def test_restore_refuses_protected_or_unprefixed_targets(tmp_path, target, reason):
    backup = fake_backup(tmp_path / "20261125T000000Z_manual")

    result = run(
        "restore.sh", "--backup", str(backup), "--target", target, env=UNREACHABLE
    )

    assert result.returncode == 2
    assert reason in result.stderr


def test_restore_refuses_a_modified_backup_before_connecting(tmp_path):
    backup = fake_backup(tmp_path / "20261125T000000Z_manual")
    with open(backup / "database.dump", "ab") as dump:
        dump.write(b"tampered")

    # An unreachable server proves the refusal comes before any connection.
    result = run(
        "restore.sh",
        "--backup",
        str(backup),
        "--target",
        "charityos_restore_x",
        env=UNREACHABLE,
    )

    assert result.returncode == 2
    assert "checksum mismatch" in result.stderr


def test_restore_refuses_an_incomplete_backup(tmp_path):
    backup = fake_backup(tmp_path / "20261125T000000Z_manual")
    (backup / "migrations.tsv").unlink()

    result = run(
        "restore.sh",
        "--backup",
        str(backup),
        "--target",
        "charityos_restore_x",
        env=UNREACHABLE,
    )

    assert result.returncode == 2
    assert "missing migrations.tsv" in result.stderr


def test_drill_refuses_unapproved_sources(tmp_path):
    for source in ("charityos", "charityos_gate", "test_charityos"):
        result = run("restore-drill.sh", "--source", source, "--root", str(tmp_path))

        assert result.returncode == 2
        assert "not approved" in result.stderr


# --- Round trip against this run's database -------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_restore_is_exact_and_never_overwrites(
    tmp_path, pg_env, restored_databases, django_user_model
):
    owner = django_user_model.objects.create_user("backup@example.com", "password")
    area = Area.objects.create(user=owner, name="Study", slug="study")
    task = Task.objects.create(user=owner, title="Read chapter 3", area=area)
    plan = DailyPlan.objects.create(
        user=owner, local_date="2026-11-25", timezone_name="UTC"
    )
    DailyPlanItem.objects.create(
        user=owner, plan=plan, task=task, title_snapshot=task.title
    )
    backup = run(
        "backup.sh",
        "--database",
        connection.settings_dict["NAME"],
        "--root",
        str(tmp_path / "backups"),
        "--no-prune",
        env=pg_env,
    )
    assert backup.returncode == 0, backup.stderr
    backup_dir = Path(result_value(backup, "BACKUP"))

    token = secrets.token_hex(16)
    target = f"charityos_restore_t{token[:10]}"
    restored_databases.append((target, token))
    restore = run(
        "restore.sh",
        "--backup",
        str(backup_dir),
        "--target",
        target,
        "--owner-token",
        token,
        env=pg_env,
    )

    assert restore.returncode == 0, restore.stderr
    assert result_value(restore, "RESTORED") == target
    for check in (
        "OK   row counts",
        "OK   content fingerprints",
        "OK   schema summary",
        "OK   applied migrations",
        "OK   manage.py check",
    ):
        assert check in restore.stderr
    comment = psql(
        pg_env,
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
        f"WHERE datname = '{target}'",
    )
    assert f"source={connection.settings_dict['NAME']}/{backup_dir.name}" in comment

    again = run(
        "restore.sh", "--backup", str(backup_dir), "--target", target, env=pg_env
    )
    assert again.returncode == 2
    assert "already exists; restore never overwrites" in again.stderr


@pytest.mark.django_db(transaction=True)
def test_restore_detects_a_copy_that_differs_from_the_backup(
    tmp_path, pg_env, restored_databases, django_user_model
):
    django_user_model.objects.create_user("backup@example.com", "password")
    backup = run(
        "backup.sh",
        "--database",
        connection.settings_dict["NAME"],
        "--root",
        str(tmp_path / "backups"),
        "--no-prune",
        env=pg_env,
    )
    backup_dir = Path(result_value(backup, "BACKUP"))
    # Forge a consistent-looking backup whose recorded content no longer matches
    # its dump: restore must notice the difference after loading.
    forged = tmp_path / "forged" / backup_dir.name
    shutil.copytree(backup_dir, forged)
    for path in forged.iterdir():
        path.chmod(0o600)
    fingerprints = (forged / "content-fingerprints.tsv").read_text()
    line = next(row for row in fingerprints.splitlines() if "users_user" in row)
    (forged / "content-fingerprints.tsv").write_text(
        fingerprints.replace(line, line.split("\t")[0] + "\t" + "0" * 32)
    )
    subprocess.run(
        "sha256sum database.dump MANIFEST row-counts.tsv content-fingerprints.tsv "
        "schema-summary.tsv migrations.tsv > SHA256SUMS",
        shell=True,
        cwd=forged,
        check=True,
    )
    token = secrets.token_hex(16)
    target = f"charityos_restore_t{token[:10]}"
    restored_databases.append((target, token))

    result = run(
        "restore.sh",
        "--backup",
        str(forged),
        "--target",
        target,
        "--owner-token",
        token,
        "--skip-django-check",
        env=pg_env,
    )

    assert result.returncode == 1
    assert "FAIL content fingerprints" in result.stderr
    assert "kept for inspection" in result.stderr
