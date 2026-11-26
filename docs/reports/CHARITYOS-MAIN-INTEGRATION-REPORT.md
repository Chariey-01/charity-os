# CharityOS — main branch integration and private PWA readiness

**Result (26 Nov 2026, 22:15 EAT): integration is prepared and validated; the merge is blocked.**
- The Phase 0A–0C stack is on `integration/phase-0` and in pull request [#4](https://github.com/Chariey-01/charity-os/pull/4). It passed fresh local validation on the exact code, including a simulation of the CI workflow from a clean export.
- **It was not merged.** GitHub Actions refuses to start any job on this account: *"The job was not started because your account is locked due to a billing issue."* The brief makes passing GitHub CI a condition of merging. Remote `main` therefore still points at `2cb5644`.
- Nothing was deployed. No personal database was touched.

**Owner action needed:** fix the account's billing state (GitHub → Settings → Billing and plans). Then re-run the checks on PR #4, and merge once `backend` and `frontend` both pass.

Sections mark **facts** (observed in this session) separately from **recommendations**.

## 1. Starting point (facts)

| | |
|---|---|
| Remote `main` | `2cb56447459941c0d35a9455b36e09f895b7031b` (tag `v0.1.1`). Read with `git ls-remote`. The cached `origin/main` matched it, so no fetch was needed. |
| Local `main` | `4ad209d4845b0e828ee87ca0fbd1be3947401c8e`: 17 commits ahead of remote `main`, never pushed |
| Working checkout | `/home/user/Progress_tracker-data-safety` on `feature/security-hardening` at `c017ec486119830729d128f7fbce0e570a3aea3a`. Clean, apart from its untracked `frontend/node_modules` symlink. |
| Final hardening commit | `c017ec486119830729d128f7fbce0e570a3aea3a`. The brief gives 39 characters (`…aea3`); that is a prefix of this one commit. |
| Validation commit of the previous session | `cb236c6e6eb913e5d0ffee5f41efc968d86c2d56` |
| Main checkout `/home/user/Progress_tracker` | `feature/mobile-scheduler` `b9b0b5e`, clean. Read only, with `--no-optional-locks`. |
| Parked worktree | `feature/project-domain` `7b1d03e`, with uncommitted task-placement work: 3 modified files and 2 untracked ones. Read only; unchanged at the end. |
| Other sessions and processes | Four peer sessions, all idle. No test, server or build process was running. |

**GitHub (facts):**
- The repository is public, and `main` has no branch protection or rulesets.
- Actions are enabled. The default token is read-only, and first-time contributors need approval to run workflows.
- The repository has no secrets, no environments, no webhooks, and has never had a deployment.

## 2. Exact commits proposed for integration (facts)

`integration/phase-0` is one line of history from remote `main` to the report commit. It contains 83 commits, including three earlier merge commits. The appendix lists them.

| Range | Commits | Content |
|---|---|---|
| `2cb5644..4ad209d` | 17 | Local `main`: mobile-first scheduler, PWA shell, Insights |
| `4ad209d..1ceba99` | 8 | Task-status workflow, plus two design-only documents on project workspaces (no code). `1ceba99` is the approved base of Phase 0. |
| `1ceba99..2cbf3a9` | 19 | Phase 0A: data safety |
| `2cbf3a9..174a3f9` | 14 | Phase 0B: data integrity |
| `174a3f9..c017ec4` | 21 | Phase 0C and its independent review fixes |
| `c017ec4..7f5e8a2` | 3 | Integration commits (below) |
| `7f5e8a2..HEAD` | 1 | This report |

**Integration commits made in this session.** None of them changes application code.

| Commit | What and why |
|---|---|
| `d643435f241667c023245fa1868ea9049ad3bc4d` `ci: test on PostgreSQL 16 with a read-only token` | CI ran PostgreSQL 17, but the runner's `pg_dump` is 16. The `pg_env` fixture then skips every backup and restore test, so CI would have passed without testing Phase 0A's backups. The commit moves to `postgres:16-alpine`, pins `ubuntu-24.04`, and declares `permissions: contents: read`. |
| `2df65a6c1ea5a5dc330a7f8f9bff529db70d8381` `docs(ops): …` | `.env.example` names `CHARITYOS_TRUSTED_PROXIES`. The proxy guide explains IPv4-mapped proxy addresses (section 6). |
| `7f5e8a2a6cf93f03cff41d51fefb93aef1400f89` `docs(ops): …` | Adds `docs/operations/deployment-plan.md` and `docs/operations/private-pwa-release-checklist.md`, and links them from the README |

**Branches.** `integration/phase-0` was created at `c017ec4` and pushed (new branch, no force). The source branches are unchanged: `feature/data-safety` `2cbf3a9`, `feature/data-integrity` `174a3f9`, `feature/security-hardening` `c017ec4`. Local `main` is unchanged at `4ad209d`.

**Not included:**
- `feature/project-domain` `7b1d03e` and its uncommitted task-placement work;
- `b9b0b5e` (a product strategy document, only on `feature/mobile-scheduler`);
- `backup/mobile-scheduler-pre-split`.

**Graph review:**
- **No duplicate commits:** no patch appears twice (patch-id check over every non-merge commit).
- **No missing dependency:** the CI simulation from a clean `git archive` export, with a fresh virtualenv and `npm ci`, passed every step.
- **No deployment experiments:** no Docker, Procfile, or platform configuration was added.
- **No deleted files.**
- **Authentication, archival and erasure** change only in the reviewed Phase 0A and 0C commits. The three small edits outside them are `bootstrap_charityos.py` (scheduler categories, `c5ba705`), `users/admin.py` (no hard delete, `c71cd1f`), and the pytest options (per-checkout test database, `03a2e5f`).

**Wider than Phase 0 (fact and note).** The scheduler (17 commits) and the task-status workflow (6 commits) come in because Phase 0 was built on them (`1ceba99`, as approved). They cannot be separated without rewriting history.

## 3. Final validation (facts)

All of these ran on `7f5e8a2a6cf93f03cff41d51fefb93aef1400f89`. The outputs are in `~/charityos-qa-evidence/20261126_main-integration_7f5e8a2/`.

| Check | Result | Exit | Evidence file |
|---|---|---|---|
| Backend, full: `pytest -q -p no:cacheprovider -rs` | `501 passed`, none skipped | 0 | `backend.txt` |
| Security and authentication (7 files) | `90 passed` | 0 | `backend-groups.txt` |
| Idempotency with concurrency (3 files) | `28 passed` | 0 | 〃 |
| Reflection revisions (3 files) | `21 passed` | 0 | 〃 |
| Archive, restore, erasure, admin (9 files) | `93 passed` | 0 | 〃 |
| Backup, restore, migration, test database (6 files) | `62 passed`, none skipped | 0 | 〃 |
| `ruff check .` / `ruff format --check .` | `All checks passed!` / `129 files already formatted` | 0 / 0 | `checks.txt` |
| `makemigrations --check --dry-run` | `No changes detected` | 0 | 〃 |
| `manage.py check` | `no issues (1 silenced)` | 0 | 〃 |
| `check --deploy`, production settings with throwaway values; also with `CHARITYOS_TRUSTED_PROXIES=10.0.0.2` | `no issues (1 silenced)` (both) | 0 | 〃 |
| `CHARITYOS_TRUSTED_PROXIES=0.0.0.0/0`, and `=proxy.internal` | `ImproperlyConfigured`; start-up refused, as it should be | 1 / 1 | 〃 |
| Frontend: lint, typecheck, `npm test`, build | clean, clean, `57 passed`, `✓ built` | 0 each | `frontend.txt` |
| **CI simulation**: the workflow's steps from a `git archive` export, a fresh venv, `npm ci`, no `.env`, and an empty PostgreSQL 16.15 database | Every step passed. Fresh migrate: 59 applied, 0 unapplied. `501 passed`. Frontend clean. The throwaway database was dropped after its token was checked. | 0 each | `ci-simulation.txt` |
| Upgrade from the Phase 0C schema (`9dce88d`), with rows seeded through that version's API | Forward: 1 migration, every table identical in rows and content. Back: the exact 0C migration set, every row identical. Forward again: identical. An idempotent create works on the upgraded database. | 0 | `upgrade-from-0c-9dce88d.txt` |
| Upgrade from remote `main` (`v0.1.1`) | Forward: 29 migrations, check and integrity OK. Back to `v0.1.1`'s exact set: every table byte-identical except `planning_area` (1→14 rows), which is the documented behaviour of `planning.0006_default_categories` (its reverse is a no-op). Forward again: OK. | 0 | `upgrade-from-main-2cb5644.txt` |
| Restore drill `--migrate` from a read-only dump of `charityos_acceptance` (34 migrations, the same state as `charityos`) | `DRILL PASSED`. Forward: 32 data tables keep their counts. Back: exactly 34 migrations, every row identical. Forward again: OK. The drill dropped its own copy. Backup `20261126T190046Z_drill`. | 0 | `restore-drill.txt` |
| Databases before and after | Names and OIDs identical. `charityos`: 34 migrations, last 24 Nov 16:37 (+03), 0 users, before and after. | — | `databases-*.txt`, `charityos-*.txt` |

**Script faults on record.** The first three runs of my upgrade script failed on faults in the script, not in the code under test:
- wrong seed fields;
- a sort-collation mismatch;
- two `set -e` traps.

Their outputs are kept as `*-attempt-script-fault.txt`. The forward step had already passed in each of them.

The report commit after `7f5e8a2` changes only this file.

## 4. Differences between `cb236c6` and `c017ec4` (facts)

- **One commit,** `c017ec4`, which adds only `docs/reports/CHARITYOS-PHASE-0C-REVIEW-AND-HARDENING-REPORT.md` (+339 lines).
- **No change to:** application code, migrations, security behaviour, dependencies, or configuration.
- **From `cb236c6` to `7f5e8a2`,** `backend/`, `frontend/` and `ops/` are byte-identical. The changes are the CI workflow, `.env.example`, the README and documentation.
- **The earlier evidence** therefore still described the code. The brief nonetheless required fresh validation, and everything in section 3 was re-run on `7f5e8a2`.
- **New tests needed:** none for the application. The CI change is covered by the simulation, which shows the backup and restore tests run and are not skipped.

## 5. Migration graph and compatibility (facts)

- **New migrations.** There are 19 new project migration files, all additions; no existing migration was edited or deleted:
  - `api.0001`
  - `execution.0003`
  - `health.0002`–`0003`
  - `planning.0005`–`0010`
  - `records.0002`–`0003`
  - `reflections.0002`–`0003`
  - `roadmaps.0002`–`0003`
  - `scheduling.0001`–`0002`
  - `users.0002`

  `django-axes` adds `axes.0001`–`0010`.
- **Conflicts:** none. `makemigrations --check` is clean, and `migrate` on an empty database applies 59 migrations.
- **`charityos`.** Its 34 applied migrations all exist unchanged at local `main` (`4ad209d`). Its upgrade to this release is 25 migrations, which is exactly the path the restore drill exercised.
- **The parked branch (read from git objects only).** It adds `planning.0009_task_project_fields`, `planning.0010_planningevent_project` and `projects.0001_initial`, starting from the same `1ceba99`. This branch has *different* `planning.0009` and `0010`. Integrating the parked work later **will need a migration merge or renumbering.** It does not affect this release.

## 6. Security review (facts)

**Idempotency** (`api/idempotency.py`, `api.0001_idempotency_keys`):
- Database uniqueness on (user, key).
- Per-user isolation.
- Fingerprint: SHA-256 of method, path and sorted-key JSON of the parsed body.
- **Concurrency:** the key row is inserted in a savepoint inside the create's transaction, so a concurrent duplicate waits on the unique index, then replays the stored answer.
- **Rollback:** a non-2xx result or an exception discards the key and every write.
- **Expiry:** keys older than 24 hours are purged before each keyed insert.
- **Behaviour:** a matching retry replays, a mismatch is 422, and a request without a key is unchanged. All are covered by tests, including 4-thread races and the expiry boundary, and were re-checked on an upgraded database.
- **The migration:** one new table, with a `CASCADE` user foreign key, a unique constraint, and an index on `created_at`. Its reverse drops only replay records.

**Reverse proxy** (`config/proxies.py`):
- **Empty by default:** confirmed under production settings.
- **Only listed proxies are believed**, and only when `REMOTE_ADDR` is one of them.
- **The header is read from the right**, so client-written entries are ignored.
- **Unusable entries** fall back to the proxy address.
- **Start-up refuses** malformed entries, host bits, and `/0`.
- **Lockout and CSRF:** the 90 security tests pass. They cover the sixth failure locking, the 15-minute boundary, CSRF on sign-in and writes, enumeration, and logs with no secrets.

**New observations in this review:**

| ID | Severity | Observation | Action |
|---|---|---|---|
| S1 | Informational | If the server listens on IPv6, an IPv4 proxy shows up as `::ffff:a.b.c.d` and does not match `a.b.c.d`. This fails safe: shared lockouts, no spoofing. | Documented in `reverse-proxy.md` (`2df65a6`) |
| S2 | Informational | A trusted range that also contains clients lets such a client choose another address in that range. | The guide already forbids listing non-proxy ranges |
| S3 | Low | Expired idempotency keys are purged only when someone sends a key, so copies of created records can outlive 24 hours. They are erased with the account. | Recommendation: purge periodically (for example, in the backup job) |
| S4 | **Medium (operations)** | With production settings, an unhandled exception's traceback is written nowhere: Django's console handler is debug-only, and `ADMINS` is empty. Verified by loading the production settings. | **Deployment prerequisite L1** in `deployment-plan.md` |
| S5 | Informational | Vercel, Render, Cursor and Claude GitHub Apps are installed on the repository (Railway also appeared on September commits). They create check suites that stay queued. The repository has had **zero** deployments, and this session's push created none. | Recommendation: review these installations. If a hosting project is ever connected, a merge into `main` could deploy automatically. |
| S6 | Informational | CI and secrets: the workflow uses no secrets and no `pull_request_target`, and now declares a read-only token | Done (`d643435`) |

`docs/operations/reverse-proxy.md` was reviewed. **Its nginx and Caddy guidance has not been tested against a real proxy.** Deployment stays blocked until the post-deploy check in that guide passes on the target host.

## 7. CI workflow and results (facts)

- **Workflow:** `.github/workflows/ci.yml`, triggered on `push` and `pull_request`, with two jobs:
  - **backend:** a disposable `postgres:16-alpine` service container; ruff, `check`, `makemigrations --check`, `migrate`, `pytest`;
  - **frontend:** `npm ci`, lint, typecheck, test, build.
- **On GitHub:**

  | Run | Event | Result |
  |---|---|---|
  | `45880549537` | push of `integration/phase-0` | `failure`: both jobs "not started because your account is locked due to a billing issue". No runner, no steps. |
  | `45880702207` | pull request #4 | The same |
  | 17 earlier runs (25–29 Sep) | push and pull request | `startup_failure`, 0 jobs. The public run page gives the cause: "recent account payments have failed or your spending limit needs to be increased" |

  **GitHub CI has therefore never run on this repository.** The billing details are not visible to this session's token, which lacks the `user` scope, and that was not widened.
- **Locally:** the simulation of the same workflow passed (section 3). It is evidence, not a replacement.

## 8. Pull request (facts)

[#4 "Integrate Phase 0: data safety, data integrity and security hardening"](https://github.com/Chariey-01/charity-os/pull/4):
- open, base `main`, head `integration/phase-0`;
- GitHub reports it `MERGEABLE` (no conflicts);
- its description states the CI blocker and says not to merge until both jobs pass.

## 9. Final remote `main` (fact)

`2cb56447459941c0d35a9455b36e09f895b7031b`, unchanged. Not merged, because GitHub CI could not run.

**Recommended merge, once CI is green on the PR head:**
- use a merge commit (`gh pr merge 4 --merge`, without `--delete-branch`), then check that `main` points at the merge commit;
- afterwards, set local `main` to match only with a fast-forward (`git merge --ff-only origin/main`). Local `main` is an ancestor, so no history changes.

## 10. Remaining known limitations

**Facts:**
- **Plan items** (`POST /plan-items`) are not covered by `Idempotency-Key` (F11).
- **The task-create screen** is in the parked work and sends no key. Only evidence saves send one.
- **Lists are unpaginated,** and the API returns two error shapes.
- **No general API rate limiting.** Lockouts are per email and IP pair.
- **Reflection revisions** have no screen yet.
- **Reminders are foreground only;** there is no Web Push.
- **Expired idempotency keys** are purged lazily (S3).
- **Production error logging** is missing (S4/L1). PWA defects SW1 and AU1 are open (section 11).
- **`charityos` has never been backed up or drilled.** The encrypted off-machine copy is on the same disk and predates 0B and 0C.
- **`charityos_restore_drill_ae_20261126t075039z`** is still waiting for the owner.

**Recommendation: plan for the parked task-creation work, reviewed separately.**
1. The owner decides how the parked work comes in. Memory rules say not to continue or cherry-pick from that branch without approval.
2. Start from the new `main`, and resolve the `planning.0009`/`0010` collision (section 5) with a merge migration or renumbering. Test it forward and back.
3. Re-test the three overlapping files (`api/views.py` `TaskViewSet`, `api/serializers.py`, `planning/services.py`) against `OwnedViewSet`'s idempotency mixin.
4. The task-create form creates one key when it opens, sends it on every retry of that submission, and starts a new key after success. Test that a double submit and a retried submit each create one task, and that two separate submissions create two.
5. Run the full suite, the migration tests and the restore drill, then review before merging.

## 11. Private PWA readiness (facts and assessment)

**Facts, from the code** (details in `docs/operations/private-pwa-release-checklist.md`):
- **Manifest:** complete, with `standalone`, start URL, scope, colours and shortcuts.
- **Icons:** 192, 512, 512 maskable, SVG and the Apple touch icon.
- **Service worker:** network-first pages, cache-first hashed assets. It never touches `/api/` or `/admin/`, non-GET requests, or other origins.
- **Offline:** the shell opens, and API calls show an offline message.
- **Viewport:** safe-area insets handled.
- **HTTPS:** production enforces it, with HSTS.
- **Install:** the prompt is wired into Profile.

**Assessment: not installable yet.** It needs an approved HTTPS deployment. Before the install test:
- fix SW1 (required): the offline shell can be replaced by a cached error page;
- fix AU1 (recommended): an expired session shows error toasts instead of sign-in.

The Android steps are 4.1–4.11 in the checklist. **CharityOS must not be called downloadable until steps 4.1–4.5 pass on a deployed HTTPS site.** It is a PWA, not an APK.

## 12. Deployment prerequisites (recommendations)

These are from `docs/operations/deployment-plan.md` (go-live gate), in order:
1. Fix GitHub billing, get CI green, merge PR #4. Recommended: protect `main` with required `backend` and `frontend` checks (a repository setting; not changed here).
2. Owner approval of hosting, domain and cost.
3. L1: error logging to stderr, with a test.
4. SW1 (and AU1).
5. Serve `frontend/dist` and `/static/` from one HTTPS origin in front of gunicorn (Django does not serve the frontend). Use PostgreSQL 16, and set every `POSTGRES_*` variable explicitly: `DATABASE_URL` is ignored.
6. Configure the proxy and pass the post-deploy check (`CHARITYOS_TRUSTED_PROXIES`).
7. Collect logs and set alerts.
8. Back up and pass a restore drill on the host before real data goes in. Choose an encrypted off-machine location. The backup timer needs separate approval.
9. Run migrations only through `ops/db/migrate-with-backup.sh`. Migrating the personal `charityos` database needs separate approval and its own drill first.
10. Android install test 4.1–4.11.

## 13. Actions not performed (facts)

**Database and data:**
- `charityos` was not migrated, modified or backed up. Only three read-only queries were made: its applied migrations, and its counts before and after.
- No personal or shared database was modified. `charityos_acceptance` was only dumped, read-only, by the drill.
- `charityos_restore_drill_ae_20261126t075039z` was not dropped.
- The only databases created were throwaway ones: `ci_sim_…`, `upgrade_test_…` (×5 runs), the drill copy, and pytest's per-checkout test databases. Each was created by this session and dropped after its owner token was checked.
- No backup timer was installed. No backups or user data were deleted.

**Repository and hosting:**
- No merge into `main`. No deployment, hosting purchase, domain, or account created.
- No change to GitHub billing, repository settings or branch protection.
- No force-push, reset, clean, stash, rebase, amend or history rewrite. No branch, worktree or backup deleted.
- `/home/user/Progress_tracker` was not modified (read with `--no-optional-locks`).
- The parked `feature/project-domain` worktree and its uncommitted task-placement changes were not modified (read with `--no-optional-locks`; its migrations were read from git objects).

**Tests:**
- No test was weakened, skipped or deleted.

## Appendix: every commit on `integration/phase-0`, oldest first

**Local main: mobile-first scheduler (merged 24 Nov, never pushed)** (`origin/main..4ad209d`, 17 commits)

- `4f99904` chore: land pending completion-pass work as scheduler baseline
- `a0da0be` docs: add mobile scheduler architecture audit and design
- `c5ba705` feat(scheduling): add ScheduleEntry domain model and lifecycle services
- `b8c6452` feat(api): expose schedule entry, Today and preference endpoints
- `8bcb932` feat(insights): derive schedule, focus, health and challenge history
- `347e225` feat(api): report the linked schedule entry on focus sessions
- `abd6e9c` feat(frontend): add typed API client, timezone helpers and test fixtures
- `f4a4616` feat(frontend): add calendar layout, lifecycle hooks and reminder logic
- `99034f6` feat(frontend): replace the dashboard with a mobile shell, Today and activity sheets
- `e9a1b3f` feat(frontend): add the Schedule tab with day, week and month calendars
- `c9356c4` feat(frontend): keep the focus timer reachable with a persistent focus bar
- `7af65ab` feat(frontend): add Insights with accessible charts and gentle milestones
- `51f48d9` feat(frontend): manage categories and foreground reminders from Profile
- `e7c3168` feat(pwa): make CharityOS installable with an offline app shell
- `da49671` docs: document the scheduler, reminders, limits and acceptance run
- `6a1a1f9` fix(categories): never re-create a default category the user archived
- `4ad209d` merge: integrate the mobile-first scheduler from feature/mobile-scheduler

**Task-status workflow and project-workspaces design docs (Phase 0 base)** (`4ad209d..1ceba99`, 8 commits)

- `3f43d6a` docs: propose personal project workspaces architecture
- `53286fd` docs(projects): record approved decisions and verify the proposal against main
- `f1cf93a` feat(frontend): accept workflow task statuses alongside legacy ones
- `03739d5` feat(planning)!: migrate tasks to the backlog-to-done status workflow
- `31bd041` feat(planning): generalise task transitions across the workflow
- `211e929` fix(api): route task status writes through the transition service
- `a9787a5` docs: add a migration ledger and document the task status workflow
- `1ceba99` merge: integrate the task status workflow (phase 1) into project workspaces

**Phase 0A: data safety** (`1ceba99..2cbf3a9`, 19 commits)

- `03a2e5f` test(config): give each checkout its own test database
- `f93c84b` feat(ops): add verified PostgreSQL backups with retention
- `7b4adeb` feat(ops): restore backups only into new databases and add a restore drill
- `ba22611` feat(ops): back up before running migrations
- `41e8173` docs(ops): document backup, restore and the restore drill
- `f1b9cf2` feat(planning): record task archive and restore in task history
- `d50caf0` feat(api)!: archive categories, tasks and challenges instead of deleting them
- `ddd4efe` feat(db): add archived_at to roadmaps, records, reflections and health logs
- `ffef57b` feat(api)!: archive roadmaps, evidence, reflections and health logs instead of deleting them
- `c41491b` feat(planning)!: remove plan items through history and stop deleting plans
- `bc3f930` fix(db): restrict deletion of history-bearing relations
- `ff73963` fix(api): report deletes blocked by history as 409
- `c71cd1f` fix(admin): remove hard-delete from Django admin
- `f904f65` feat(users): add a dry-run-first erase_user command
- `5a80dd2` docs: record the Phase 0A data-safety contract and migration ledger
- `7c48f59` fix(ops): make the migration wrapper prove it migrates the database it backed up
- `37e0efe` fix(ops): require an explicit database for migrate-with-backup
- `742fa6d` docs(reports): sign off Gate 0A
- `2cbf3a9` fix(ops): keep drill evidence and reserve the test database namespace

**Phase 0B: data integrity** (`2cbf3a9..174a3f9`, 14 commits)

- `74cc99c` fix(roadmaps): reject parent cycles and cross-roadmap parents
- `3cc9557` fix(execution): compare session versions as numbers and answer conflicts with 409
- `3aa02b4` fix(api): make focus-session edits version-aware and keep attribution out of PATCH
- `3edba23` merge: bring the Gate 0A follow-up fixes into Phase 0B
- `a2f2008` feat(execution): correct session attribution and times through the audited service
- `2729e1b` fix(scheduling): keep a linked entry's attribution with its focus session
- `0b9252b` fix(api): answer duplicate and conflicting saves with field errors, never 500
- `d4c72be` feat(roadmaps): add a roadmap item to Today, and optionally start focus, atomically
- `99f39a4` feat(frontend): use the atomic Add to Today for roadmap items
- `ca36488` feat(ops): add a read-only check_data_integrity command
- `7e893a0` docs: record the Phase 0B data-integrity contract
- `16acce9` docs(reports): add the Phase 0B implementation report
- `df16ea7` fix(api): begin focus sessions only through /sessions/start
- `174a3f9` docs(reports): record the Phase 0B review and acceptance

**Phase 0C: security hardening and its review fixes** (`174a3f9..c017ec4`, 21 commits)

- `6f52c2e` fix(api): enforce evidence URL rules on every update
- `50be4c2` fix(api): bound the metrics range and query only its window
- `1dd4008` test(api): keep every Insights period valid for the bounded metrics endpoint
- `9975cd4` feat(db): add reflection versions and a revision history table
- `e0cf687` feat(api): keep reflection history on every edit and make creates idempotent
- `fe5660f` feat(frontend): edit today's reflection with its version instead of posting a new one
- `0a3641f` feat(auth): lock out repeated failed logins and require CSRF on login
- `5e4f2d4` feat(config): log security events without secrets or raw emails
- `3f1c6a2` test(frontend): show the lockout message after repeated failed sign-ins
- `43156f4` docs: record the Phase 0C security contract, migrations and operations
- `9dce88d` docs(reports): add the Phase 0C implementation report
- `2b3cbf0` fix(api): answer 400, not 500, when a JSON body is not an object
- `c7cfc13` fix(reflections): a create that races its own retry answers like a retry
- `398e2df` feat(api): replay retried creates that carry an Idempotency-Key
- `28a134c` feat(frontend): send one Idempotency-Key per evidence save
- `c7cfcbd` fix(users): erasure also removes the account's sign-in sessions
- `3ddcd1a` fix(security): keep the admin CSRF token out of sign-in attempt records
- `26977cd` fix(metrics): refuse a period sent together with its own dates
- `6b4cb7d` feat(security): resolve the client address only through trusted proxies
- `cb236c6` docs: idempotency keys, proxy configuration and review follow-ups
- `c017ec4` docs(reports): Phase 0C independent review and hardening session

**Integration (this session)** (`c017ec4..7f5e8a2`, 3 commits)

- `d643435` ci: test on PostgreSQL 16 with a read-only token
- `2df65a6` docs(ops): list CHARITYOS_TRUSTED_PROXIES and IPv4-mapped proxy addresses
- `7f5e8a2` docs(ops): add the deployment plan and private PWA release checklist

**This report** (`7f5e8a2..HEAD`, 1 commit)

- docs(reports): main integration and private PWA readiness
