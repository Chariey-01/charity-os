# CharityOS — Gate 0A final sign-off

**Decision: Gate 0A is closed. It passed.** The one defect found in review, a backup/migration target mismatch in `ops/db/migrate-with-backup.sh`, is fixed on `feature/data-safety` and verified below. Phase 0B starts from this commit.

| | |
|---|---|
| Base | `1ceba9929afb3ec4f47dd96756c4425c6f2dd484` (main + task-status workflow) |
| Gate 0A as first reported | `5a80dd296aacc55f260cf254dea8ab20a7ab9a6d` (15 commits) |
| Corrections after review | `7c48f59` (wrapper proves its target, from QA `270e169` + `6cce451`), `37e0efe` (explicit `--database`) |
| Final Gate 0A code | `37e0efe5e469bc6758c30f92ad01623c05b4a5aa` |
| Sign-off | the commit that adds this file, on `feature/data-safety` |
| Verified | 26 Nov 2026, 10:40–10:50 EAT, PostgreSQL 16.15 (cluster on 5433), Python 3.12.3, Node 24 |

Not done, as instructed:
- no push, merge, deploy or timer install;
- no migration of `charityos`.

## 1. Branches, worktrees and sessions

- **`feature/data-safety`**: in the durable worktree `/home/user/Progress_tracker-data-safety`. Clean apart from its `frontend/node_modules` symlink.
- **Main checkout**: `feature/mobile-scheduler` at `b9b0b5e`, clean.
- **Other refs**: all unchanged since 25 Nov, including `main` `4ad209d`, `backup/mobile-scheduler-pre-split` `6df1a35` and the parked `feature/project-domain` `7b1d03e`. Its uncommitted worktree in `/tmp` is byte-identical to the preserved copy.
- **`charityos`**: still at the pre-Phase-0 schema. It has 34 applied migrations, with `planning` at `0006`, and the last one ran on 24 Nov at 16:37 EAT. It has 0 users. It was only ever read.
- **Sessions**:
  - **QA session `progress-tracker-30`** (overnight clone `~/charityos-overnight-qa`): stood down at 10:3x EAT on the owner's instruction. It reported a clean tree and a stopped rehearsal cluster on 5434, and said it changed nothing in the owner repo or the 5433 databases. Its 18 refs are preserved in `~/charityos-work-preservation/20261126T103704+0300_overnight-qa-clone/`, as a verified bundle; the clone is untouched.
  - **`progress-tracker-ae`**: read-only. It plans to verify this evidence independently (section 5).
  - **`ef` and `4f`**: idle since 25 Nov.

## 2. QA-session reconciliation

`qa/release-candidate` is `5a80dd2` plus 11 commits; `phase-0bc` adds `6cce451`.

| QA commit | What it is | Relevant now? | Decision |
|---|---|---|---|
| `270e169`, `6cce451` | Wrapper backs up and migrates the same server; proves Django's target | **Yes, Gate 0A defect** | **Integrated** as `7c48f59`, code and tests only. Correct, compatible and safe (section 3). |
| `6cfdef4` | Add to Today appends after the plan's last item | Phase 0B (B4) | Superseded: B4 moves Add to Today into one server transaction that picks the position itself. |
| `af0d36c` | Service worker never caches an error page over the offline shell | Beta, not 0B | Hold. A sound, self-contained frontend fix with tests; integrate when PWA/beta work is approved. |
| `066da59` | Return to sign-in when the session ends | Beta, not 0B | Hold, as above. |
| `5f3d821`, `1b4300a`, `987974e` | One-origin production serving, `DATABASE_URL`, container image, beta runbook | Deployment | **Hold.** Deployment is not approved, and `5f3d821` adds `DATABASE_URL`. The ops scripts now refuse to run while it is set, so the two are already reconciled. |
| `6cc2c2b`, `3e73fda`, `6d7afa5`, `ad3b335` | Browser QA harness and evidence, independent Gate 0A check, 0B/0C plan, morning report | Reference | Kept in the QA clone. The 0B/0C plan was read as input to Phase 0B. |

**QA finding R2 was not reproduced.** It claimed `archived_at` was still writable by PATCH, giving a 500 on restore-by-PATCH. On `5a80dd2`:
- PATCH `{"archived_at": null}`, a date, or alongside other fields answers 400 with a field error, and the record stays archived;
- POST with `archived_at` answers 400;
- `/restore` into a name that is now taken answers 409 `restore_conflict`.

Covered permanently by `test_archived_at_cannot_be_written_directly` and `test_archive_not_delete`.

## 3. Review of commit `270e169` (and `6cce451`)

**The defect is real.** The ops scripts took the server from `PG*` for `pg_dump` and `psql`, while `manage.py` read `POSTGRES_*`, falling back to `.env` or `localhost:5432`. When the two disagreed, the wrapper could verify a backup of one server and migrate a same-named database on another.

**`270e169` alone was incomplete.** Aligning the environment variables still trusted them. `6cce451` adds a check of where Django actually connects.

| Requirement | How it is met | Test |
|---|---|---|
| Backup and migration use the same resolved connection | `load_connection_env` exports the resolved `PG*` host, port, user and password as `POSTGRES_*` | `test_backup_and_migrate_always_reach_the_same_server` (conflicting host) |
| Host, port, database and settings cannot silently diverge | Before Django writes, the wrapper compares the database name, OID and server start time, read through both libpq and Django | `test_a_different_postgres_port_cannot_split_backup_and_migrate`, `test_postgres_db_naming_another_database_does_not_redirect_the_migration`, `test_migration_is_refused_when_django_reaches_another_database` |
| Backup failure prevents migration | `backup.sh` must succeed and produce a verified folder | `test_migrations_never_run_when_the_backup_fails` |
| Verification failure prevents migration | `backup.sh` dies on any checksum or table-list mismatch; an identity mismatch or a Django connection failure refuses | Identity tests above |
| Unsafe targets refused | Each of these is refused: invalid name, a database that is missing or not a CharityOS one, `DATABASE_URL` set, **and, new in `37e0efe`, no `--database`**. Without it, a bare run would have migrated whatever `.env` names, the personal `charityos` | `test_database_url_is_refused_before_anything_runs`, `test_the_database_must_be_named_explicitly` |

- **Mutation checks** (on this branch, files restored byte-identically afterwards): removing the alignment, the identity comparison or the `DATABASE_URL` refusal each makes its test fail.
- **Run against a real copy of `charityos_acceptance`**: the copy was restored into a drill database.
  - The wrapper backed it up, confirmed `Django and the backup both reach <db>|340062|…`, and applied all 13 migrations (34 → 47).
  - Re-run with `PGPORT=5433` but `POSTGRES_PORT=5434`, it reached the same confirmed database.
  - Run without `--database`, it refused.
  - The drill database was then dropped after its owner and token were checked.

## 4. Gate 0A checks on `37e0efe` (actual results)

| Check | Result |
|---|---|
| Ruff lint and format | `All checks passed!`, `99 files already formatted` |
| `makemigrations --check --dry-run` | `No changes detected` |
| `manage.py check`, `check --deploy` (production settings) | `System check identified no issues (1 silenced).` |
| Gate 0A test groups (13 files: ops, test database, archive, migrations, restrict, admin, erasure) | `135 passed` |
| Full backend suite | `312 passed`, 0 skipped |
| Frontend | lint clean, typecheck clean, `Tests 52 passed (52)`, production build OK |
| Restore drill with `--migrate` | `DRILL PASSED`: 35 tables and 499 rows, with every check matching (checksums, row counts, the fingerprint of every row, schema, migrations, `manage.py check`). All 13 migrations went forward, back with every row identical, and forward again. The drill database was dropped. |
| Wrapper on a real copy | Section 3 |
| Test-database isolation | Two checkouts ran at the same time in `test_charityos_f794a3f543` and `test_charityos_a587c0a981`, 48/48 each. The database list and OIDs were identical before and after. |
| Archive and restore | `test_archive_api`, `test_archive_records_api` and `test_plan_history_api` pass, covering 15 resources, Today, next actions, progress and Insights |
| History preserved | `test_history_restrict` passes: every non-user link is `RESTRICT` and old-shape data round-trips. Insights and metrics output is identical after archiving. |
| User erasure | `test_erase_user` passes: dry run, wrong confirmation, cross-user refusal, rollback on plan mismatch. On 25 Nov a migrated real-shaped copy erased exactly its 287 planned rows, and the source database was unchanged. |

## 5. Evidence locations

- **Backups:** `~/charityos-backups/charityos_acceptance/`. The closing drill's backup is `20261126T074526Z_drill`, dump sha256 `9ae8cd50…4b15c4`.
- **Drill reports:** `~/charityos-backups/drill-reports/`. The closing drill is `20261126T074526Z_charityos_acceptance.txt`.
- **Tests:** `cd backend && pytest`. The test database is `test_charityos_<hash of the checkout path>`; set `CHARITYOS_TEST_DB=test_<name>` to choose one.
- **Off-machine:** `~/charityos-offsite/20261125T234735+0300/`, encrypted, holding the refs up to `5a80dd2`. The key is kept separately in `~/.config/charityos-keys/`. A refreshed package including this sign-off should be made at the 0B gate.

## 6. Known limitations and remaining risks

- **CI has never run on this work, because nothing is pushed.** In CI, the backup and restore round-trip tests skip by design: the PostgreSQL 16 client tools are older than CI's Postgres 17 service. The refusal tests still run.
- **There is no point-in-time recovery.** The recovery point is the last backup, and the nightly timer is designed but not installed.
- **`charityos` itself has never been backed up or drilled.** Only `charityos_acceptance` is approved for that.
- **Phase 0B scope:**
  - roadmap cycles;
  - focus-session concurrency and attribution;
  - duplicate-create 500s;
  - non-atomic Add to Today.
- **Phase 0C scope:**
  - login throttling;
  - login CSRF;
  - security logging;
  - the unbounded metrics range;
  - evidence URL validation on PATCH;
  - reflection duplicate handling and revision protection.

## Addendum: independent verification and two follow-up fixes (26 Nov, after sign-off)

**Independent verification.** Session `progress-tracker-ae` re-verified Gate 0A from its own export of `742fa6d`, without using this worktree. It reproduced:
- 312 backend tests passing, in its own `test_charityos_9ea67f29fe`, with the 13 gate files collecting 135 tests;
- clean ruff, `makemigrations`, `check` and `check --deploy`;
- the frontend: 52/52 tests, lint, typecheck and build;
- a restore of `20261126T074605Z_drill`, with checksums, rows, fingerprints, schema, migrations and `manage.py check` all OK;
- the migration round trip on its copy (forward 13, back with every row identical, forward again);
- `charityos` unchanged.

It raised four findings:

1. **An evidence backup was pruned.** The backup cited in section 5, `20261126T074526Z_drill`, was deleted 38 seconds later by retention during the next drill, because retention kept only the newest backup per day. Its drill report still exists. **Fixed:** retention never deletes `drill` backups, and `restore-drill.sh` passes `--no-prune`. Tested and mutation-checked. The surviving `20261126T074605Z_drill` is what the independent restore used.
2. **The test-database guard protected only `test_charityos`.** `CHARITYOS_TEST_DB=test_charityos_p2` would have let pytest-django drop that protected database. **Fixed:** overrides may not use the reserved `test_charityos*` prefix. Tested with `test_charityos_p2` and another checkout's automatic name.
3. **The "off-machine" package is still on the same disk** as the repository and backups. Correct: moving it needs a medium only the owner has. This is still an open action for the owner.
4. **It questioned starting 0B.** The owner approved Phase 0B directly to session b0 on 26 Nov, so no change is needed.

**Left for the owner.** `progress-tracker-ae`'s own restore database, `charityos_restore_drill_ae_20261126t075039z`, still exists: the safety check blocked its drop. It was not created by this branch's drill, so it is not dropped here.

**Final Gate 0A code** is the follow-up commit that carries this addendum. Phase 0B merges it in.
