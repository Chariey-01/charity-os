# CharityOS — Phase 0C implementation report

**Status: Phase 0C (S8–S12) is implemented and validated. It stops here for product-owner review.**
- Nothing was merged into `main`, pushed or deployed.
- No personal or shared database was modified.
- No backup timer was installed.

## 1. Branches, base and environment

| | |
|---|---|
| Phase 0B, reviewed and accepted | `feature/data-integrity` at `174a3f93efe1cb80d5117d2ced09fec672096c21`. The review is in `CHARITYOS-PHASE-0B-REVIEW.md`; one Medium finding was fixed in `df16ea7`. |
| Phase 0C branch | `feature/security-hardening`, created from `174a3f9` |
| Phase 0C final code commit | `43156f4f631ad7f21cbd5734c6a0d20212ad0dbf`. This report is the commit after it. |
| Worktree | `/home/user/Progress_tracker-data-safety`. Durable, outside `/tmp`, and clean apart from its `frontend/node_modules` symlink. |
| Python environment | A new `.venv` inside the worktree (gitignored). It holds the project's pinned requirements plus `django-axes==9.1.0`. The shared virtualenv in `/home/user/Progress_tracker` was not used for installs and was not changed. |
| `/home/user/Progress_tracker` | Its working tree, index, checked-out branch (`feature/mobile-scheduler` `b9b0b5e`) and `.venv` were not touched. As with every worktree, the new commits and branch refs are stored in its shared `.git`. |

Other refs are unchanged: `main` `4ad209d`, `feature/data-safety` `2cbf3a9`, the parked `feature/project-domain` `7b1d03e`, the backup branch and the QA clone.

| # | Commit | Item | What |
|---|---|---|---|
| 1 | `6f52c2e` | S10 | Evidence URL rules are enforced on every update, against the merged record |
| 2 | `50be4c2` | S9 | Metrics range bounded to 366 days and validated; series query only the window |
| 3 | `1dd4008` | S9 | Pins that every Insights period is valid for metrics. It also corrects a wrong statement in `50be4c2`'s message (see section 6). |
| 4 | `9975cd4` | S8 | Schema: reflection `version` and the `ReflectionRevision` table (`reflections.0003`, with a reverse guard) |
| 5 | `e0cf687` | S8 | Edits keep history: versioned edits, a revisions endpoint, idempotent creates or 409 `already_exists` |
| 6 | `fe5660f` | S8 | The Reflect screen edits the existing reflection with its version |
| 7 | `0a3641f` | S11 | django-axes lockout (five failures allowed, the sixth refused, 15 minutes), login CSRF, erasure of sign-in records |
| 8 | `5e4f2d4` | S12 | Security event log with masked emails and truncated IPs |
| 9 | `3f1c6a2` | S11 | Frontend test: the lockout message is shown, and the CSRF token is fetched first |
| 10 | `43156f4` | Docs | API contract, migration ledger, operations (unlocking, logs, the proxy IP setting) |

## 2. Each item: reproduced, tested first, fixed

| Item | Reproduced before the fix | After |
|---|---|---|
| **S10 Evidence URLs** | 3 of 15 new tests failed: an update to `http://` (audit probe: 200), moving a GitHub link to another host, blanking a note. Creates were already correct. | 15/15. Rules are checked against the stored record merged with the update. Malformed, `ftp:` and `javascript:` URLs get field errors. |
| **S9 Metrics** | Failed before: the audit probe `start=1900` (200, 8.4 MB), a 367-day range, an end before the start, an unknown period, and the row-count test (699 sessions loaded for a 7-day view). | 15/15. At most 366 days; field errors; series read only the window; all-time totals aggregated in SQL; every Insights period accepted. |
| **S8 Reflections** | 13 of 15 failed. The audit probe for a duplicate reflection gave 500 at audit time and 400 after 0B. | 15/15 behaviour tests and 3 migration tests. Versioned edits keep every earlier wording; 409 for a stale edit; owner-only revisions endpoint; an identical retry returns the record (200), different words give 409 `already_exists` with the existing id; two devices racing give one 200 and one 409. The UI edits instead of re-posting. |
| **S11 Sign-in** | 5 of 9 failed. The audit probes: no CSRF needed (200), and no lockout after 25 failures. | 10/10, plus 1 erasure test and 1 frontend test. CSRF is required (403 without it). Failures 1–5 answer normally; the 6th answers 429 and locks that email and IP for 15 minutes, for the API and the admin alike. Identical responses for unknown accounts. A success resets the count; the right password after five failures gets in; the lock expires. Session-authenticated writes need CSRF. |
| **S12 Security log** | 6/6 failed (no log) | 6/6: `login_succeeded`, `login_failed`, `login_locked_out`, `logout`, `csrf_rejected`, `erasure_dry_run`, `user_erased`. Every test also scans all captured log records for the raw email, password, session key and CSRF token. |

**Mutation checks.** Each guard was removed, its tests were confirmed to fail, and the file was restored byte-identically:
- S8: revision write, version check;
- S11: login CSRF, axes backend;
- S12: email masking (all 6 tests fail).

**Duplicate-request handling across Phase 0.**
- Reflections and reviews: an identical retry returns the record (200); different content gives 409 `already_exists`. This is S8, and supersedes 0B's 400 for these two resources.
- Daily water and nutrition: a second save updates the day (B3).
- Sessions, schedule entries and Add to Today: idempotent by client id or natural key.
- Other duplicates: 400 field errors, or 409 on a race.

## 3. Migrations

| Migration | Notes |
|---|---|
| `reflections.0003_reflection_revisions` | Constant-default `version` columns (no table rewrite) and the new table. The reverse refuses while revisions exist. Tested forward and back with old-shape rows. |
| `axes.0001`–`0010` | Third party. Sign-in attempt tables only. Reversible (`axes zero`) in the drill. |

Neither conflicts with the parked `feature/project-domain` (its apps are `planning` and `projects`). `makemigrations --check` reports `No changes detected`.

## 4. Final validation (actual outputs)

Evidence is in `~/charityos-qa-evidence/20261126_phase-0c_43156f4/`:
- `backend.txt`, `frontend.txt`, `restore-drill.txt`;
- `check-data-integrity-on-migrated-acceptance-copy.txt`;
- `audit-probes-24nov-rerun.txt`;
- `databases-before.txt` and `databases-after.txt`.

| Check (on `43156f4`) | Output |
|---|---|
| `ruff check` / `ruff format --check` | `All checks passed!` / `120 files already formatted` |
| `makemigrations --check --dry-run` | `No changes detected` |
| `manage.py check`, `check --deploy` (production settings) | `System check identified no issues (1 silenced).` (both). The silenced check is `auth.W004`, explained in settings. |
| Full backend suite | `436 passed` (312 at Gate 0A, 371 at 0B) |
| Phase 0C test files (6) | `63 passed` |
| Forward and reverse migration tests (6 files) | `51 passed` |
| Archive, restore, backup, erasure, admin and test-database groups | `102 passed` |
| Frontend lint, typecheck | clean, clean |
| Frontend tests | `Test Files 9 passed`, `Tests 56 passed` |
| Production build | `✓ built in 3.42s` |
| Restore drill `--migrate` | `DRILL PASSED`. Every check matched: row counts, the fingerprints of all rows, schema, migrations and `manage.py check`. Forward (including axes and `reflections.0003`), backward with every row identical, forward again. Backup: `20261126T154037Z_drill`. |
| `check_data_integrity` on the migrated copy | 5× `OK`, `All integrity checks passed.` The copy was dropped after its owner and token were verified. |
| Databases | Names and OIDs identical before and after. `charityos`: 34 migrations, last 24 Nov 16:37, 0 users. |

**The 24 Nov audit probes, re-run.**

| Probe | Result now | Fixed in |
|---|---|---|
| Metrics `start=1900` | 400 | 0C |
| Login without CSRF | 403 | 0C |
| Evidence URL to `http://` | 400 | 0C |
| Duplicate reflection | (201, 200): an identical retry returns the existing record | 0C |
| Parent cycle | (200, 400) | 0B |
| Cross-roadmap parent | 400 | 0B |
| Session PATCH without a version | 400 | 0B |
| Task delete, plan delete, category with sessions | 405 | 0A |

Still open: `/tasks` returns an unpaginated list (outside the authorized S8–S12 scope).

## 5. Known limitations

- **Deployment must configure the client IP for lockouts.** Behind a reverse proxy, `REMOTE_ADDR` is the proxy, so all users would share one lockout. Set `AXES_CLIENT_IP_CALLABLE` to the proxy's trusted forwarded-for header (documented in operations).
- **Lockout is per email and IP pair.** A distributed attack on one email from many addresses is slowed only per address. A per-account ceiling could be added later.
- **django-axes is disabled in the test settings.** Django's test `client.login()` calls `authenticate()` without a request, which axes refuses. The 10 login-security tests and the lockout log test enable it explicitly.
- **Reflection revisions are kept indefinitely.** They are removed only by `erase_user`. There is no UI yet for viewing revisions; the API endpoint exists.
- **Unpaginated lists.** List endpoints are still unpaginated (`/tasks` returned 120 rows in the probe).
- **Retried creates.** Tasks, evidence and accomplishments can still be created twice if a client resends (0B review, Medium).
- **Two error shapes.** DRF field errors and the domain envelope coexist.

## 6. Correction on record

The message of `50be4c2` says the bundled client does not call `/analytics/metrics`. That is wrong: `InsightsScreen` calls it for roadmap progress. History was not rewritten. Commit `1dd4008` records the correction and adds a test confirming that every period the screen sends (`7d`, `30d`, `90d`, `challenge`, `year`) is accepted.

## 7. Remaining risks and owner decisions

- **Merging is waiting on your approval.** `feature/data-safety` (0A), `feature/data-integrity` (0B) and `feature/security-hardening` (0C) form one stacked line on `1ceba99`. None of it is merged into `main`.
- **Deployment prerequisites:**
  - HTTPS;
  - `AXES_CLIENT_IP_CALLABLE`;
  - production logging collection;
  - a backup and restore drill of the real database before any real data goes in.
- **`charityos` has never been backed up or drilled.** Only the acceptance database is approved for that.
- **The off-machine copy is still on the same disk.** The encrypted package predates 0B and 0C and should be refreshed.
- **The verifier's leftover database**, `charityos_restore_drill_ae_20261126t075039z`, is still waiting for the owner to drop it.
- **CI has never run on this work**, because nothing is pushed.
