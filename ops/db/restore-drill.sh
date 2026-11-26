#!/usr/bin/env bash
# Restore drill: prove that a backup can be restored exactly, end to end.
#
#   ops/db/restore-drill.sh [--source charityos_acceptance] [--root DIR] [--migrate] [--keep]
#
# 1. backup.sh takes a read-only backup of the source. Only approved throwaway
#    databases may be drilled (currently: charityos_acceptance).
# 2. restore.sh restores it into a new charityos_restore_drill_<stamp>_<random> database
#    and checks checksums, row counts, schema summary, migrations and manage.py check.
# 3. With --migrate, the copy is migrated with this checkout's migrations, forward,
#    back to the backup's recorded state and forward again. Every table from the backup
#    must keep its exact row count at each step, and after the backward step the copy
#    must match the backup's tables, applied migrations and the content fingerprint of
#    every data table (every row byte for byte) exactly. Django's own
#    bookkeeping tables (auth_permission, django_content_type, django_migrations) are
#    reported, not required to match: migrate adds rows to them by design.
# 4. The drill database is dropped at the end unless --keep, and only after proving it
#    is the one this run created (its name prefix plus a random token in its COMMENT).
# Everything printed is also written to <root>/drill-reports/<stamp>_<source>.txt.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

APPROVED_SOURCES=(charityos_acceptance)
BOOKKEEPING='^public\.(auth_permission|django_content_type|django_migrations)\t'

usage() {
  sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

SOURCE="charityos_acceptance" ROOT="$BACKUP_ROOT_DEFAULT" MIGRATE=0 KEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
  --source) SOURCE="${2:-}" && shift 2 ;;
  --root) ROOT="${2:-}" && shift 2 ;;
  --migrate) MIGRATE=1 && shift ;;
  --keep) KEEP=1 && shift ;;
  -h | --help) usage 0 ;;
  *) usage ;;
  esac
done

approved=0
for name in "${APPROVED_SOURCES[@]}"; do [[ "$SOURCE" == "$name" ]] && approved=1; done
((approved)) || refuse "'$SOURCE' is not approved for restore drills (approved: ${APPROVED_SOURCES[*]})"
assert_outside_repositories "$ROOT"
require_tools psql pg_dump pg_restore sha256sum python3 od
load_connection_env

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TOKEN="$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')"
TARGET="charityos_restore_drill_${STAMP,,}_${TOKEN:0:6}"
mkdir -p "$ROOT/drill-reports" && chmod 700 "$ROOT" "$ROOT/drill-reports"
REPORT="$ROOT/drill-reports/${STAMP}_${SOURCE}.txt"
[[ ! -e "$REPORT" ]] || refuse "$REPORT already exists"
exec > >(tee -a "$REPORT") 2>&1

drop_if_ours() {
  database_exists "$TARGET" || return 0
  local comment
  comment="$(psql_ro postgres "SELECT coalesce(shobj_description(oid, 'pg_database'), '')
    FROM pg_database WHERE datname = '$TARGET'")"
  if [[ "$TARGET" != charityos_restore_drill_* || "$comment" != *"owner-token=$TOKEN"* ]]; then
    log "NOT dropping $TARGET: this run cannot prove it created it"
    return 0
  fi
  psql_admin "DROP DATABASE \"$TARGET\""
  log "dropped $TARGET (created by this drill)"
}
finish() {
  local status=$?
  if ((KEEP)); then log "kept $TARGET (--keep)"; else drop_if_ours || true; fi
  if ((status == 0)); then log "DRILL PASSED"; else log "DRILL FAILED (exit $status)"; fi
  log "report: $REPORT"
}
trap finish EXIT

log "restore drill of $SOURCE into $TARGET"
log "tools: $(pg_dump --version); $(pg_restore --version); server $(psql_ro postgres 'SHOW server_version')"
# --no-prune: a drill must never delete earlier backups, including other drills'
# evidence. Retention never deletes "drill" backups either (retention.py).
BACKUP="$("$OPS_DB_DIR/backup.sh" --database "$SOURCE" --root "$ROOT" --label drill --no-prune | sed -n 's/^BACKUP=//p')"
[[ -n "$BACKUP" ]] || die "backup failed"
log "backup: $BACKUP"
log "manifest: tables=$(manifest_value "$BACKUP" tables) rows=$(manifest_value "$BACKUP" total_rows) dump_sha256=$(manifest_value "$BACKUP" dump_sha256)"
"$OPS_DB_DIR/restore.sh" --backup "$BACKUP" --target "$TARGET" --owner-token "$TOKEN" >/dev/null

((MIGRATE)) || exit 0

PYTHON="$(python_for_django)"
manage() { (cd "$REPO_ROOT/backend" && POSTGRES_DB="$TARGET" "$PYTHON" manage.py "$@"); }
counts() { psql_ro "$TARGET" "$COUNT_ROWS_SQL"; }

# Every table in the backup must still exist with the same row count.
check_backup_tables_unchanged() {
  local step="$1" problems
  problems="$(awk -F'\t' 'NR == FNR { now[$1] = $2; next }
    !($1 in now) { print "missing " $1; next }
    now[$1] != $2 { print $1 ": " $2 " -> " now[$1] }' \
    <(counts | grep -vP "$BOOKKEEPING") <(grep -vP "$BOOKKEEPING" "$BACKUP/row-counts.tsv"))"
  if [[ -z "$problems" ]]; then
    log "OK   $step: all $(grep -cvP "$BOOKKEEPING" "$BACKUP/row-counts.tsv") data tables keep their exact row counts"
  else
    log "FAIL $step: $problems"
    exit 1
  fi
  log "INFO $step: bookkeeping rows: $(counts | grep -P "$BOOKKEEPING" | tr '\t\n' '= ')"
}

log "migrating the copy forward with this checkout ($(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown))"
manage migrate --noinput >/dev/null
log "applied: $(comm -13 "$BACKUP/migrations.tsv" <(psql_ro "$TARGET" "$MIGRATIONS_SQL") | tr '\t\n' '. ')"
check_backup_tables_unchanged "forward"
manage migrate --check >/dev/null && log "OK   forward: no migrations left unapplied"

log "migrating the copy back to the backup's recorded state"
while IFS= read -r app; do
  leaf="$(awk -F'\t' -v app="$app" '$1 == app { name = $2 } END { print name }' "$BACKUP/migrations.tsv")"
  manage migrate --noinput "$app" "${leaf:-zero}" >/dev/null
  log "     $app -> ${leaf:-zero}"
done < <(comm -13 "$BACKUP/migrations.tsv" <(psql_ro "$TARGET" "$MIGRATIONS_SQL") | cut -f1 | sort -u)
if diff -q "$BACKUP/migrations.tsv" <(psql_ro "$TARGET" "$MIGRATIONS_SQL") >/dev/null; then
  log "OK   backward: applied migrations equal the backup's $(wc -l <"$BACKUP/migrations.tsv")"
else
  log "FAIL backward: applied migrations differ from the backup"
  diff "$BACKUP/migrations.tsv" <(psql_ro "$TARGET" "$MIGRATIONS_SQL") >&2 || true
  exit 1
fi
check_backup_tables_unchanged "backward"
if diff -q <(grep -vP "$BOOKKEEPING" "$BACKUP/row-counts.tsv" | cut -f1) \
  <(counts | grep -vP "$BOOKKEEPING" | cut -f1) >/dev/null; then
  log "OK   backward: the table list equals the backup's (new tables removed)"
else
  log "FAIL backward: table list differs from the backup"
  exit 1
fi

changed="$(awk -F'\t' 'NR == FNR { now[$1] = $2; next } now[$1] != $2 { print $1 }' \
  <(psql_ro "$TARGET" "$CONTENT_FINGERPRINT_SQL" | grep -vP "$BOOKKEEPING") \
  <(grep -vP "$BOOKKEEPING" "$BACKUP/content-fingerprints.tsv"))"
if [[ -z "$changed" ]]; then
  log "OK   backward: every row of every data table is identical to the backup"
else
  log "FAIL backward: content differs from the backup in: $changed"
  exit 1
fi

log "migrating forward again"
manage migrate --noinput >/dev/null
check_backup_tables_unchanged "forward again"
