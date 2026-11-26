"""ops/db/backup.sh and its retention policy (ops/db/retention.py)."""

import importlib.util
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.db import connection

from tests.opsdb import OPS, REPO_ROOT, result_value, run

spec = importlib.util.spec_from_file_location("retention", OPS / "retention.py")
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def name(moment, label="manual"):
    return moment.strftime("%Y%m%dT%H%M%SZ") + f"_{label}"


# --- Retention policy ------------------------------------------------------------


def test_retention_keeps_14_daily_and_8_weekly():
    names = [name(NOW - timedelta(days=age)) for age in range(120)]

    kept = set(names) - set(retention.plan_deletions(names, NOW))

    assert {name(NOW - timedelta(days=age)) for age in range(14)} <= kept
    weeks_kept = {
        (NOW - timedelta(days=age)).isocalendar()[:2]
        for age in range(120)
        if name(NOW - timedelta(days=age)) in kept
    }
    assert len(weeks_kept) == 8
    weeks_in_daily_window = {
        (NOW - timedelta(days=age)).isocalendar()[:2] for age in range(14)
    }
    assert len(kept) == 14 + 8 - len(weeks_in_daily_window)


def test_retention_keeps_only_the_newest_backup_of_a_day():
    morning = name(NOW - timedelta(hours=6))
    evening = name(NOW - timedelta(hours=1))

    assert retention.plan_deletions([morning, evening], NOW) == [morning]


def test_recent_pre_migrate_backups_are_kept_even_on_a_busy_day():
    before = name(NOW - timedelta(hours=3), "pre-migrate")
    later = name(NOW - timedelta(hours=1))
    old = name(NOW - timedelta(days=40, hours=3), "pre-migrate")
    old_daily = name(NOW - timedelta(days=40, hours=1))

    deleted = retention.plan_deletions([before, later, old, old_daily], NOW)

    assert before not in deleted
    assert old in deleted  # older than 30 days and not the newest of its day/week


def test_drill_backups_are_evidence_and_never_pruned():
    first = name(NOW - timedelta(hours=5), "drill")
    second = name(NOW - timedelta(hours=1), "drill")
    old = name(NOW - timedelta(days=200), "drill")
    newer_manual = name(NOW)

    assert retention.plan_deletions([first, second, old, newer_manual], NOW) == []


def test_retention_never_deletes_the_newest_unknown_or_future_backups():
    future = name(NOW + timedelta(days=3))
    newest = name(NOW)
    stray = ["notes", "20261125T120000Z", "20261125T120000Z_UPPER", ".x.partial"]

    assert retention.plan_deletions([future, newest, *stray], NOW) == []
    assert retention.plan_deletions([], NOW) == []


# --- Refusals before any connection -------------------------------------------------


def test_backup_refuses_a_root_inside_the_repository():
    result = run("backup.sh", "--database", "charityos", "--root", str(REPO_ROOT / "x"))

    assert result.returncode == 2
    assert "inside the repository" in result.stderr


def test_backup_refuses_a_root_inside_any_git_work_tree(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    result = run("backup.sh", "--database", "charityos", "--root", str(tmp_path / "b"))

    assert result.returncode == 2
    assert "inside a git work tree" in result.stderr


@pytest.mark.parametrize("bad", ["Charity", "a-b", "x;drop", ""])
def test_backup_refuses_invalid_database_names(tmp_path, bad):
    result = run("backup.sh", "--database", bad, "--root", str(tmp_path))

    assert result.returncode == 2


# --- Against this run's database -------------------------------------------------------


def backup(pg_env, root, *extra):
    return run(
        "backup.sh",
        "--database",
        connection.settings_dict["NAME"],
        "--root",
        str(root),
        *extra,
        env=pg_env,
    )


@pytest.mark.django_db(transaction=True)
def test_backup_is_verified_complete_and_read_only(tmp_path, pg_env, django_user_model):
    django_user_model.objects.create_user("backup@example.com", "password")

    result = backup(pg_env, tmp_path, "--label", "test", "--no-prune")

    assert result.returncode == 0, result.stderr
    directory = Path(result_value(result, "BACKUP"))
    assert directory.name.endswith("_test")
    files = sorted(path.name for path in directory.iterdir())
    assert files == [
        "MANIFEST",
        "SHA256SUMS",
        "content-fingerprints.tsv",
        "database.dump",
        "migrations.tsv",
        "row-counts.tsv",
        "schema-summary.tsv",
    ]
    counts = dict(
        line.split("\t")
        for line in (directory / "row-counts.tsv").read_text().split("\n")
        if line
    )
    assert counts["public.users_user"] == "1"
    assert all(path.stat().st_mode & 0o222 == 0 for path in directory.iterdir())
    assert directory.stat().st_mode & 0o222 == 0
    check = subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=directory)
    assert check.returncode == 0


@pytest.mark.django_db(transaction=True)
def test_backups_are_never_overwritten(tmp_path, pg_env):
    database_dir = tmp_path / connection.settings_dict["NAME"]
    database_dir.mkdir()
    start = datetime.now(UTC)
    # Occupy every name the next ten seconds could produce.
    for second in range(10):
        taken = database_dir / name(start + timedelta(seconds=second))
        taken.mkdir()
        (taken / "SENTINEL").write_text("existing backup")

    result = backup(pg_env, tmp_path, "--no-prune")

    assert result.returncode == 2
    assert "never overwritten" in result.stderr
    assert all(
        (path / "SENTINEL").read_text() == "existing backup"
        and [child.name for child in path.iterdir()] == ["SENTINEL"]
        for path in database_dir.iterdir()
    )


@pytest.mark.django_db(transaction=True)
def test_retention_removes_only_recognisable_backups(tmp_path, pg_env):
    database = connection.settings_dict["NAME"]
    database_dir = tmp_path / database
    database_dir.mkdir()
    day = datetime(2025, 1, 6, tzinfo=UTC)

    def make(label_time, manifest_database):
        directory = database_dir / name(label_time)
        directory.mkdir()
        if manifest_database:
            (directory / "MANIFEST").write_text(
                f"format_version=1\ndatabase={manifest_database}\n"
            )
            (directory / "SHA256SUMS").write_text("")
        return directory

    superseded = make(day + timedelta(hours=1), database)  # same day, older
    stray = make(day + timedelta(hours=2), None)  # no manifest: not ours
    foreign = make(day + timedelta(hours=3), "someone_else")  # another database
    newest_of_day = make(day + timedelta(hours=4), database)

    result = backup(pg_env, tmp_path)

    assert result.returncode == 0, result.stderr
    assert not superseded.exists()
    assert stray.exists() and foreign.exists() and newest_of_day.exists()
    assert "skipping" in result.stderr
