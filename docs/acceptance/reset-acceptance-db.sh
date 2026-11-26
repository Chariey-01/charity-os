#!/usr/bin/env bash
# Clears activity data in the throwaway acceptance database ONLY.
# Never point this at a database that holds real records.
set -euo pipefail
DB="${ACCEPT_DB:-charityos_acceptance}"
case "$DB" in *acceptance*) ;; *) echo "Refusing to reset '$DB' (name must contain 'acceptance')." >&2; exit 1 ;; esac
psql -h "${PGHOST:-localhost}" -p "${PGPORT:-5433}" -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
DELETE FROM scheduling_scheduleentry;
DELETE FROM records_evidence;
DELETE FROM execution_sessionpause;
DELETE FROM execution_focussessioncorrection;
DELETE FROM execution_focussession;
DELETE FROM health_exerciselog;
DELETE FROM health_sleeplog;
UPDATE users_user SET timezone = 'Africa/Nairobi';
SQL
echo "acceptance data reset"
