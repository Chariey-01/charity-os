# CharityOS — daily operations: integration review and pull request

## PR #5 CI failure investigation (27 Nov 2026, ~05:50 EAT)

**Result.**
- **Every GitHub Actions failure on PR #5 has one cause.** GitHub refused to start the jobs because the account is locked for a billing issue. No runner was assigned, no step ran, and there are no logs. **[Blocked]** on the owner.
- **Both CI jobs were reproduced locally** on the PR head's exact tree, with the workflow's own commands, versions and lockfiles. **Both pass.** **[Verified]**
- **No defect was found, so no code was changed.** This report is the only file changed.
- **GitHub CI has never run a step in this repository.** PR #5 has no GitHub CI result and is **not CI-verified**. Do not merge it until both checks pass on its latest commit.

Legend: **[Verified]** verified and passing · **[Failed]** · **[Blocked]** blocked by external action · **[Not independently verified]**.

### C1. Commits and runs

| Item | Value |
|---|---|
| Base | `main` at `e17a153791aab356944e57f298223caab87404ed` |
| PR head at the start (local = remote) | `b368836418b6d029ab3eed7fb85666e0c3c60e41` |
| Reviewed code | `5895f950aa808699f436f4a1cabf0c1ec9459d35`. Since then, `b368836` only adds this report (`git diff --stat 5895f95 b368836`: 1 file). |
| What `pull_request` CI tests | The merge ref `7848be58b83cc61e60a69c20969c2ed8de808181`. Its tree `787bfcd` is identical to the head's tree, because the branch is 0 behind `main`. |
| Runs on `b368836` | [45925406327](https://github.com/Chariey-01/charity-os/actions/runs/45925406327) (`pull_request`) and 45925401844 (`push`), both `failure` |
| Earlier runs on this branch | 45925385083 and 45925336265, on `e384f06`, both `failure` for the same reason |
| Latest PR commit after this investigation | See C7 |

### C2. Root cause of every CI failure

| Run | Job (ID) | Runner label | Steps run | Duration | GitHub annotation | Category |
|---|---|---|---|---|---|---|
| 45925406327 | frontend (140265440904) | `ubuntu-latest` | 0 | 2 s | "The job was not started because your account is locked due to a billing issue." | **A, billing** [Verified] |
| 45925406327 | backend (140265441126) | `ubuntu-24.04` | 0 | 3 s | same | **A** [Verified] |
| 45925401844 | backend (140265424769) | `ubuntu-24.04` | 0 | 3 s | same | **A** [Verified] |
| 45925401844 | frontend (140265425027) | `ubuntu-latest` | 0 | 2 s | same | **A** [Verified] |

Evidence: every job has an empty `runner_name`, no steps, and that annotation on `.github`. The run log archive is 22 bytes (an empty zip), and the job log answers `BlobNotFound`.

**The other causes were ruled out:**
- **B. Workflow configuration.** GitHub parsed `ci.yml` and planned both jobs with the correct runner labels. A parse error ends in `startup_failure` with no jobs, as in September. The PR does not change the workflow.
- **C. Dependencies or environment.** Nothing was installed on GitHub. Locally, a fresh `pip install` and a fresh `npm ci` from the lockfiles both succeed (C3).
- **D and E. Application defects and test failures.** Every workflow step passes locally on the exact tree (C3).
- **F. Infrastructure or service startup.** The PostgreSQL service container was never started, because no runner was assigned. Locally, PostgreSQL 16 passes.
- **Permissions.** Actions is enabled with all actions allowed. The workflow token is `contents: read`. The repository is public.

**Not visible from here:** the billing page itself. The CLI token lacks the `user` scope that GitHub's billing API needs. That scope was not requested, and billing settings are not authorized here.

**History.** The repository has 26 runs, and none has ever executed a step:
- 17 are `startup_failure` from September 2026 (`path: BuildFailed`, no jobs), before the current workflow.
- 9 are billing refusals, from 26–27 November.

### C3. Local reproduction of both CI jobs [Verified]

| | GitHub (`ci.yml`) | Local reproduction |
|---|---|---|
| Checkout | `actions/checkout` of the merge ref (tree `787bfcd`) | Fresh clone at `b368836` (tree `787bfcd`). No `.env`, and pushing is disabled. |
| Python | 3.12 | 3.12.3, fresh venv, `pip install -r requirements-dev.txt` |
| Node | 24 | 24.14.0 with npm 11.13.0, fresh `npm ci` (no reused `node_modules`) |
| PostgreSQL | `postgres:16-alpine` on 127.0.0.1:5432; password auth; container role `charityos` (a superuser) | Private 16.15 cluster on 127.0.0.1:5433; password auth; role `charityos` (not a superuser, and no test needs one) |
| Database | `charityos_test` | Labelled throwaway `charityos_cirepro_8c_20261127t022130z`, dropped afterwards after its token was checked |
| Time zone and locale | UTC, C.UTF-8 | `TZ=UTC`, `C.UTF-8` (this machine runs on EAT) |

The container image was not used because Docker is unusable on this machine (socket permission denied). The major version is the same, and the backup tests compare major versions only.

| Job | Command (in order, as in `ci.yml`) | Result | Exit |
|---|---|---|---|
| backend | `ruff check .` | `All checks passed!` | 0 |
| backend | `ruff format --check .` | `136 files already formatted` | 0 |
| backend | `python manage.py check` | `no issues (1 silenced)` | 0 |
| backend | `python manage.py makemigrations --check --dry-run` | `No changes detected` | 0 |
| backend | `python manage.py migrate --noinput` | 60 migrations applied | 0 |
| backend | `pytest -rs` | **`545 passed`**, 0 skipped (backup and restore tests included) | 0 |
| frontend | `npm ci` | Installed. `npm audit` notes 12 findings from `main` (C9). | 0 |
| frontend | `npm run lint` / `npm run typecheck` | clean / clean | 0 / 0 |
| frontend | `npm test` | **`98 passed`** (16 files) | 0 |
| frontend | `npm run build` | `✓ built` | 0 |

The earlier review ran both suites on EAT. Together with this UTC run, that shows both suites are independent of the time zone.

### C4. Fixes, files changed and regression tests

- **Code fixes: none.** No defect was found. The failure is external, so code was not changed to suit CI.
- **Files changed:** this report only.
- **Regression tests added:** none, because there was no defect to pin. The attribution probe in C8b ran in a scratch clone and was **not committed**: it would pin behaviour the owner has not yet decided on.

### C5. Revalidation beyond CI

| Check | Result |
|---|---|
| `check --deploy` (production settings with throwaway values) | `no issues (1 silenced)`, exit 0 **[Verified]** |
| Migration consistency | One `planning` leaf, no conflicts, `makemigrations --check` clean. The PR's only migration change is `A planning/migrations/0011_task_due_date.py`. **[Verified]** |
| Backup, restore and migration tests | All inside the 545: `test_ops_backup` 14, `test_ops_restore` 13, `test_ops_migrate` 8, `test_history_restrict` 19, `test_task_due_dates` 5, `test_test_database` 12. **[Verified]** |
| `ops/db/restore-drill.sh --migrate` | **Not run in this session:** the session's permission system refused the command. It last passed on identical code (`5895f95`, section 9 below). **[Not independently verified]** in this session |

### C6. Browser workflow on `b368836` [Verified]

**Setup:**
- The production build from the clean clone, served by `vite preview`.
- A Django development server on the throwaway database.
- A freshly bootstrapped test account. No restored data and no personal or protected database were used.
- Chrome 151 headless at 390×844 with touch.

**Result: 17/17 passed with 0 console errors.** The server answered 121 requests (115 × 200, 4 × 201, 2 × 403), with no 5xx and no tracebacks. The two 403s are expected: `/me` before sign-in, and the deliberately ended session in step 15.

| Brief item | Browser step | Result |
|---|---|---|
| 1. Task quick capture | 3: title only, from Today | [Verified] |
| 2. Workstream assignment | 2: add the six workstreams; 4: assign Learning, high priority, due today, 30 min | [Verified] |
| 3. Scheduling | 5: quick add pre-filled; the entry is linked to the task | [Verified] |
| 4. Focus-session lifecycle | 6: start from the task, which starts the scheduled activity; run 40 s; finish | [Verified] |
| 5. Task completion | 6–7: finished together with the focus session; kept in history and reopenable | [Verified] |
| 6. Weekly progress | 8: Today shows "100% · 1 of 1 planned done"; 9: the Insights weekly % | [Verified] |
| 7. Completed-task chart | 9: "Completed tasks by workstream" shows Learning and Education | [Verified] |
| 8. Time-allocation chart | 9: "Tracked time by workstream" shows Learning and Education, 1m, 100% | [Verified] |
| 9. Historical week accuracy | 10: the previous week is unchanged and empty. Backend: 21 `test_progress` tests. Caveat: workstream reassignment (C8). | [Verified], with the C8 caveat |
| 10. Weekly review and revisions | 12: saved, then still there after leaving and returning ("Earlier versions are kept"). That earlier versions are kept is verified by the 15 `test_reflection_revisions` tests, not in the browser. | [Verified] |
| 11. Offline launch and recovery | 14: the installed shell opens offline and recovers without a tap | [Verified] |
| 12. Expired-session handling | 15: all sessions deleted server-side; the next navigation returns to sign-in without a reload | [Verified] |
| 13. Mobile responsiveness | 13: 360, 390 and 430 px on Today, Tasks, Insights and Review, with no horizontal overflow | [Verified] |

### C7. GitHub CI on the latest PR commit [Blocked]

This report's commit is documentation only; its parent is `b368836`. Its CI runs are recorded in C7a, which was added after the commit was pushed and its runs were inspected.
- **Frontend CI result:** [Blocked] by the billing lock. Locally reproduced as passing (C3).
- **Backend CI result:** [Blocked] by the billing lock. Locally reproduced as passing (C3).
- No earlier run succeeded, so no earlier run can stand in for the latest commit.

### C8. Migration `planning.0011` [Verified]

Independent check: real `migrate` commands against a real migrated database, comparing whole rows (`row_to_json`). **14/14 passed.**
- The graph has one `planning` leaf, no conflicts, and `0011` depends only on `0010_restrict_history_deletes` (`main`'s leaf).
- **Existing records stay intact.** Four tasks were created under `0010` with Unicode titles, multi-line descriptions, every status, with and without a workstream. After migrating forward, every value was byte-identical and `due_date` was NULL: no due date is invented.
- **Reversal refuses to delete populated due dates.** With one due date set, `migrate planning 0010` raised `RuntimeError: Refusing to reverse planning.0011: 1 task(s) have a due date that would be lost.` Afterwards `0011` was still recorded, the column was still there, and every row was identical, with the date kept.
- **Once due dates are cleared deliberately,** the reversal runs and the rows are identical to the `0010` originals. Migrating forward again gives identical rows with NULL due dates.
- **No unrelated migration history changed.** `git diff --name-status e17a153 b368836 -- '*/migrations/*'` lists only `A backend/planning/migrations/0011_task_due_date.py`.

### C8b. Historical analytics: workstream attribution

**Finding [Verified]: reassigning a done task rewrites past weeks' completed-task chart, but not the time chart.** A probe test on the head code did this:
1. Completed a task on Tue 17 Nov, with a one-hour completed activity in Learning.
2. On 24 Nov, after that week, moved the task to Personal Administration through the real `PATCH /api/v1/tasks/<id>`.

```
BEFORE completed_tasks=[('Learning and Education', 1)]   time=[('Learning and Education', 60)]
AFTER  completed_tasks=[('Personal Administration', 1)]  time=[('Learning and Education', 60)]
```

After the edit, the two donuts for the same past week disagree.

**Why:**
- `planning/progress.py` `_summary()` reads the task's **current** `area`.
- No `PlanningEvent` type records a workstream change, so the old value cannot be rebuilt.
- The task serializer allows editing `area` on done tasks.
- Time allocation reads the schedule entry's own category, which can only be edited while the entry is open, or an unlinked focus session's category, which is fixed and changed only through audited corrections. So time does not move.
- The same mechanism means retitling a task changes its title in past weeks' lists (cosmetic). Renaming a workstream relabels both charts: it is the same entity, which is acceptable.

**Assessment:**
- This contradicts the module's own promise ("a past week is judged as it stood at the end of that week").
- It is documented in `docs/api-contract.md` and the reports, but not in the app.
- Its impact is low for a single-user beta: nothing is lost, the task is only regrouped, and only after a deliberate recategorisation. It is not a CI or data-integrity issue.

**Recommendation:**
- **Acceptable for merging PR #5.**
- **A historical attribution snapshot is required before My Journey or long-term history** (Phase B) builds on these charts. The smallest design: store the task's workstream (ID and label) in the snapshot of each completion event, and attribute a completed task to the workstream at its completion, falling back to the current one for older events. `PlanningEvent.snapshot` is JSON, so this needs **no schema migration**.
- A fuller alternative is an `area_changed` event, rebuilt at the end of the week like due dates. It needs a state-only choices migration.
- Owner decision. Not implemented here, by instruction.

### C9. Remaining risks

| Risk | Status |
|---|---|
| **GitHub has never executed this workflow.** Differences that exist only on the runner are unverified: the runner image's PostgreSQL client tools (the backup tests call `pg_dump`/`pg_restore`), the minor version of `postgres:16-alpine`, and the first-time action downloads. | [Not independently verified] until billing is fixed |
| **`npm audit`: 12 findings** (2 critical, 2 high, 8 moderate). None is introduced by this PR (`package.json` and the lockfile are unchanged from `main`). They are in dev and build tooling: `vitest`/`tinypool`, `vite` (dev-server `launch-editor`), `source-map-js`, `typescript-eslint`, `minimatch`. None is in the browser bundle. Recommend a separate dependency-update PR once CI works. | Open, not a PR #5 defect |
| Workstream attribution in past weeks (C8b) | Owner decision |
| Restore drill not rerun in this session (C5) | [Not independently verified] in this session |
| The parked `feature/project-domain` migrations collide with `0009`–`0011` (section 6 below) | Unchanged, deferred |

### C10. Owner actions required

1. **Fix the GitHub billing lock.** It is the only thing blocking CI.
   - Go to github.com → your avatar → **Settings → Billing and plans** for the account `Chariey-01`.
   - Clear what locked it: a failed payment, an unpaid invoice, or the payment method.
   - Public repositories get free standard runners, but an account lock blocks them too.
2. **Re-run PR #5's checks on its latest commit** (Checks tab → "Re-run all jobs"), or push any commit. Confirm that `backend` and `frontend` are both green **on the head SHA**.
3. **Only then review and merge,** yourself. Consider requiring both checks on `main`.
4. **Decide on workstream attribution** (C8b) before Phase B.
5. *Optional:* allow the restore drill to be rerun on this code.

**Evidence:** `~/charityos-qa-evidence/20261127_pr5-ci-investigation_b368836/`. It holds the GitHub run and annotation data, both CI job logs, the migration check and its script, the attribution probe, the browser results with screenshots and the server log, cleanup, and the database inventory.

**Boundaries kept:**
- No merge, deployment, hosting, billing, branch-protection or repository-setting change.
- No force-push or history rewrite.
- `charityos`, `charityos_acceptance`, `charityos_restore_drill_ae_20261126t075039z` and every other database were untouched: names and OIDs are identical before and after.
- Only this session's own labelled database was created and dropped.
- The parked worktree and the main checkout were not modified.

---

*The sections below are the earlier integration review (~05:00 EAT), kept as written. Where they differ, the CI investigation above supersedes them.*

**Result (27 Nov 2026, ~05:00 EAT).** `feature/daily-operations` was reviewed against `main`, not taken on its report's word.
- **Four review findings were fixed:** one Medium (migration reversal could lose data) and three Low.
- **Everything was revalidated on the reviewed code:** backend 545, frontend 98, 17/17 browser checks, restore drill passed.
- **It is ready for owner review** through a pull request. It is **not merged** and not deployed.
- **GitHub Actions still refuses every job** for the account's billing lock, so there is no GitHub CI result.

Legend: **[Verified]** verified and complete · **[Not independently verified]** implemented but not independently verified · **[Failed]** · **[Blocked]** · **[Deferred]**.

## 1–3. Commits

| | SHA |
|---|---|
| Starting `main` (local and remote) | `e17a153791aab356944e57f298223caab87404ed` (merge of PR #4) |
| Feature branch at the start of this review | `3a19a378ae3dc6f13e1837712f10e09afe6c3f79`: 15 commits on `e17a153`, 0 behind |
| **Final reviewed code** (all validation below) | `5895f950aa808699f436f4a1cabf0c1ec9459d35` |
| After it | This report only (documentation) |

## 4. Working-tree safety [Verified]

- **The worktree** `/home/user/Progress_tracker-data-safety` was on `feature/daily-operations`, clean apart from its untracked `frontend/node_modules` symlink. There were no uncommitted changes to attribute.
- **The main checkout** `/home/user/Progress_tracker` is on `feature/mobile-scheduler` `b9b0b5e`, clean and untouched.
- **The parked `feature/project-domain` worktree** has 3 modified and 2 untracked files, which belong to the other session. They were untouched; read only with `--no-optional-locks`.
- **Sessions and processes:** no other session was active, and no test or server process was running.
- **Remote:** `main` = `e17a153`. The feature branch was not on the remote before this review, and no PRs were open.

## 5. Diff summary (`e17a153..5895f95`, 19 commits)

| Area | Change |
|---|---|
| Error logging | Server errors to stderr through a redacting formatter (`config/error_logging.py`) |
| API errors | `not_authenticated`; `csrf_failed` with `reason` |
| Tasks | Optional `due_date` with `due_changed` events; list filters `status`, `area`, `completed_since` (`planning.0011`) |
| Progress | `planning/progress.py` and `GET /progress`. Insights' category minutes are now shared, not copied. |
| Workstreams | Six suggested categories, opt-in (`POST /areas/ensure-workstreams`, `--with-workstreams`) |
| Frontend | Tasks tab, quick capture, task sheet, Today task panels, Insights "This week", weekly review, donut chart, focus finish can complete the task, expired-session handling, offline auto-retry |
| PWA | Service worker keeps the last complete shell |
| Docs | API contract, migration ledger, deployment plan, PWA checklist, reports |

Size: 57 files changed, +4818 / −144 lines. The commits are listed in the pull request.

## 6. Migration assessment

| Check | Result |
|---|---|
| Based on `main`'s graph | `planning.0011_task_due_date` depends only on `planning.0010_restrict_history_deletes` (`main`'s leaf). There is one `planning` leaf and no conflicts (`MigrationLoader.detect_conflicts() == {}`). `makemigrations --check`: no changes. **[Verified]** |
| Overwrites nothing | It adds a column, a choices change (state only) and a reverse guard. No other migration was touched. **[Verified]** |
| Existing tasks keep their values and get **no invented due date** | A task created under the old schema keeps every value and has `due_date` NULL after migrating (test). Old-shape rows elsewhere are byte-identical, with the new column NULL (`test_history_restrict`). **[Verified]** |
| Reversal is safe | **Finding R1 (Medium), fixed in `faa0a36`.** The reverse used to drop every due date silently. It now refuses while any task has one, as the Phase 0A reverses do. Covered by tests and a mutation check; the drill reverses through it on real-shaped data. **[Verified]** |
| Parked branch compatibility | **Not compatible as is.** The parked `feature/project-domain` adds `planning.0009_task_project_fields` (including an identical `due_date`) and `0010_planningevent_project`, also starting from `1ceba99`. Those collide with this line's `planning.0009`/`0010`/`0011`. An identical field definition does **not** make the histories compatible: integrating it needs its migrations renumbered after `0011`, and its `due_date` `AddField` dropped. Not attempted here, by instruction. **[Deferred]** |

## 7. Security review

| Area | Finding | Status |
|---|---|---|
| Authorization | Every new query is scoped to the requesting user: tasks, events, schedule entries, plan items, focus sessions, roadmap nodes, evidence and accomplishments. A new test puts another user's tasks, entries and sessions into the same week and sees none of them. | [Verified] |
| Input validation | `week`, `completed_since`, `status` and `area` (including a non-UUID) answer 400, never 500 | [Verified] |
| CSRF and sessions | `not_authenticated` signs out; `csrf_failed` is retried once with a fresh token and never signs out. Django's reason is now visible to the operator: it is printable-only and capped because it can echo the client's `Origin` header. | [Verified] |
| Duplicate submissions | Captures and creates send one Idempotency-Key per action. **Finding R3 (Low), fixed in `5895f95`:** a lost answer followed by an edited resubmit showed a raw "Idempotency-Key reused" error; it now explains what happened. | [Verified] |
| Error logs | Emails masked; password, token, secret, session, CSRF, API-key and Authorization values replaced; no query strings; tracebacks contain code lines, not variable values. Over-redaction of code lines that mention "password" is harmless. | [Verified] |
| Rendering | No raw HTML rendering in the frontend (no `dangerouslySetInnerHTML`, `innerHTML` or `eval`). The service worker parses only same-origin `index.html`. | [Verified] |
| Service worker | Only same-origin 2xx responses are cached. `/api/`, `/admin/` and `/static/` are never intercepted. **Finding R2 (Low), fixed in `a3cc60e`:** every page load re-downloaded the shell's assets; an unchanged shell is now left alone. | [Verified] |
| Development diagnostics | Routing `django.security` to the error handler means Django's own CSRF *warnings* (for example admin form rejections) no longer print in development. API CSRF rejections are still logged as `csrf_rejected` with their reason. | Accepted, documented |

## 8. Historical analytics review

`planning/progress.py` reconstructs each task at the end of a week from append-only events: status changes, due-date changes, archive and restore, plan carry-overs and removals, and the replacement entry's creation time for a moved activity. It doesn't rely on the current status.

| Question | Result |
|---|---|
| Does a past week change when a task is later completed, reopened, deferred or archived? | No: tests for completing on Monday then reopening and archiving the next week, deferring after the week, and archiving after the week. The browser run checks the previous week is unchanged. **[Verified]** |
| Changes *during* the week | Reopened later the same week: not completed. Deferred out during the week: leaves it. Archived during the week: leaves it (the user removed it). **[Verified]** |
| Duplicate counting | A task due, scheduled twice and on a plan counts once (test). **[Verified]** |
| Completion timestamps | From status events; tasks with no events fall back to `completed_at`. **[Verified]** |
| Percent denominators | Weekly: planned tasks completed in the week over the planned workload; `null` with no workload. Overall: done over done plus open; archived and cancelled excluded. Unplanned completions are reported separately. **[Verified]** |
| Time allocation | The same "each minute once" computation as Insights (completed activities plus unlinked focus sessions, by the category at the time). **[Verified]** |
| Workstream distribution of completed **tasks** | Uses each task's *current* workstream, so recategorising a done task moves it in past charts. Documented limitation. |
| Weekly review history | Saved through the versioned reflections API; every earlier wording is kept. Saving and revisiting were checked in the browser. **[Verified]** |
| Carry-forward | Only on an explicit "Carry to …" tap; nothing is completed or dropped automatically. **[Verified]** |

## 9. Tests on the reviewed commit `5895f95`

Evidence: `~/charityos-qa-evidence/20261127_daily-ops-review_5895f95/`. Every file records the commit.

| Command | Result | Exit |
|---|---|---|
| `backend/: pytest -q -p no:cacheprovider -rs` | `545 passed`, none skipped | 0 |
| Backup, restore, migration and due-date groups (10 files) | `88 passed` | 0 |
| `ruff check .` / `ruff format --check .` | `All checks passed!` / `136 files already formatted` | 0 / 0 |
| `makemigrations --check --dry-run` | `No changes detected` | 0 |
| `manage.py check`; `check --deploy` (production settings, throwaway values) | `no issues (1 silenced)` (both) | 0 / 0 |
| `frontend/: npm run lint`, `typecheck`, `test`, `build` | clean, clean, `98 passed`, `✓ built` | 0 each |
| `ops/db/restore-drill.sh --migrate` | `DRILL PASSED` (forward, backward through the new guard with every row identical, forward again) | 0 |
| Databases afterwards | Names and OIDs identical to the reference inventory. `charityos`: 34 migrations, 0 users. | — |

The earlier claims (540 / 95 / 17) were reproduced and superseded by these results. **[Verified]**

## 10. Browser verification

- **Earlier evidence.** `20261126_daily-ops_e17a153/e2e-results.txt` did not record a commit; it ran on a working tree later committed as `902b49a`. `20261126_daily-ops_final/` records `2d64ae2` for tests, checks and the drill. Both are consistent with the history, but the earlier e2e file is not tied to a SHA.
- **This review's rerun on `5895f95`.** Chrome 151 headless, 390×844 touch, against a production build and a **fresh, token-labelled restored copy** of `charityos_acceptance` (the seed data, not reset). The copy was dropped after its token was verified. **17/17 passed, 0 console errors.**
- **The brief's 15-point workflow** is covered by these steps: capture by title; workstream, priority, due date, estimate; schedule; start focus from the scheduled task; finish the focus session and the task together; Today and weekly progress; both workstream charts; accomplishments; the previous week unchanged; deferring an overdue task; saving and **revisiting** the weekly review; offline launch and automatic recovery; expired-session return to sign-in; widths 360, 390 and 430 px with no horizontal overflow. **[Verified]**

## 11. Issues found and fixes made

| ID | Severity | Issue | Fix | Status |
|---|---|---|---|---|
| R1 | Medium | Reversing `planning.0011` silently dropped all due dates | Reverse guard plus tests (`faa0a36`) | [Verified] |
| R2 | Low | The service worker re-downloaded unchanged assets on every page load | Skip when unchanged and complete (`a3cc60e`) | [Verified] |
| R3 | Low | Raw "Idempotency-Key reused" message after an edited resubmit | A plain explanation (`5895f95`) | [Verified] |
| R4 | Test gap | Isolation and same-week rules were not pinned | Four tests (`6754070`) | [Verified] |
| R5 | Evidence gap | Earlier e2e results did not record a commit | The rerun prints the SHA | [Verified] |

## 12. Pull request

**https://github.com/Chariey-01/charity-os/pull/5**, "feat: complete daily operations and weekly progress tracking", from `feature/daily-operations` against `main`. It is open and **not merged**; its description states the CI blocker and the reviewed SHA.

## 13. GitHub CI status [Blocked]

Every job is refused: "The job was not started because your account is locked due to a billing issue." This was most recently seen on the merge of PR #4. The checks on the new PR will show the same until billing is fixed. **The local results in section 9 are not GitHub CI.**

## 14. Remaining blockers

| Blocker | Status |
|---|---|
| GitHub billing lock: no CI | [Blocked] on the owner |
| Owner review and merge of the PR | [Blocked] on the owner (not authorised here) |
| Hosting, domain, HTTPS, trusted proxy, logs, on-host backup and drill | [Blocked] on owner decisions (`deployment-plan.md`) |
| Android install test | [Blocked] on deployment |

## 15. Product gap assessment

The intended chain is: My Vision → Goals → Milestones → Roadmaps and Projects → Tasks → Schedule → Focus Sessions and Work Logs → Evidence and Achievements → My Journey and Insights.

| Element | State on this branch |
|---|---|
| **My Vision** | Not built. There is no model, screen or document defining it. |
| **Goals** | Not built. The 96-day *Challenge* is a time-boxed commitment, not a goal hierarchy. |
| **Milestones** | Partial: roadmap nodes (section, topic, item) with completion act as roadmap milestones. Project milestones exist only in the parked branch. |
| **My Roadmaps** | Built: roadmaps, nodes, prerequisites, resources, progress, Add to Today. A roadmap is a learning path, **not** a goal. |
| **My Projects** | Not on this line. The parked `feature/project-domain` holds the `projects` app, epics, journal and the independent FundBridge and QUAHAXTON workspaces (design approved 24 Nov). A **workstream is a category, not a project.** |
| **Tasks** | Built: workflow statuses, due dates, priority, estimate, workstream, roadmap item link, history, archive. No subtasks or dependencies (parked). |
| **My Schedule** | Built: day, week and month; activities linked to tasks and roadmap items; reminders in the foreground. |
| **Focus sessions and work logs** | Focus sessions built (server-timed, corrections audited). A work-log journal exists only in the parked design. |
| **Evidence and achievements** | Records and API built. Evidence can be added when finishing focus; achievements are listed weekly. There is no dedicated screen. |
| **My Journey** | Not built. Weekly accomplishments and reviews are the beginning of the history it would show. |
| **Insights** | Built: this week (progress, workstreams, accomplishments, review) and trends. |

## 16. Recommended next phases (planning only, not started)

- **Phase A, integration and private release.**
  - Merge this PR after CI.
  - Fix billing and protect `main` with required checks.
  - Deploy per `deployment-plan.md`: HTTPS, trusted proxy, stderr logs, on-host backup and drill.
  - Android install test.
- **Phase B, core personal operating system.**
  - My Vision (a short versioned statement).
  - Goals with measurable milestones, linked to roadmaps, projects and tasks.
  - My Journey: a timeline built from completions, milestones, evidence, reviews and accomplishments.
  - An evidence and achievements screen.
  - Long-term history (monthly and yearly).
- **Phase C, project management.**
  - Decide how the parked `feature/project-domain` comes in (migration renumbering after `planning.0011`, `due_date` reconciliation).
  - Independent FundBridge and QUAHAXTON workspaces, backlogs and epics, subtasks and dependencies, client and startup project tracking.
- **Phase D, learning and career.**
  - Roadmap editing in the app.
  - Course and curriculum tracking: real enrolments entered by the owner, none invented.
  - Skills and career milestones.
  - Application tracking.

## 17. What you need to do

1. **Review the pull request.** Merge only when you're satisfied **and** after CI passes.
2. **Fix GitHub billing** (Settings → Billing and plans), then re-run the PR's checks. Consider requiring `backend` and `frontend` checks on `main`.
3. **Follow `deployment-plan.md`** and `CHARITYOS-DAILY-OPERATIONS-REPORT.md` §12 for hosting, configuration, deployment, account creation (`--with-workstreams`), the go-live gate and the Android install.
4. **Decide on the parked project-domain work** before Phase C. It needs the migration reconciliation described in §6.

## Not done (by instruction)

- No merge, deployment, hosting, domain, timer, or repository-setting change.
- No force-push or history rewrite.
- Nothing ran against `charityos`; one read-only query only.
- `charityos_restore_drill_ae_20261126t075039z`, the seed data and every other database are unchanged.
- Only my own token-labelled copies were dropped.
- The parked worktree and the main checkout are untouched.
