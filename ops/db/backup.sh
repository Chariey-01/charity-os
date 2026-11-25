#!/usr/bin/env bash
# Take a verified, checksummed PostgreSQL backup of one CharityOS database.
#
#   ops/db/backup.sh --database NAME [--root DIR] [--label LABEL] [--no-prune]
#
# Writes <root>/<database>/<UTC stamp>_<label>/ containing:
#   database.dump      pg_dump custom-format archive
#   MANIFEST           versions, sizes, checksums and totals
#   row-counts.tsv     exact rows per table, counted inside the dump's own snapshot
#   content-fingerprints.tsv  order-independent hash of every table's rows, same snapshot
#   schema-summary.tsv tables, indexes, sequences, views and constraints in public
#   migrations.tsv     applied Django migrations
#   SHA256SUMS         checksums of every file above
# The directory is made read-only. An existing backup is never overwritten.
# After a successful backup, retention (ops/db/retention.py) prunes older ones
# unless --no-prune is given. Default root: $CHARITYOS_BACKUP_ROOT or ~/charityos-backups.
# The last line of output is BACKUP=<path>.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

DATABASE="" ROOT="$BACKUP_ROOT_DEFAULT" LABEL="manual" PRUNE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
  --database) DATABASE="${2:-}" && shift 2 ;;
  --root) ROOT="${2:-}" && shift 2 ;;
  --label) LABEL="${2:-}" && shift 2 ;;
  --no-prune) PRUNE=0 && shift ;;
  -h | --help) usage 0 ;;
  *) usage ;;
  esac
done

# --- Checks that need no database connection -----------------------------------
[[ -n "$DATABASE" ]] || usage
valid_database_name "$DATABASE" || refuse "'$DATABASE' is not a valid database name"
[[ "$LABEL" =~ ^[a-z0-9-]{1,20}$ ]] || refuse "label must be 1-20 of [a-z0-9-]"
[[ -n "$ROOT" ]] || refuse "empty backup root"
assert_outside_repositories "$ROOT"
require_tools psql pg_dump pg_restore sha256sum python3 realpath
load_connection_env

# --- Checks against the server (all read-only) ---------------------------------
database_exists "$DATABASE" || refuse "database '$DATABASE' does not exist"
[[ "$(psql_ro "$DATABASE" "SELECT to_regclass('public.django_migrations') IS NOT NULL
  AND to_regclass('public.users_user') IS NOT NULL")" == t ]] ||
  refuse "'$DATABASE' is not a CharityOS database (no django_migrations/users_user)"
SERVER_MAJOR="$(server_major "$DATABASE")"
SERVER_VERSION="$(psql_ro "$DATABASE" "SHOW server_version")"
DUMP_MAJOR="$(tool_major pg_dump)"
((DUMP_MAJOR >= SERVER_MAJOR)) ||
  refuse "pg_dump $DUMP_MAJOR cannot dump a PostgreSQL $SERVER_MAJOR server; install client $SERVER_MAJOR or newer"

mkdir -p "$ROOT/$DATABASE"
chmod 700 "$ROOT" "$ROOT/$DATABASE"
ROOT="$(realpath "$ROOT")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${STAMP}_${LABEL}"
FINAL="$ROOT/$DATABASE/$NAME"
PARTIAL="$ROOT/$DATABASE/.$NAME.partial"
[[ ! -e "$FINAL" && ! -e "$PARTIAL" ]] || refuse "$FINAL already exists; backups are never overwritten"
mkdir "$PARTIAL"
cleanup_partial() { [[ -d "$PARTIAL" ]] && chmod -R u+w "$PARTIAL" && rm -rf -- "$PARTIAL"; }
trap 'cleanup_partial' EXIT

# --- Dump and counts from one snapshot -------------------------------------------
# A read-only REPEATABLE READ transaction exports its snapshot; pg_dump reads that
# snapshot and the same transaction counts every table, so the manifest describes
# exactly what is in the dump even while the database is in use.
coproc SNAPSHOT_SESSION {
  PGOPTIONS="$READ_ONLY_PGOPTIONS" psql -X -q -At -v ON_ERROR_STOP=1 -d "$DATABASE" 2>&1
}
send() { printf '%s\n' "$1" >&"${SNAPSHOT_SESSION[1]}"; }
receive_until() {
  local line
  while IFS= read -r -t 600 line <&"${SNAPSHOT_SESSION[0]}"; do
    [[ "$line" == "$1" ]] && return 0
    printf '%s\n' "$line"
  done
  die "the snapshot session ended unexpectedly"
}
send "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;"
send "SELECT pg_export_snapshot();"
send "SELECT '__SNAPSHOT__';"
SNAPSHOT="$(receive_until __SNAPSHOT__)"
[[ "$SNAPSHOT" =~ ^[0-9A-F]+-[0-9A-F]+-[0-9]+$ ]] || die "unexpected snapshot reply: $SNAPSHOT"

log "dumping $DATABASE (snapshot $SNAPSHOT)"
pg_dump --snapshot="$SNAPSHOT" --format=custom --file="$PARTIAL/database.dump" --dbname="$DATABASE"

send "$COUNT_ROWS_SQL"
send "SELECT '__COUNTS__';"
receive_until __COUNTS__ >"$PARTIAL/row-counts.tsv"
send "$CONTENT_FINGERPRINT_SQL"
send "SELECT '__FINGERPRINTS__';"
receive_until __FINGERPRINTS__ >"$PARTIAL/content-fingerprints.tsv"
send "$SCHEMA_SUMMARY_SQL"
send "SELECT '__SCHEMA__';"
receive_until __SCHEMA__ >"$PARTIAL/schema-summary.tsv"
send "$MIGRATIONS_SQL"
send "SELECT '__MIGRATIONS__';"
receive_until __MIGRATIONS__ >"$PARTIAL/migrations.tsv"
send "COMMIT;"
eval "exec ${SNAPSHOT_SESSION[1]}>&-"
wait "$SNAPSHOT_SESSION_PID" || die "the snapshot session failed"

# --- Verify what was written -------------------------------------------------------
grep -qvP '^[^\t]+\t\d+$' "$PARTIAL/row-counts.tsv" && die "malformed row counts"
grep -qvP '^[^\t]+\t([0-9a-f]{32}|empty)$' "$PARTIAL/content-fingerprints.tsv" && die "malformed fingerprints"
[[ "$(cut -f1 "$PARTIAL/row-counts.tsv")" == "$(cut -f1 "$PARTIAL/content-fingerprints.tsv")" ]] ||
  die "row counts and fingerprints cover different tables"
TABLES="$(wc -l <"$PARTIAL/row-counts.tsv")"
TOTAL_ROWS="$(awk -F'\t' '{s += $2} END {print s + 0}' "$PARTIAL/row-counts.tsv")"
TOC_TABLES="$(pg_restore --list "$PARTIAL/database.dump" | grep -c ' TABLE DATA ' || true)"
[[ "$TOC_TABLES" == "$TABLES" ]] ||
  die "archive lists $TOC_TABLES tables with data, the database has $TABLES"
DUMP_SHA="$(sha256sum "$PARTIAL/database.dump" | cut -d' ' -f1)"

cat >"$PARTIAL/MANIFEST" <<EOF
format_version=$BACKUP_FORMAT_VERSION
database=$DATABASE
label=$LABEL
created_utc=$STAMP
source_host=$PGHOST
source_port=$PGPORT
server_version=$SERVER_VERSION
server_major=$SERVER_MAJOR
pg_dump_version=$(pg_dump --version)
pg_dump_major=$DUMP_MAJOR
dump_file=database.dump
dump_bytes=$(stat -c %s "$PARTIAL/database.dump")
dump_sha256=$DUMP_SHA
tables=$TABLES
total_rows=$TOTAL_ROWS
applied_migrations=$(wc -l <"$PARTIAL/migrations.tsv")
EOF
(cd "$PARTIAL" && sha256sum database.dump MANIFEST row-counts.tsv content-fingerprints.tsv schema-summary.tsv migrations.tsv >SHA256SUMS)
(cd "$PARTIAL" && sha256sum --quiet -c SHA256SUMS) || die "checksum verification failed"
chmod 0400 "$PARTIAL"/*
mv -T -- "$PARTIAL" "$FINAL"
trap - EXIT
chmod 0500 "$FINAL"
log "backup verified: $TABLES tables, $TOTAL_ROWS rows, dump sha256 $DUMP_SHA"

# --- Retention -----------------------------------------------------------------------
if ((PRUNE)); then
  while IFS= read -r old; do
    [[ -n "$old" ]] || continue
    target="$ROOT/$DATABASE/$old"
    # Delete only what is unmistakably one of our backups of this database.
    if [[ -L "$target" || ! -d "$target" || "$target" == "$FINAL" ]] ||
      [[ "$(manifest_value "$target" database 2>/dev/null)" != "$DATABASE" ]] ||
      [[ "$(manifest_value "$target" format_version 2>/dev/null)" != "$BACKUP_FORMAT_VERSION" ]] ||
      [[ ! -f "$target/SHA256SUMS" ]]; then
      log "retention: skipping $old (not a recognisable backup of $DATABASE)"
      continue
    fi
    chmod -R u+w -- "$target" && rm -rf -- "$target"
    log "retention: removed $old"
  done < <(python3 -I "$OPS_DB_DIR/retention.py" "$ROOT/$DATABASE")
fi

echo "BACKUP=$FINAL"
