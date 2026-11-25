"""Decide which CharityOS backups retention may delete. Standard library only.

A backup directory is named ``YYYYmmddTHHMMSSZ_<label>`` (UTC). Kept:

* the newest backup, always;
* the newest backup of each of the 14 most recent days that have a backup;
* the newest backup of each of the 8 most recent ISO weeks that have a backup;
* every ``pre-migrate`` backup younger than 30 days;
* anything dated in the future (a wrong clock is not a reason to delete).

Directories whose names do not match the pattern are never deleted. The
caller (backup.sh) re-validates every candidate before removing it.

Usage: python3 -I retention.py <database-backup-dir> [--now ISO8601]
Prints one directory name per line: the backups that may be deleted.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

NAME = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)_(?P<label>[a-z0-9-]{1,20})$")
DAILY = 14
WEEKLY = 8
PRE_MIGRATE_DAYS = 30


@dataclass(frozen=True)
class Backup:
    name: str
    taken_at: datetime
    label: str


def parse(name):
    match = NAME.fullmatch(name)
    if not match:
        return None
    taken_at = datetime.strptime(match["stamp"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return Backup(name, taken_at, match["label"])


def plan_deletions(names, now):
    backups = sorted(
        (backup for backup in map(parse, names) if backup),
        key=lambda backup: backup.taken_at,
        reverse=True,
    )
    if not backups:
        return []
    keep = {backups[0].name}
    newest_per_day = {}
    newest_per_week = {}
    for backup in backups:  # newest first, so the first seen per bucket wins
        newest_per_day.setdefault(backup.taken_at.date(), backup.name)
        newest_per_week.setdefault(backup.taken_at.isocalendar()[:2], backup.name)
    keep.update(newest_per_day[day] for day in sorted(newest_per_day)[-DAILY:])
    keep.update(newest_per_week[week] for week in sorted(newest_per_week)[-WEEKLY:])
    for backup in backups:
        if backup.taken_at > now:
            keep.add(backup.name)
        elif backup.label == "pre-migrate" and now - backup.taken_at <= timedelta(
            days=PRE_MIGRATE_DAYS
        ):
            keep.add(backup.name)
    return sorted(backup.name for backup in backups if backup.name not in keep)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--now", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    now = args.now or datetime.now(UTC)
    if now.tzinfo is None:
        parser.error("--now needs a timezone, e.g. 2026-11-25T10:00:00+00:00")
    names = [path.name for path in args.directory.iterdir() if path.is_dir()]
    for name in plan_deletions(names, now):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
