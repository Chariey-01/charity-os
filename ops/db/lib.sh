# shellcheck shell=bash
# Shared helpers for the CharityOS database scripts. Source this file; do not run it.
#
# Connection settings come from libpq's PG* variables when set, otherwise from
# POSTGRES_* in the environment or the checkout's .env (parsed, never sourced).

set -Eeuo pipefail
umask 077

OPS_DB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$OPS_DB_DIR/../.." && pwd -P)"
BACKUP_ROOT_DEFAULT="${CHARITYOS_BACKUP_ROOT:-$HOME/charityos-backups}"
BACKUP_FORMAT_VERSION=1
# Names that may never be a restore target, even when no such database exists yet.
# Every existing database is refused as a target as well.
PROTECTED_DATABASES=(charityos charityos_acceptance postgres template0 template1)
# Restores land only in databases with this prefix, so a typo can never name a real one.
RESTORE_PREFIX="charityos_restore"

log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}
refuse() {
  printf 'REFUSED: %s\n' "$1" >&2
  exit 2
}

load_connection_env() {
  local env_file="$REPO_ROOT/.env" line key value
  if [[ -f "$env_file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ "$line" =~ ^(POSTGRES_(HOST|PORT|USER|PASSWORD|DB))=(.*)$ ]] || continue
      key="${BASH_REMATCH[1]}"
      value="${BASH_REMATCH[3]}"
      value="${value%\"}" && value="${value#\"}"
      value="${value%\'}" && value="${value#\'}"
      [[ -n "${!key:-}" ]] || export "$key=$value"
    done <"$env_file"
  fi
  export PGHOST="${PGHOST:-${POSTGRES_HOST:-localhost}}"
  export PGPORT="${PGPORT:-${POSTGRES_PORT:-5432}}"
  export PGUSER="${PGUSER:-${POSTGRES_USER:-charityos}}"
  if [[ -z "${PGPASSWORD:-}" && -n "${POSTGRES_PASSWORD:-}" ]]; then
    export PGPASSWORD="$POSTGRES_PASSWORD"
  fi
  # Production settings prefer DATABASE_URL over POSTGRES_*, so with it set a
  # manage.py step could reach a different server than pg_dump. Refuse rather
  # than guess which one was meant.
  if [[ -n "${DATABASE_URL:-}" ]]; then
    refuse "DATABASE_URL is set; ops/db scripts use PG*/POSTGRES_* only. Unset DATABASE_URL and name the server with PGHOST/PGPORT."
  fi
  # Django reads POSTGRES_*, libpq reads PG*. Point both at the one server chosen
  # above, so a backup and the migrate or check that follows it can never reach
  # different servers.
  export POSTGRES_HOST="$PGHOST" POSTGRES_PORT="$PGPORT" POSTGRES_USER="$PGUSER"
  if [[ -n "${PGPASSWORD:-}" ]]; then
    export POSTGRES_PASSWORD="$PGPASSWORD"
  fi
  export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"
}

valid_database_name() { [[ "$1" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; }

is_protected_database() {
  local name="$1" protected
  for protected in "${PROTECTED_DATABASES[@]}"; do
    [[ "$name" == "$protected" ]] && return 0
  done
  [[ "$name" == test_* ]]
}

require_tools() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || die "required tool '$tool' is not installed"
  done
}

# Major version of a PostgreSQL client tool, e.g. 16 for "pg_dump (PostgreSQL) 16.15".
tool_major() { "$1" --version | sed -nE 's/^[^0-9]*([0-9]+)[.].*/\1/p' | head -1; }

# Read-only sessions with fixed output settings, so row text (and therefore the
# content fingerprints) does not depend on the client's timezone or date style.
READ_ONLY_PGOPTIONS='-c default_transaction_read_only=on -c timezone=UTC -c datestyle=ISO,YMD -c intervalstyle=postgres -c extra_float_digits=1'

# Read-only query against one database; names are validated before they get here.
psql_ro() {
  PGOPTIONS="$READ_ONLY_PGOPTIONS" psql -X -q -At -v ON_ERROR_STOP=1 -d "$1" -c "$2"
}

# The only writable connection: CREATE/COMMENT/DROP DATABASE from the maintenance database.
psql_admin() { psql -X -q -At -v ON_ERROR_STOP=1 -d postgres -c "$1"; }

server_major() { echo $(($(psql_ro "$1" "SHOW server_version_num") / 10000)); }

database_exists() {
  [[ "$(psql_ro postgres "SELECT count(*) FROM pg_database WHERE datname = '$1'")" == 1 ]]
}

# Refuse any path inside this checkout or inside any other git work tree.
assert_outside_repositories() {
  local real probe
  real="$(realpath -m -- "$1")"
  case "$real/" in
  "$REPO_ROOT"/*) refuse "$real is inside the repository $REPO_ROOT" ;;
  esac
  probe="$real"
  while [[ ! -d "$probe" ]]; do probe="$(dirname "$probe")"; done
  if git -C "$probe" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    refuse "$real is inside a git work tree ($(git -C "$probe" rev-parse --show-toplevel))"
  fi
}

# Exact row count of every ordinary table, one "schema.table<TAB>count" per line.
read -r -d '' COUNT_ROWS_SQL <<'SQL' || true
SELECT format('%I.%I', n.nspname, c.relname) || E'\t' ||
       (xpath('/row/c/text()',
              query_to_xml(format('SELECT count(*) AS c FROM %I.%I', n.nspname, c.relname),
                           false, true, '')))[1]::text
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\_toast%'
ORDER BY 1;
SQL

# Order-independent fingerprint of every table's content: md5 over the sorted md5s
# of its rows. "empty" for a table without rows.
read -r -d '' CONTENT_FINGERPRINT_SQL <<'SQL' || true
SELECT format('%I.%I', n.nspname, c.relname) || E'\t' ||
       coalesce((xpath('/row/h/text()',
                       query_to_xml(format('SELECT md5(string_agg(md5(t::text), %L ORDER BY md5(t::text))) AS h FROM %I.%I t',
                                           '', n.nspname, c.relname),
                                    false, true, '')))[1]::text, 'empty')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\_toast%'
ORDER BY 1;
SQL

# Object counts in the public schema, used to check a restored schema.
read -r -d '' SCHEMA_SUMMARY_SQL <<'SQL' || true
SELECT kind || E'\t' || total FROM (
  SELECT 1 AS o, 'tables' AS kind, count(*) AS total FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'
  UNION ALL SELECT 2, 'indexes', count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'i'
  UNION ALL SELECT 3, 'sequences', count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'S'
  UNION ALL SELECT 4, 'views', count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'v'
  UNION ALL SELECT 5, 'constraints', count(*) FROM pg_constraint co
    JOIN pg_namespace n ON n.oid = co.connamespace WHERE n.nspname = 'public'
) summary ORDER BY o;
SQL

MIGRATIONS_SQL="SELECT app || E'\t' || name FROM django_migrations ORDER BY app, name;"

# One line that identifies the exact database on the exact running server:
# name, database OID and the server's start time. Two servers never share all
# three, and a restart in between changes it, so equal identities seen through
# libpq and through Django mean both reach the same database.
IDENTITY_SQL="SELECT current_database() || '|' || (SELECT oid FROM pg_database WHERE datname = current_database()) || '|' || extract(epoch FROM pg_postmaster_start_time())::text"

# The identity of the database Django connects to with POSTGRES_DB=$1.
django_identity() {
  local python
  python="$(python_for_django)"
  (cd "$REPO_ROOT/backend" && POSTGRES_DB="$1" "$python" manage.py shell -c \
    "from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"$IDENTITY_SQL\")
    print('IDENTITY=' + cursor.fetchone()[0])" | sed -n 's/^IDENTITY=//p' | tail -1)
}

manifest_value() { sed -n "s/^$2=//p" "$1/MANIFEST" | head -1; }

python_for_django() {
  if [[ -n "${CHARITYOS_PYTHON:-}" ]]; then
    echo "$CHARITYOS_PYTHON"
  elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    echo "$REPO_ROOT/.venv/bin/python"
  else
    echo python3
  fi
}
