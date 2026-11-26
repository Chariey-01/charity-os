# CharityOS — Phase 0B implementation report

**Status: Phase 0B (B1–B5) is implemented and tested. It stops here for product-owner review.** Phase 0C has not been started. Nothing was pushed, merged, deployed or migrated in `charityos`, and no backup timer was installed.

## 1. Commits and branches

| | |
|---|---|
| Gate 0A base (signed off) | `742fa6d409e94b842d122a590c3e9fc5370d05c2` on `feature/data-safety` |
| Gate 0A follow-up (after independent verification) | `2cbf3a9530aa839a174875e9b66be0178c94d902` on `feature/data-safety`, merged into 0B by `3edba23` |
| Phase 0B branch | `feature/data-integrity`, created from `742fa6d` |
| Phase 0B final code commit | `7e893a0ae1dad4c48661fd5959251b3e26718d50`. This report is the commit after it. |
| Worktree | `/home/user/Progress_tracker-data-safety`, durable and outside `/tmp`. Clean apart from its `frontend/node_modules` symlink. |
| Diff `742fa6d..7e893a0` | 34 files, +2599 / −62. No migrations. |

Other refs, including `main` `4ad209d`, the parked `feature/project-domain` `7b1d03e` and the backup branch, are unchanged. The QA clone `~/charityos-overnight-qa` is untouched. Its 18 refs are preserved in `~/charityos-work-preservation/20261126T103704+0300_overnight-qa-clone/`.

| # | Commit | Part | What and why |
|---|---|---|---|
| 1 | `74cc99c` | B1 | **Reject parent cycles and cross-roadmap parents.** Validation runs under the roadmap row lock; the roadmap is immutable after creation; tree walks guard against cycles. |
| 2 | `3cc9557` | B2 | **Compare session versions as numbers and answer conflicts with 409.** `"2"` no longer conflicts with 2; a stale write answers `version_conflict`. |
| 3 | `3aa02b4` | B2 | **Version-aware session PATCH, attribution kept out.** Fields are allowed by status; attribution changes answer `use_correction`. |
| — | `2cbf3a9` + merge `3edba23` | 0A follow-up | Drill evidence is never pruned; the `test_charityos*` override namespace is reserved. |
| 4 | `a2f2008` | B2 | **Audited corrections of attribution and times.** The linked entry is updated in the same transaction (decision 4.5); end-in-future and 24-hour rules; pauses are clipped to the window. |
| 5 | `2729e1b` | B2 | **A linked entry's attribution follows its session.** |
| 6 | `0b9252b` | B3 | **Duplicates and invalid combinations become field errors, never 500.** Every database constraint is validated; a race answers 409; daily totals update; plan items append. |
| 7 | `d4c72be` | B4 | **Atomic Add to Today / Start focus endpoint.** |
| 8 | `99f39a4` | B4 | **The frontend uses the atomic endpoint.** |
| 9 | `ca36488` | B5 | **Read-only `check_data_integrity` command.** |
| 10 | `7e893a0` | Docs | The API contract and the migration ledger. |

## 2. What changed, by requirement

**B1 Roadmap integrity.** Creates and moves validate the parent while holding the roadmap's row lock. The parent may not be:
- in another roadmap;
- the node itself or one of its descendants;
- archived;
- part of a cycle already in old data.

A node's roadmap can't change. `_ancestry` (used when a session starts) and the tree builder stop at nodes they have already seen. Previously a legacy cycle could make starting a session loop forever.

**B2 Focus-session concurrency and attribution.**
- Versions are parsed as whole numbers, and a stale version answers 409 `version_conflict`.
- PATCH needs the current version and increments it.
- Category, task, roadmap item and the deep-work flag change only through the audited correction. That correction:
  - validates ownership, archived categories, a future end and the 24-hour limit;
  - clips pauses to the corrected window;
  - records before and after values;
  - updates the linked schedule entry in the same transaction.
- Insights counts the corrected minutes once, under the new category (tested).
- A linked entry can no longer switch category on its own.

**B3 Duplicate operations.** The root cause was in DRF: per-user constraints were never validated, so PostgreSQL rejected the write and the API answered 500. Now:
- Every constraint is validated with Django's own `Constraint.validate`, using a single table of messages. That covers unique (including case-insensitive and conditional), check and overlap constraints.
- A race past validation answers 409 or 400 via the SQLSTATE backstop. Generic writes run in a savepoint.
- Duplicate behaviour is defined: water and nutrition update the day's entry, and an archived day is refused. Plan items without a position are appended, and a collision is a field error. Carry-over appends.

**B4 Atomic Add to Today.** One endpoint, one transaction:
1. Reuse the item's open task, or create one.
2. Plan it for today, or carry it over from another day.
3. Optionally start the focus session, with the roadmap's category by default.

Every failure rolls back every write. Repeated taps no longer create duplicate tasks.

**B5 Data integrity.** `check_data_integrity` is read-only and exits 1 on any finding. Its first run on real-shaped data found a false positive in its own query: two NULL tasks were treated as different. That was fixed, with a regression test.

Elsewhere:
- Ownership is validated in every new path: corrections, Add to Today, roadmap parents and session PATCH.
- Rollback is tested in corrections, Add to Today and the race backstop.
- Focus time and evidence are untouched by any 0B path. The Gate 0A `RESTRICT` rules and the archive rules still hold; their tests pass.

## 3. Migration details

**None.** Phase 0B changes validation, services and the API only, and `makemigrations --check` reports `No changes detected`.

The restore drill still runs every pending migration (the 11 from Phase 0A plus the task-status `planning.0007`/`0008`) forward, back and forward again. It ran on a copy of `charityos_acceptance`, with every row identical after the reversal.

## 4. Tests and actual results

Evidence is in `~/charityos-qa-evidence/20261126_phase-0b_7e893a0/`:
- `backend.txt`, `frontend.txt`, `restore-drill.txt`;
- `check-data-integrity-on-migrated-acceptance-copy.txt`;
- `audit-probes-24nov-rerun.txt`;
- `databases-before.txt` and `databases-after.txt`.

| Check (on `7e893a0`) | Actual output |
|---|---|
| `ruff check` / `ruff format --check` | `All checks passed!` / `111 files already formatted` |
| `makemigrations --check --dry-run` | `No changes detected` |
| `manage.py check`, `check --deploy` (production settings) | `System check identified no issues (1 silenced).` (both) |
| Full backend suite | `371 passed`, 0 skipped (312 at Gate 0A) |
| Phase 0B test files (8) | `56 passed` |
| Forward/reverse migration tests (5 files) | `48 passed` |
| Frontend lint, typecheck | clean, clean |
| Frontend tests | `Test Files 9 passed`, `Tests 53 passed` |
| Production build | `✓ built` (to a scratch directory) |
| Restore drill `--migrate` | `DRILL PASSED`. All checks matched: row counts, content fingerprints, schema and migrations. Forward, backward with every row identical, forward again. Backup: `20261126T083321Z_drill`; report: `drill-reports/20261126T083320Z_charityos_acceptance.txt`. |
| `check_data_integrity` on the migrated acceptance copy | 5× `OK`, `All integrity checks passed.` The copy was then dropped after its owner and token were checked. |
| Databases | Identical names and OIDs before and after QA. `charityos` still has 34 migrations (last 24 Nov 16:37), 0 users. |

**Mutation checks.** Each guard was removed, its test was confirmed to fail, and the file was restored byte-identically:
- roadmap lock;
- session row lock;
- entry sync;
- pause clipping;
- future-end rule;
- constraint validation;
- integrity backstop;
- Add to Today transaction.

**Regression tests for every reported defect.**

| Defect (source) | Test |
|---|---|
| Parent cycle accepted (audit) | `test_audit_probe_two_node_cycle_is_refused` |
| Cross-roadmap parent (audit) | `test_parents_must_be_in_the_same_roadmap` |
| `_ancestry` loops on a cycle (audit) | `test_cycles_already_in_old_data_are_contained` |
| Session PATCH without a version (audit) | `test_audit_probe_attribution_cannot_be_patched`, `test_patch_requires_the_current_version_and_bumps_it` |
| Corrections not tested; future end, unbounded length, pause handling (audit) | `tests/test_session_corrections.py` (12 tests) |
| Completed-session attribution bypassing corrections; linked entry diverging (QA) | `test_correcting_a_linked_session_corrects_its_entry_and_insights_once`, `test_a_running_linked_entry_cannot_switch_category_alone` |
| Duplicate reflection 500 (audit); duplicate area, challenge, water and nutrition 500 (QA) | `test_audit_probe_second_reflection_for_a_day`, `test_every_duplicate_or_invalid_combination_is_a_field_error`, `test_daily_totals_saved_twice_update_the_day` |
| Add to Today non-atomic, stray tasks, duplicate tasks (audit, QA) | `tests/test_add_to_today.py` (8 tests) |
| `expected_version` sent as text gave a false conflict | `test_a_version_sent_as_text_is_the_same_version` |

**The 24 Nov audit probes, re-run.** The 0B-scope findings are fixed:
- a parent cycle gives `(200, 400)`;
- a cross-roadmap parent gives `400`;
- a session PATCH without a version gives `400`;
- a duplicate reflection gives `(201, 400)`.

The 0C-scope findings are unchanged, as expected:
- `metrics?start=1900` still answers 200 (1.22 s, 8.4 MB);
- 25 failed logins all answer `[400]`, with no throttle;
- a login without CSRF answers 200;
- an evidence URL can be PATCHed to `http://` (200).

## 5. QA-session reconciliation

The QA clone's `qa/release-candidate` (`5a80dd2` + 11 commits) and `phase-0bc` (+ `6cce451`) are preserved and untouched.

- **Integrated:** only `270e169` and `6cce451`, the migration-wrapper target proof, applied as `7c48f59` after independent review and mutation checks.
- **Superseded:** `6cfdef4`, the Add to Today position, by B4.
- **Held for later approval:**
  - deploy: `5f3d821`, `1b4300a`, `987974e`;
  - PWA and session-expiry fixes: `af0d36c`, `066da59`;
  - QA harness and reports: `6cc2c2b`, `3e73fda`, `6d7afa5`, `ad3b335`.
- **QA finding R2** (`archived_at` writable by PATCH) did not reproduce. See the Gate 0A sign-off.

The full table is in `CHARITYOS-GATE-0A-FINAL-SIGNOFF.md`, section 2.

## 6. Commit `270e169` review (summary)

The defect was real: backups followed `PG*` while `manage.py` followed `POSTGRES_*`. `270e169` alone was incomplete, and `6cce451` completes it by proving which database Django actually reaches. Both were integrated as `7c48f59`. `37e0efe` then removes the wrapper's implicit default target, which was the personal `charityos` named in `.env`. Details and tests are in the Gate 0A sign-off, section 3.

## 7. Known limitations

- **Running sessions can't change attribution at all.** PATCH refuses it, and the correction service accepts only ended sessions. To recategorise a running session, finish it and then correct it.
- **`check_data_integrity` reports but never repairs.** Repairing legacy cycles or cross-user links is a deliberate, manual step.
- **Two API error shapes still exist.** DRF field errors (`{"field": [...]}`) and domain errors (`{"detail", "error": {...}}`) coexist. Unifying them is Phase 0C (S10).
- **A duplicate daily reflection now answers 400 instead of 500.** The reflection UX and revision protection (load and edit the existing reflection, never silently overwrite it) are still Phase 0C.
- **Same-day `manual` backups are pruned** by a later backup on the same day, by the daily rule. Before a risky manual change, use `--label pre-migrate` or `--no-prune`. Noted by the independent verifier.
- **CI has never run, because nothing is pushed.** The ops round-trip tests skip there (PG16 client, PG17 service).

## 8. Remaining risks

- **The off-machine copy is not yet off the machine.** `~/charityos-offsite/` is on the same disk; it needs the owner's medium. It also predates `2cbf3a9`, so it should be refreshed after this review.
- **`charityos` itself has never been backed up or drilled.** Only `charityos_acceptance` is approved for that.
- **Database left for the owner.** `charityos_restore_drill_ae_20261126t075039z` was created by the read-only verifier session and is left for the owner to drop.
- **The QA clone's deploy work assumes `DATABASE_URL`.** The ops scripts now refuse `DATABASE_URL`, so deployment work must name the server with `PGHOST`/`PGPORT`, or adapt the scripts deliberately.
- **Public deployment stays unsafe until Phase 0C**, because login has no throttling and no CSRF check.

## 9. Recommended Phase 0C scope

As the owner listed:

1. **C1. Login throttling** with `django-axes`: 5 failures per email+IP, a 15-minute lockout, covering the API and admin. Responses must not reveal whether the email exists.
2. **C2. Login requires CSRF.** Without a token, 403.
3. **C3. Security logging.** A `charityos.security` logger records login success, failure and lockout, logout, `erase_user` and blocked deletes. Emails are masked; passwords, session ids and tokens never appear.
4. **C4. Explicit writable fields** for every serializer. No `"__all__"`, enforced by a meta-test.
5. **C5. Bounded analytics.** `/analytics/metrics` gets a window of at most 366 days, filtered in SQL. Plan its retirement once Insights covers it.
6. **C6. One error envelope** for every status. Generic 500 messages with request ids, and structured server logs.
7. **C7. Evidence URL validation on PATCH**, using merged values.
8. **C8. Reflections.** The Reflect screen loads today's reflection; reflections are never silently overwritten (immutable or edit-disabled, explained in the UI) until Phase 3 revisions exist. A duplicate already answers 400 (B3).

Deployment, the beta, the PWA fixes held in the QA clone, and installing the backup timer each need separate approval.
