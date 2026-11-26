# Backup and restore

CharityOS keeps years of personal history in one PostgreSQL database. This page describes how that database is backed up, how a backup is restored, and how both are proven to work. The scripts live in [`ops/db/`](../../ops/db/) and print their own usage with `--help`.

## What a backup is

`ops/db/backup.sh --database charityos` writes one folder:

```
~/charityos-backups/charityos/20261125T200539Z_manual/
  database.dump             pg_dump custom-format archive
  MANIFEST                  versions, sizes, totals, dump checksum
  row-counts.tsv            exact row count of every table
  content-fingerprints.tsv  order-independent hash of every table's rows
  schema-summary.tsv        tables, indexes, sequences, views, constraints
  migrations.tsv            applied Django migrations
  SHA256SUMS                checksums of the six files above
```

Properties:

- **Consistent.** A read-only transaction exports its snapshot. `pg_dump` reads that snapshot, and the same transaction counts and fingerprints every table. The manifest therefore describes exactly what is in the dump, even while the app is in use.
- **Verified before it counts.** The archive's table list is checked against the database. The checksums are re-read before the folder is renamed into place. A failed backup leaves no folder behind.
- **Immutable.** The folder and its files are read-only. An existing folder name is refused, never overwritten.
- **Outside the code.** The backup root may not be inside this repository or any git work tree.

The root is `~/charityos-backups` unless `--root` or `CHARITYOS_BACKUP_ROOT` says otherwise.

Connection settings come from the PG* variables if they are set. Otherwise they come from `POSTGRES_*` in the environment or in the checkout's `.env`. That file is parsed, never executed. Whichever server that selects is also passed to every `manage.py` step (check, migrate), so a backup and the migration after it always reach the same server.

## Retention

After each successful backup, older backups of the same database are pruned. The rules are in `ops/db/retention.py`. Days and weeks are UTC. Kept:

- the newest backup, always;
- the newest backup of each of the 14 most recent days that have one;
- the newest backup of each of the 8 most recent ISO weeks that have one;
- every `pre-migrate` backup younger than 30 days;
- every `drill` backup, because a drill report names it as its evidence. Drills also never prune;
- anything dated in the future.

Only folders whose manifest names the same database are ever deleted. Use `--no-prune` to skip retention.

## Before every migration

```bash
ops/db/migrate-with-backup.sh --database NAME
ops/db/migrate-with-backup.sh --database NAME -- planning 0008   # extra migrate args
```

The wrapper never migrates by default; the target is always named. It:

1. Takes a verified `pre-migrate` backup of that database.
2. Confirms that Django would migrate the very database just backed up. The database name, its OID and the server's start time must match through both Django and libpq.
3. Only then runs `manage.py migrate`.

If any step fails, nothing is migrated, and the backup path is printed. The `PG*` server settings are also handed to Django, so the two can't drift apart. While `DATABASE_URL` is set, every `ops/db` script refuses to run. **Use the wrapper instead of a bare `migrate` on any database that holds real records.**

## Restoring

A restore always creates a new database. It never replaces one.

```bash
ops/db/restore.sh --backup ~/charityos-backups/charityos/<folder> --target charityos_restored_20261201
```

Refused before anything is created:

- **Target name:**
  - any target not named `charityos_restore*`;
  - the protected names `charityos`, `charityos_acceptance`, `postgres`, the templates and `test_*`;
  - any database that already exists.
- **Backup:** a damaged or incomplete one (its checksums are verified first).
- **Versions:**
  - a `pg_restore` older than the archive;
  - a server older than the one the backup came from.

After loading, the copy must match the backup's row counts, content fingerprints, schema summary and applied migrations. `manage.py check` must also pass against it. On any mismatch the script fails and keeps the copy for inspection. It never drops anything.

### Recovering the real database

1. Choose the backup. `MANIFEST` shows when it was taken and what it holds.
2. Restore it into a new database, for example `charityos_restored_20261201`, and wait for every check to pass.
3. Stop the app. Set `POSTGRES_DB=charityos_restored_20261201` in `.env`, then start the app again.
4. Keep the old database until the restored one has been used for a while. Remove it only deliberately; nothing here deletes databases.

## Restore drill

```bash
ops/db/restore-drill.sh            # backup + restore + every check, then clean up
ops/db/restore-drill.sh --migrate  # also migrate the copy forward, back and forward again
```

The drill runs only against approved throwaway databases (currently `charityos_acceptance`). Each run:

1. Takes a real backup of the source with `backup.sh`. The dump is read-only.
2. Restores it into a uniquely named `charityos_restore_drill_*` database and runs every restore check.
3. **With `--migrate`, also runs the round trip below.** It uses this checkout's migrations:
   - Migrate forward. Every data table must keep its exact row count.
   - Migrate back to the state recorded in the backup. Applied migrations, the table list and every row of every data table must be identical to the backup.
   - Migrate forward again.
4. Drops the drill database, but only after proving this run created it: the name prefix plus a random token in the database's `COMMENT`. `--keep` leaves it for inspection.

Each run writes its report to `~/charityos-backups/drill-reports/`.

### Drill record

| Date (UTC) | Code | Source | Result |
|---|---|---|---|
| 2026-11-25 20:05 | `ba22611` | `charityos_acceptance`, 35 tables, 499 rows | Passed. All checks matched: checksums, row counts, content fingerprints, schema, 34 migrations and `manage.py check`. `--migrate` applied `planning.0007`/`0008`, reversed them and re-applied them. All 32 data tables were byte-identical to the backup after the reversal. The drill database was dropped. |

## Off-machine copies

A copy on the same disk does not survive the loss of that disk. Copies that leave the machine are always encrypted, and the key never travels with them:

```bash
# one-time: a random key, kept outside the backup and in your password manager
mkdir -p ~/.config/charityos-keys && chmod 700 ~/.config/charityos-keys
openssl rand -base64 32 > ~/.config/charityos-keys/offsite.key && chmod 400 ~/.config/charityos-keys/offsite.key

tar -C ~/charityos-backups -cf - charityos/<folder> |
  gpg --batch --pinentry-mode loopback --passphrase-file ~/.config/charityos-keys/offsite.key \
      --symmetric --cipher-algo AES256 -o charityos-<folder>.tar.gpg
```

Decrypt with `gpg --decrypt` and the same key. Then check `SHA256SUMS` inside the folder before restoring. Never upload an unencrypted dump. No storage service is connected by these scripts.

## Scheduled backups (designed, not installed)

[`ops/db/systemd/`](../../ops/db/systemd/) holds a user-level service and timer. Together they run `backup.sh --database charityos --label scheduled` every night at 02:30, with retention. **They are not installed.** Installing them needs the owner's approval, given only after manual backup and restore have passed against the database they will protect:

```bash
cp ops/db/systemd/charityos-backup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now charityos-backup.timer
loginctl enable-linger "$USER"        # optional: run even when not logged in
systemctl --user list-timers charityos-backup.timer
```

The unit expects the checkout at `~/Progress_tracker`; adjust `WorkingDirectory` and `ExecStart` otherwise.

## Limits

- **Recovery point.** There is no WAL archiving or point-in-time recovery. A restore returns the database to the moment of the chosen backup, so with nightly backups up to a day of changes can be lost. Back up manually before risky work; the migrate wrapper does this for migrations.
- **Versions.** The local cluster and client tools are PostgreSQL 16; compose and CI use 17. A dump from a 17 server needs 17 client tools to back up and to restore. The scripts refuse mismatched versions rather than producing a partial dump. In CI, whose client tools are older than its Postgres 17 service, the backup and restore round-trip tests skip with that reason; the refusal tests still run.
- **Fingerprints.** They compare row text, so they detect any change of content, including changes in column order made by an unusual migration. The drill's backward step relies on migrations restoring the original columns.
