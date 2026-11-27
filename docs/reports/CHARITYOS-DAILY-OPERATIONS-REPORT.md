# CharityOS — daily operations and private release readiness

**Summary (26 Nov 2026, ~00:10 EAT on 27 Nov).** On branch `feature/daily-operations` you can now do all of this, verified in a real browser on a copy of the seeded data:
- capture tasks with only a title;
- organise them by workstream, priority, due date and estimate;
- schedule them and focus on them, recording real time;
- complete, defer and archive them;
- see truthful daily and weekly progress, with charts, and review the week.

The three known release blockers are fixed:
- production error logging;
- the offline shell being replaced by error pages;
- expired sessions.

**What is not done:**
- The branch is **not pushed or merged**. This brief did not authorise either.
- Nothing is deployed, and the app has not been installed on a phone.
- GitHub Actions still refuses to start jobs: "account is locked due to a billing issue".
- My Vision, My Projects, My Journey, Goals and the FundBridge and QUAHAXTON workspaces were **not built**. Section 13 explains why.

Each item below is labelled **[Verified]** (complete and verified), **[Partly verified]** (implemented but not fully verified), **[Not implemented]** or **[Blocked]** (blocked by an external action).

## 1. Starting and final commits

| | |
|---|---|
| Start | `main` = `e17a153791aab356944e57f298223caab87404ed`, your merge of PR #4 (22:28 EAT). Its tree is byte-identical to the validated integration head `f21a6ca`. |
| Final code and docs | `2d64ae2e499c61e8c5895857826a33e48e2b4c97`. This report is the commit after it. |
| Baseline on `e17a153` | Backend `501 passed`; frontend lint, typecheck, `57 passed`, build: all exit 0 (`~/charityos-qa-evidence/20261126_daily-ops_e17a153/baseline-*.txt`) |

## 2. Branch

`feature/daily-operations`, created from `origin/main` with `--no-track`, in `/home/user/Progress_tracker-data-safety`. It holds 14 commits (15 with this report), with no co-author trailers and no history rewritten.

**Not pushed.** The remote has no branch of this name.

## 3. Files and domains changed

56 files, +4430 / −144 lines.

| Domain | Files |
|---|---|
| Error logging | `backend/config/error_logging.py` (new), `config/settings/base.py` |
| API errors | `backend/api/exceptions.py` |
| Tasks | `planning/models.py`, `planning/migrations/0011_task_due_date.py`, `planning/services.py`, `api/serializers.py`, `api/views.py` |
| Progress | `planning/progress.py` (new), `api/views.py`, `api/urls.py`; `scheduling/insights.py` (shared category-minutes helper) |
| Workstreams | `planning/categories.py`, `api/schedule_views.py`, `users/management/commands/bootstrap_charityos.py` |
| PWA | `frontend/public/sw.js` |
| Frontend | `lib/api.ts`, `lib/tasks.ts`, `lib/charts.ts`, `lib/types.ts`, `app/*`, `features/tasks/*` (new), `features/insights/{Chart,InsightsScreen,WeeklyProgress,WeeklyReview,progressData}`, `features/today/TodayScreen.tsx`, `features/profile/ProfileScreen.tsx`, `features/focus/FocusBar.tsx`, `index.css` |
| Tests | Backend: `test_error_logging`, `test_auth_error_codes`, `test_task_due_dates`, `test_progress`, `test_workstreams` (new); `history_graph`, `test_history_restrict` (adjusted, section 8). Frontend: `sw.test`, `lib/*.test`, `TasksScreen.test`, `WeeklyProgress.test`, `FocusBar.test` (new); `App.test`, `InsightsScreen.test`, `ProfileScreen.test` (extended) |
| Docs | `api-contract.md`, `migrations.md`, `operations/deployment-plan.md`, `operations/private-pwa-release-checklist.md` |

## 4. Features completed

| Feature | Status |
|---|---|
| **Task capture from Today and from Tasks.** Only a title is needed; one Idempotency-Key per capture, so a resend never creates a second task. | [Verified] |
| **Full task form.** Workstream, priority, due date (Today, Tomorrow, Next week or any date), estimate, status, notes, optional roadmap milestone item. | [Verified] |
| **Tasks tab.** Overdue, Today, Upcoming, No date and Backlog groups; workstream filter; done in the last 7 days; archive with restore. | [Verified] |
| **Acting on a task.** Mark done or reopen; start focus; schedule; defer (tomorrow, next week, a date, backlog); edit; archive. Starting focus on a task scheduled today starts that activity, so the time belongs to the plan; otherwise it opens a free focus session and asks for a workstream if the task has none. Finishing focus can also complete the task, only when ticked. | [Verified] |
| **Workstreams.** Learning and Education, Startup and Entrepreneurship, Client Work and Income, Career and Professional Development, Personal Development and Personal Administration, as ordinary categories: rename, recolour, archive in Profile. Opt-in from Profile or `bootstrap_charityos --with-workstreams`. No fake tasks or course names were seeded. | [Verified] |
| **Today dashboard.** Tasks for today (overdue, due today, in progress, high priority) with an overdue count, this week's task progress, the existing schedule, "Up next" and activities. | [Verified] |
| **Overall progress.** Done, remaining, overdue, due today, and % = done / (done + open), excluding archived and cancelled tasks. | [Verified] |
| **Weekly progress.** Planned workload, completed, outstanding, %, unplanned completions shown separately, comparison with the previous week when it had a plan; definitions shown in the app. | [Verified] |
| **Workstream charts.** Two separate donuts, completed tasks by workstream and tracked time by workstream, each beside ranked figures, with a table view and keyboard and tap read-out. | [Verified] |
| **Roadmap progress** (completed milestone items per roadmap). | [Verified] (shown in the e2e run) |
| **Weekly accomplishments** with date range and week navigation: completed tasks, milestones reached, focus time, roadmaps advanced, learning counts, evidence, achievements. | [Verified] |
| **Historical accuracy.** A past week is reconstructed as it stood at its end from append-only events (status, due date, archive, plan carry-overs, schedule moves). Later reopening, archiving or deferral never changes it. Mutation-checked. | [Verified] |
| **Weekly review.** Planned, completed, not completed; time and attention per workstream; "What went well?", "Obstacles and lessons" and "Next week's priorities" saved with version history; unfinished work moves only on an explicit "Carry to …" tap. | [Verified] |

## 5. Existing features repaired

| Defect | Fix | Status |
|---|---|---|
| L1: a 500's traceback was written nowhere in production | `django.request` and `django.security` errors go to stderr through a redacting formatter (emails masked; password, token, secret, session, CSRF, API-key and Authorization values replaced; the path without its query string) | [Verified] by tests that trigger a real 500 |
| AU1: an expired session showed error toasts until a reload | `not_authenticated` error code; the app returns to sign-in with an explanation, no reload. A CSRF failure (`csrf_failed`) is retried once with a fresh token and never signs you out. | [Verified] (unit tests, and in Chrome by deleting the session server-side) |
| SW1–SW3: the offline shell could be replaced by an error page; assets piled up; the first offline launch failed | The service worker adopts a new shell only after all its assets load; serves the last good shell on errors; prunes old assets; pre-caches on install | [Verified] (8 tests; 6 fail against the old worker); offline launch in Chrome |
| The CSRF reason was hidden by the new friendly message (my own regression, found in the e2e run) | Kept as `error.reason` and in the security log | [Verified] |
| An app opened offline needed a manual "Try again" | It retries on the `online` event | [Verified] (test and Chrome) |
| A task focused from the task sheet left its scheduled activity "Up next" | Start focus uses today's scheduled activity (section 4) | [Verified] |
| "1 tasks", "1h 46m min" | Singular counts and a plain label | [Verified] |

## 6. Database and migration changes

**One migration, `planning.0011_task_due_date`:**
- a nullable `planning_task.due_date`;
- `due_changed` added to the PlanningEvent choices (choices only; there is no DB constraint on event types).

It is reversible, but the reverse drops the column. Its definition is identical to the parked `feature/project-domain` branch's `due_date` (that branch's `planning.0009`). When the parked work is integrated, drop its `AddField` and renumber its `0009`/`0010` after `0011` (`docs/migrations.md`).

Nothing else changed in the schema. No data migration runs, and no existing data is rewritten.

## 7. Test commands and results

All on `2d64ae2e499c61e8c5895857826a33e48e2b4c97`. Evidence is in `~/charityos-qa-evidence/20261126_daily-ops_final/`.

| Command | Result | Exit |
|---|---|---|
| `backend/: pytest -q -p no:cacheprovider -rs` | `540 passed`, none skipped (501 at baseline + 39 new) | 0 |
| `ruff check .` / `ruff format --check .` | `All checks passed!` / `136 files already formatted` | 0 / 0 |
| `manage.py makemigrations --check --dry-run` | `No changes detected` | 0 |
| `manage.py check`; `check --deploy` (production settings, throwaway values) | `no issues (1 silenced)` (both) | 0 / 0 |
| `frontend/: npm run lint`, `typecheck` | clean, clean | 0 / 0 |
| `npm run test` | `Test Files 16 passed`, `Tests 95 passed` (57 at baseline + 38 new) | 0 |
| `npm run build` | `✓ built` | 0 |
| `ops/db/restore-drill.sh --migrate` (read-only dump of `charityos_acceptance`) | `DRILL PASSED`: 34 → all migrations, back with every row identical, forward again; the drill dropped its copy (backup `20261126T205735Z_drill`) | 0 |
| End-to-end, Chrome headless, 390×844 touch, America/New_York, against a restored copy of the seeded data (`e2e-results.txt`) | `SUMMARY 17/17 passed`, 0 console errors | 0 |

**Mutation checks.** Each guard was broken on purpose, its tests were seen failing, and the file was restored byte-identically:
- status history ignored: 1 progress test fails;
- due-date history ignored: 1 fails;
- due-change events not written: 3 fail;
- the previous service worker: 6 of 8 SW tests fail.

## 8. Tests that failed or could not run

- **GitHub Actions [Blocked]:** every job is refused for the billing lock (most recently run `45883860011`, on your merge). **No GitHub CI result exists for any of this work.** The local results above are not GitHub CI.
- **`test_history_restrict` failed after `planning.0011`** (1 of 540). It compared every column of old-shape rows after migrating forward, so any new column failed it. It now compares the columns the old rows had (still required unchanged both ways) and also asserts that the new column holds only NULLs. This is not a weakening: the claim being tested ("old data survives") is the same.
- **Two existing frontend tests changed with the product:** the navigation now has six sections (`App.test`), and the old Insights charts moved to `#/insights?view=trends` (`InsightsScreen.test`). Their assertions are otherwise unchanged.
- **The first two e2e runs failed, and the evidence is kept:**
  - Run 1: every sign-in was refused, "Origin checking failed": my preview proxy's origin wasn't in `DJANGO_CSRF_TRUSTED_ORIGINS`. That was a setup issue, but it exposed the hidden CSRF reason (fixed).
  - Run 2: 4 failures. Two were ambiguous selectors in my script and one followed from those. The fourth exposed the offline auto-retry gap, and the run's screenshots showed the scheduled-activity inconsistency (both fixed).
  - Run 3 passed 17/17.
- **Not run:** an Android device, an HTTPS deployment, a real reverse proxy, and the post-deploy proxy check. Nothing is deployed.

## 9. Screens and workflows verified in a browser

Chrome 151 headless, against a production build (`vite preview`) and Django on a **restored copy** of `charityos_acceptance` (existing seed data, not reset). Each copy was dropped afterwards, after its owner token was checked. Screenshots are in `~/charityos-qa-evidence/20261126_daily-ops_e17a153/e2e-screens/`.

1. Sign in; add the six workstreams.
2. Capture a task from Today (title only).
3. Assign it to Learning and Education, high priority, due today, 30 min.
4. Schedule it (quick add pre-filled, linked to the task).
5. Start focus from the task (starts the scheduled activity), about 40 s, then finish it with "Also mark the task complete".
6. The task is done and listed under "Done in the last 7 days". Today shows "100% · 1 of 1 planned done" and the activity as done.
7. Insights shows 100% with its denominator, the workstream donut, the time donut (with the seed data's own activities beside the new minute), and the accomplishment listed.
8. The previous week shows "No tasks were planned" (unchanged).
9. An overdue task appears on Today ("1 overdue"), and deferring it to tomorrow removes it from today's list.
10. The weekly review lists the completed task and saves a reflection.
11. No horizontal overflow at 360, 390 and 430 px on Today, Tasks, Insights and Review.
12. Offline: the cached shell opens and shows the offline screen, then recovers by itself when back online.
13. After deleting the session server-side, the next navigation returns to sign-in with "Your session has ended", without a reload.

## 10. Remaining defects and limitations (facts)

- **Distribution follows the current workstream.** Completed-task distribution uses each task's current workstream: moving a done task to another workstream moves it in past charts. Time distribution uses snapshots and does not move.
- **Weekly reviews assume a Monday week start** (a database rule from earlier work). Your account uses Monday.
- **Offline shows a screen, not data.** Offline, the app opens to an offline screen rather than your data: API data is deliberately never cached.
- **Plan items have no retry protection.** `POST /plan-items` is not covered by Idempotency-Key.
- **API rough edges remain:** lists are unpaginated, there are two error shapes, there is no general API rate limiting, and 404s still use DRF's plain shape.
- **No projects or goals yet.** Tasks can't be assigned to a goal or project, because those domains don't exist on this branch (section 13).
- **Separate add buttons on Today.** The floating "+" there still adds a scheduled *activity*; tasks are captured with the inline box. On the Tasks tab, "+" adds a task.

## 11. PWA readiness

The code is ready for an install test. The manifest, icons, service worker (fixed), offline shell, HTTPS settings, session handling (fixed) and mobile layouts (360–430 px checked) are all in place.

**It is not installable or "downloadable" yet [Blocked]:** it needs an HTTPS deployment and the Android test in `docs/operations/private-pwa-release-checklist.md` §4. It is a PWA, not an APK.

## 12. What you need to do tomorrow

1. **Review this branch** and decide whether to push it (`git push origin feature/daily-operations`) and open a PR. I was not authorised to push or merge this time.
2. **Fix GitHub billing** (Settings → Billing and plans), so CI can run on that PR. Merge only when `backend` and `frontend` pass.
3. **Choose hosting and a domain** (`docs/operations/deployment-plan.md` §1–2). The current code needs a host where a web server serves `frontend/dist` and `/static/` in front of gunicorn.
4. **Configure** following the plan's §3:
   - `DJANGO_SETTINGS_MODULE=config.settings.production`, a new `DJANGO_SECRET_KEY`;
   - `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your host>`;
   - all five `POSTGRES_*` variables (not `DATABASE_URL`);
   - `CHARITYOS_TRUSTED_PROXIES` once the proxy address is known.
   - Use PostgreSQL 16.
5. **Deploy:**
   - `npm ci && npm run build`;
   - `manage.py collectstatic --noinput`;
   - `ops/db/migrate-with-backup.sh --database <new db>`;
   - start gunicorn with `--access-logfile - --error-logfile -`.
6. **Create your account** on the server:
   `python manage.py bootstrap_charityos --email <you> --display-name <name> --timezone Africa/Nairobi --challenge-name "<name>" --password-env <VAR> --with-workstreams`
7. **Run the go-live gate** (plan §11):
   - `check --deploy`;
   - the proxy check from `reverse-proxy.md`;
   - log collection;
   - a backup and restore drill on the host before real data.
8. **Install on Android:** open the HTTPS address in Chrome, then menu → **Install app**. Run checklist steps 4.1–4.5 (4.6–4.11 when convenient).
9. **Start using it:**
   - capture responsibilities as they come (Today's "Add a task…");
   - add details where useful;
   - schedule or start focus from the task;
   - review the week under Insights → "Review this week".

## 13. Deliberately deferred

| Item | Why | Status |
|---|---|---|
| My Vision, Goals, My Journey | Not present in this codebase. Building them now would create new domains overnight; they are later phases of the approved plan (Phase 3+). | [Not implemented] |
| My Projects, FundBridge and QUAHAXTON workspaces, task assignment to projects and milestones | They exist only in the parked `feature/project-domain` work. You said not to pull it in without approval, and a second Projects domain here would compete with it. Until then, roadmaps (with milestone items) and workstreams cover organising and linking. | [Blocked] on your decision about the parked branch |
| Task-placement and hierarchy (parked uncommitted work) | Not touched, by instruction | [Not implemented] here |
| Pagination, one error shape, rate limiting, plan-item idempotency | Not needed for first personal use; known, in section 10 | [Not implemented] |
| Web Push reminders | Needs a push service; out of scope for tomorrow | [Not implemented] |

## Actions not taken

- No push, merge, deployment, hosting, domain or external infrastructure change.
- No backup timer installed.
- `charityos` was not modified or migrated. This session made one read-only query of it (migration count and users, at the end), and the result is unchanged.
- `charityos_acceptance` was only read: one read-only query of its categories, tasks and roadmaps, and read-only dumps by the restores and the drill.
- `charityos_restore_drill_ae_20261126t075039z` and the other databases are untouched. Names and OIDs are identical to the inventory taken before this work.
- Only databases I created were dropped: three e2e copies and the drill's copy, each after its token was verified.
- `/home/user/Progress_tracker` and the parked worktree were not modified (both read with `--no-optional-locks`). The parked worktree's 3 modified and 2 untracked files are intact.
- No reset, clean, stash, rebase, amend or force-push. No test deleted or weakened.
