#!/usr/bin/env bash
# Restore a backup made by backup.sh into a NEW database, then prove the copy is exact.
#
#   ops/db/restore.sh --backup DIR --target NAME [--owner-token TOKEN] [--skip-django-check]
#
# The target must be named charityos_restore* and must not exist. Protected names
# (charityos, charityos_acceptance, postgres, templates, test_*) are always refused.
# Nothing existing is ever overwritten: the database is created by this script,
# labelled with a COMMENT, and filled in a single transaction.
#
# Afterwards it checks, and fails loudly on any difference:
#   * every file's checksum, before anything is created;
#   * exact row counts of every table against row-counts.tsv;
#   * the content fingerprint of every table against content-fingerprints.tsv;
#   * the schema summary (tables, indexes, sequences, views, constraints);
#   * the applied Django migrations against migrations.tsv;
#   * `manage.py check` against the restored database (unless --skip-django-check).
# The restored database is kept, also on failure, for inspection. This script never
# drops anything. To recover, restore into e.g. charityos_restored_YYYYMMDD and point
# POSTGRES_DB at it once it passes.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

BACKUP="" TARGET="" TOKEN="" DJANGO_CHECK=1
while [[ $# -gt 0 ]]; do
  case "$1" in
  --backup) BACKUP="${2:-}" && shift 2 ;;
  --target) TARGET="${2:-}" && shift 2 ;;
  --owner-token) TOKEN="${2:-}" && shift 2 ;;
  --skip-django-check) DJANGO_CHECK=0 && shift ;;
  -h | --help) usage 0 ;;
  *) usage ;;
  esac
done

# --- Checks that need no database connection -----------------------------------
[[ -n "$BACKUP" && -n "$TARGET" ]] || usage
valid_database_name "$TARGET" || refuse "'$TARGET' is not a valid database name"
is_protected_database "$TARGET" && refuse "'$TARGET' is protected and can never be a restore target"
[[ "$TARGET" == "$RESTORE_PREFIX"* ]] || refuse "restore targets must be named ${RESTORE_PREFIX}*"
[[ -z "$TOKEN" || "$TOKEN" =~ ^[a-f0-9]{16,64}$ ]] || refuse "owner token must be 16-64 hex characters"
[[ -d "$BACKUP" ]] || refuse "no backup directory at $BACKUP"
BACKUP="$(realpath "$BACKUP")"
[[ "$(basename "$BACKUP")" =~ ^[A-Za-z0-9_.+-]+$ ]] || refuse "backup directory name has unexpected characters"
for file in MANIFEST SHA256SUMS database.dump row-counts.tsv content-fingerprints.tsv schema-summary.tsv migrations.tsv; do
  [[ -f "$BACKUP/$file" ]] || refuse "$BACKUP is not a complete backup (missing $file)"
done
[[ "$(manifest_value "$BACKUP" format_version)" == "$BACKUP_FORMAT_VERSION" ]] ||
  refuse "unsupported backup format in $BACKUP"
(cd "$BACKUP" && sha256sum --quiet -c SHA256SUMS) ||
  refuse "checksum mismatch in $BACKUP: the backup is damaged or was modified"
[[ "$(sha256sum "$BACKUP/database.dump" | cut -d' ' -f1)" == "$(manifest_value "$BACKUP" dump_sha256)" ]] ||
  refuse "dump checksum does not match the manifest"
require_tools psql pg_restore sha256sum
load_connection_env

# --- Checks against the server (read-only) --------------------------------------
RESTORE_MAJOR="$(tool_major pg_restore)"
DUMP_MAJOR="$(manifest_value "$BACKUP" pg_dump_major)"
SOURCE_MAJOR="$(manifest_value "$BACKUP" server_major)"
TARGET_MAJOR="$(server_major postgres)"
((RESTORE_MAJOR >= DUMP_MAJOR)) ||
  refuse "pg_restore $RESTORE_MAJOR cannot read an archive written by pg_dump $DUMP_MAJOR"
((TARGET_MAJOR >= SOURCE_MAJOR)) ||
  refuse "backup came from PostgreSQL $SOURCE_MAJOR; restoring into older PostgreSQL $TARGET_MAJOR is unsupported"
database_exists "$TARGET" && refuse "database '$TARGET' already exists; restore never overwrites"

# --- Create and fill the new database ------------------------------------------------
SOURCE_DB="$(manifest_value "$BACKUP" database)"
valid_database_name "$SOURCE_DB" || refuse "manifest names an invalid source database"
SOURCE_ID="$SOURCE_DB/$(basename "$BACKUP")"
# CREATE DATABASE fails atomically if the name was taken since the check above.
psql_admin "CREATE DATABASE \"$TARGET\"" || die "could not create $TARGET"
COMMENT="charityos-restore created=$(date -u +%Y%m%dT%H%M%SZ) source=$SOURCE_ID"
[[ -n "$TOKEN" ]] && COMMENT="$COMMENT owner-token=$TOKEN"
psql_admin "COMMENT ON DATABASE \"$TARGET\" IS '$COMMENT'"
log "created $TARGET; restoring $SOURCE_ID"
pg_restore --exit-on-error --single-transaction --no-owner --no-privileges \
  --dbname="$TARGET" "$BACKUP/database.dump" || die "pg_restore failed; $TARGET kept for inspection"

# --- Validate --------------------------------------------------------------------------
FAILED=0
compare() { # label expected-file actual-text
  if diff <(cat "$2") <(printf '%s\n' "$3" | sed '/^$/d') >/dev/null; then
    log "OK   $1"
  else
    log "FAIL $1"
    diff <(cat "$2") <(printf '%s\n' "$3" | sed '/^$/d') | head -20 >&2 || true
    FAILED=1
  fi
}
compare "row counts ($(wc -l <"$BACKUP/row-counts.tsv") tables, $(manifest_value "$BACKUP" total_rows) rows)" \
  "$BACKUP/row-counts.tsv" "$(psql_ro "$TARGET" "$COUNT_ROWS_SQL")"
compare "content fingerprints (every row of every table)" \
  "$BACKUP/content-fingerprints.tsv" "$(psql_ro "$TARGET" "$CONTENT_FINGERPRINT_SQL")"
compare "schema summary" "$BACKUP/schema-summary.tsv" "$(psql_ro "$TARGET" "$SCHEMA_SUMMARY_SQL")"
compare "applied migrations ($(wc -l <"$BACKUP/migrations.tsv"))" \
  "$BACKUP/migrations.tsv" "$(psql_ro "$TARGET" "$MIGRATIONS_SQL")"

if ((DJANGO_CHECK)); then
  PYTHON="$(python_for_django)"
  if (cd "$REPO_ROOT/backend" && POSTGRES_DB="$TARGET" "$PYTHON" manage.py check --database default) >&2; then
    log "OK   manage.py check --database default"
  else
    log "FAIL manage.py check --database default"
    FAILED=1
  fi
  # Informational: what this checkout would still apply. Read-only.
  PENDING="$(cd "$REPO_ROOT/backend" && POSTGRES_DB="$TARGET" "$PYTHON" manage.py migrate --plan 2>/dev/null |
    grep -cE '^ *[a-z_]+\.[0-9]{4}_' || true)"
  log "INFO this checkout has $PENDING migration(s) not yet applied to the restored copy"
fi

((FAILED == 0)) || die "restore validation FAILED; $TARGET kept for inspection"
echo "RESTORED=$TARGET"
