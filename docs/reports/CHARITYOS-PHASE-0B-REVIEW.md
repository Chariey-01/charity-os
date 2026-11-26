# CharityOS — Phase 0B review and acceptance

**Decision: Phase 0B is accepted.**
- No Critical or High findings.
- Gate 0A dependencies R1 and R2 have evidence.
- One Medium integrity finding was fixed during the review (`df16ea7`).
- Phase 0C may proceed from this branch.

Reviewed on 26 Nov 2026, 17:34–18:00 EAT.

## 1. Verified starting state

| Check | Result |
|---|---|
| Worktree | `/home/user/Progress_tracker-data-safety` on `feature/data-integrity`, HEAD `16acce96bac77cd15628d1de94aaf74ad443194f`. Clean apart from its `frontend/node_modules` symlink. All 0B work is committed. |
| Ancestry | `1ceba99` (base), `742fa6d` (Gate 0A sign-off) and `2cbf3a9` (Gate 0A follow-up) are all ancestors of `16acce9` |
| Other checkouts | Main checkout `/home/user/Progress_tracker`: `feature/mobile-scheduler` `b9b0b5e`, clean, not touched. QA clone: `phase-0bc` `6cce451`, clean, not touched. Parked `feature/project-domain` worktree: unchanged. |
| Sessions and processes | No other session was active and no test or server process was running |

## 2. Review by requirement

| Area | Verdict | Evidence |
|---|---|---|
| Roadmap integrity | Pass | Validated in the API serializer through the service functions `lock_roadmap` and `validate_parent`. Every invalid tree change answers 400, never 500. Concurrent opposite moves give exactly one 200. |
| Focus-session concurrency | Pass | `select_for_update` on every session write. Versions are numeric, and a stale write answers 409. PATCH requires the current version. A two-thread race gives one 200 and one 409. |
| Completed-session integrity (the earlier issue) | **Resolved** | PATCH of category, task, roadmap item or deep-work answers `use_correction` in every state. Corrections are audited (before and after) and update the linked entry in the same transaction; Insights moves the minutes once. A linked entry cannot switch category alone. Policy: an ended session's words (notes, outcome, learning) are editable with a version check; its times and attribution change only through an audited correction; nothing else changes. |
| Duplicate operations | Pass | Every database constraint is validated, giving a 400 field error. A race answers 409. Daily totals update the day. Sessions and schedule entries are idempotent by client id. |
| Add to Today | Pass | One transaction. A repeated request returns the same task and plan item. Failures roll back every write. History is kept: carry-over, not deletion. It creates plan items, never schedule entries. |
| Transaction rollback | Pass | Tested with injected failures in corrections and Add to Today, and with the race backstop. |
| History consistency | Pass | `check_data_integrity` is clean on a migrated real-shaped copy, and the Gate 0A `RESTRICT` and archive suites pass. |

## 3. Tests demonstrate the previous failures

The 8 Phase 0B test files from `16acce9` were run against the code **before** Phase 0B: an export of `742fa6d` (Gate 0A), in its own throwaway test database. For the duplicates file only, the import of the new `api.constraints` module was stubbed.

| File (pre-fix code) | Result |
|---|---|
| `test_roadmap_integrity.py` | 5 failed, 1 passed (control: another user's parent was already refused). **`test_cycles_already_in_old_data_are_contained` never finished:** starting a session on a node in a cycle looped in `_ancestry`. The process reached 716 MB and was stopped after 10 minutes. This is exactly the audit's prediction. |
| `test_session_versions.py` | 7 failed, 1 passed (control) |
| `test_session_patch.py` | 4 failed, 2 passed (controls) |
| `test_session_corrections.py` | 9 failed, 3 passed (controls) |
| `test_linked_entry_attribution.py` | 1 failed |
| `test_duplicate_operations.py` | 10 failed. The server log shows HTTP 500s for areas, daily reflections, water, nutrition and plan items. |
| `test_add_to_today.py` | 8 failed (the endpoint did not exist) |
| `test_data_integrity_command.py` | 4 failed (the command did not exist) |

Two failures in the duplicates file don't demonstrate behaviour: the race test's patched helper, and the message guard's stubbed table, did not exist before Phase 0B. Every other failure is the old behaviour. The leftover test database from the stopped run was removed by the next run in the same export.

## 4. Test commands and results on `16acce9`

Run from `backend/` with the project virtual environment. The test database is the worktree's own `test_charityos_<hash>`.

| Command | Result |
|---|---|
| `pytest -q` | `371 passed` |
| `pytest -q tests/test_roadmap_integrity.py tests/test_session_versions.py tests/test_session_patch.py tests/test_session_corrections.py tests/test_linked_entry_attribution.py tests/test_duplicate_operations.py tests/test_add_to_today.py tests/test_data_integrity_command.py` | `56 passed` |
| `pytest -q tests/test_ops_migrate.py -rA` (R1) | 8/8 passed (listed in section 5) |
| `pytest -q tests/test_archive_api.py tests/test_archive_records_api.py -k "archived_at or name_now_taken or archive_not_delete"` (R2) | `16 passed` |
| `cd frontend && npx vitest run` | `Tests 53 passed` |
| After `df16ea7`: `pytest -q tests/test_session_patch.py tests/test_mvp_api.py tests/test_acceptance_flow.py tests/test_schedule_entries.py` | `71 passed` |

The Gate 0B QA outputs from 26 Nov 11:28 (restore drill, integrity check, audit probes, static checks) are in `~/charityos-qa-evidence/20261126_phase-0b_7e893a0/`.

## 5. Gate 0A dependencies

**R1, backup and migration connection safety.** Implemented in `7c48f59` (the reviewed QA fixes `270e169` + `6cce451`, never `270e169` alone) and `37e0efe`. Each requirement has a passing test:

| Requirement | Test |
|---|---|
| Explicit `--database` | `test_the_database_must_be_named_explicitly` |
| `DATABASE_URL` refused | `test_database_url_is_refused_before_anything_runs` |
| Django and backup settings aligned | `test_backup_and_migrate_always_reach_the_same_server`, `test_a_different_postgres_port_cannot_split_backup_and_migrate` |
| Identity checked before migration | `test_postgres_db_naming_another_database_does_not_redirect_the_migration` |
| Fail-closed on a mismatch | `test_migration_is_refused_when_django_reaches_another_database` (migrate is never invoked) |
| A failed backup prevents migration | `test_migrations_never_run_when_the_backup_fails` |

It was also exercised on a real restored copy (Gate 0A sign-off, section 3).

**R2, archive and restore integrity.** Resolved at Gate 0A. PATCH or POST containing `archived_at` answers 400 and changes nothing. Restoring into a now-taken active name answers 409 `restore_conflict`. Covered by `test_archived_at_cannot_be_written_directly` (×3), `test_archive_not_delete` (×12) and `test_restoring_into_a_name_now_taken_is_a_conflict`. Probed again today: 400/400/400, still archived, 409.

**Gate 0A is closed** (see `CHARITYOS-GATE-0A-FINAL-SIGNOFF.md` and its addendum).

## 6. Findings

| Severity | Finding | Action |
|---|---|---|
| Critical | none | — |
| High | none | — |
| Medium | The generic `POST /sessions` create route still existed. It failed today, with a misleading 400, but it was a second way to create session history. | **Fixed: `df16ea7`.** It answers 405 `use_start`. Tested. |
| Medium | Generic creates without a natural key (tasks, evidence, accomplishments, meal logs) create a second row if the client resends. Sessions and schedule entries are already idempotent by client id. The bundled client does not retry automatically. | Not in 0B scope. Recommendation: client-generated ids for those creates, as entries and sessions use. |
| Medium (0C scope) | No login throttling or login CSRF; unbounded metrics range; evidence URL rules skipped on PATCH; duplicate reflections and no revision history. | Phase 0C, S8–S11 |
| Low | Cycle prevention is application-level, with no database trigger. `seed_personal_roadmaps` builds fresh trees directly through the ORM. | Legacy data is covered by `check_data_integrity`; the seeds create acyclic trees. |
| Low | API errors still come in two shapes (DRF field errors and the domain envelope). | Not in the authorized 0C list (S8–S12). Recorded for later. |
| Low | A running session's attribution cannot change: finish it, then correct it. | By design, documented. |

## 7. Branch for Phase 0C

Phase 0C starts from `feature/data-integrity` at the commit that adds this review. It goes on a new branch, `feature/security-hardening`, in the same durable worktree. `feature/data-integrity` stays as reviewed.
