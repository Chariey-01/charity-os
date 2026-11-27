# CharityOS — daily operations: integration review and pull request

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

Opened from `feature/daily-operations` against `main`: see the PR link recorded in the pull request itself and in the commit that adds it to this report. It has not been merged.

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
