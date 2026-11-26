#!/usr/bin/env bash
# Run Django migrations only after a verified backup of the same database.
#
#   ops/db/migrate-with-backup.sh [--database NAME] [--root DIR] [-- extra migrate arguments]
#
# The database defaults to POSTGRES_DB (environment or the checkout's .env).
# 1. backup.sh takes a verified backup labelled "pre-migrate" (retention keeps these
#    for 30 days). If the backup fails for any reason, nothing is migrated.
# 2. `manage.py migrate --noinput` runs against that database with any extra arguments.
# The backup path is printed so a failed migration can be investigated or the
# database restored into a new one with restore.sh.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

DATABASE="" ROOT="$BACKUP_ROOT_DEFAULT" EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
  --database) DATABASE="${2:-}" && shift 2 ;;
  --root) ROOT="${2:-}" && shift 2 ;;
  --) shift && EXTRA=("$@") && break ;;
  -h | --help) usage 0 ;;
  *) usage ;;
  esac
done

load_connection_env
DATABASE="${DATABASE:-${POSTGRES_DB:-}}"
[[ -n "$DATABASE" ]] || refuse "no database given and POSTGRES_DB is not set"
valid_database_name "$DATABASE" || refuse "'$DATABASE' is not a valid database name"

log "step 1/2: verified backup of $DATABASE before migrating"
if ! OUTPUT="$("$OPS_DB_DIR/backup.sh" --database "$DATABASE" --root "$ROOT" --label pre-migrate)"; then
  die "backup failed; NOT migrating $DATABASE"
fi
BACKUP="$(sed -n 's/^BACKUP=//p' <<<"$OUTPUT")"
[[ -n "$BACKUP" && -f "$BACKUP/SHA256SUMS" ]] || die "backup produced no result; NOT migrating $DATABASE"
log "backup: $BACKUP"

# The backup went through libpq (PG*). Prove Django would migrate that same
# database on that same server before letting it write anything.
EXPECTED="$(psql_ro "$DATABASE" "$IDENTITY_SQL")" || die "cannot read the identity of $DATABASE; NOT migrating"
ACTUAL="$(django_identity "$DATABASE" || true)"
[[ -n "$ACTUAL" ]] || die "Django could not connect to $DATABASE; NOT migrating. Backup: $BACKUP"
[[ "$ACTUAL" == "$EXPECTED" ]] ||
  refuse "Django would migrate '$ACTUAL' but the backup came from '$EXPECTED'; NOT migrating. Backup: $BACKUP"
log "target confirmed: Django and the backup both reach $EXPECTED"
log "step 2/2: manage.py migrate on $DATABASE"
PYTHON="$(python_for_django)"
if ! (cd "$REPO_ROOT/backend" && POSTGRES_DB="$DATABASE" "$PYTHON" manage.py migrate --noinput "${EXTRA[@]}"); then
  die "migrate failed on $DATABASE. The pre-migration backup is $BACKUP; restore it into a new database with ops/db/restore.sh"
fi
log "migrated $DATABASE; pre-migration backup: $BACKUP"
echo "BACKUP=$BACKUP"
