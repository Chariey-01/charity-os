# CharityOS — Phase 0C independent review and hardening session

**Status.** Phase 0C was reviewed against the running code, not against its report.
- Every Critical, High and Medium finding was fixed on `feature/security-hardening`, along with all Low findings in scope.
- Server-side idempotency for retried creates was added.
- Nothing was merged, pushed or deployed.
- No personal or shared database was modified.

The work stops here for owner review.

Each section separates **facts** (observed or measured in this session) from **assumptions** and **recommendations**.

## 1. Starting point

| | |
|---|---|
| Branch | `feature/security-hardening` |
| Commit | `9dce88d14e0c249c4d5aa165f2c65fc5e583dd22`: the Phase 0C report, on top of code commit `43156f4` |
| Worktree | `/home/user/Progress_tracker-data-safety`, clean apart from its `frontend/node_modules` symlink |
| 0B / 0C boundaries | 0B is `742fa6d..174a3f9` (15 commits). 0C is `174a3f9..9dce88d` (11 commits). Both were confirmed as ancestors of HEAD. |
| Other refs at start (unchanged at the end) | `main` `4ad209d`, `feature/data-safety` `2cbf3a9`, `feature/data-integrity` `174a3f9`, `feature/project-domain` `7b1d03e`, `backup/mobile-scheduler-pre-split` `6df1a35`, `feature/mobile-scheduler` `b9b0b5e` |
| Processes | No other CharityOS session or development process was active |

## 2. Final point

| | |
|---|---|
| Branch | `feature/security-hardening` |
| Final code and docs commit | `cb236c6e6eb913e5d0ffee5f41efc968d86c2d56` |
| This report | The commit after `cb236c6` |

Commits in this session, oldest first. All use Conventional Commits, with no co-author trailers.

| # | Commit | What |
|---|---|---|
| 1 | `2b3cbf0b7cab5742a8cf66ed579017c7e9e7f7fc` | fix(api): a JSON body that is not an object is a 400, not a 500 |
| 2 | `c7cfc13d8fb62fb859656be36ff615a797361632` | fix(reflections): a create that races its own retry answers like a retry |
| 3 | `398e2df3647bb1de2643e9b8e32c98b058de8fc4` | feat(api): replay retried creates that carry an `Idempotency-Key` |
| 4 | `28a134c32cae44650772362b2276e6b8de3be4e2` | feat(frontend): send one `Idempotency-Key` per evidence save |
| 5 | `c7cfcbdee61acd7616d541d55684a4b456f969bb` | fix(users): erasure also removes the account's sign-in sessions |
| 6 | `3ddcd1ac2d0758f66eacf0c5ea61fc9887808e59` | fix(security): keep the admin CSRF token out of sign-in attempt records; exact lockout-boundary tests |
| 7 | `26977cd2a0eb9228b783d8ea78fddc31bcf74cf4` | fix(metrics): refuse a period sent together with its own dates |
| 8 | `6b4cb7d4c1401ab8c02a7c98bd308634ad52a6be` | feat(security): resolve the client address only through trusted proxies |
| 9 | `cb236c6e6eb913e5d0ffee5f41efc968d86c2d56` | docs: idempotency keys, proxy configuration and review follow-ups |

Diff from `9dce88d`: 26 files, +1343 / −18 lines.

## 3. Files inspected

**Reports:**
- `docs/reports/CHARITYOS-PHASE-0B-REVIEW.md`
- `docs/reports/CHARITYOS-PHASE-0C-IMPLEMENTATION-REPORT.md`

**Phase 0C code:**
- `backend/config/settings/base.py`, `production.py`, `test.py`
- `backend/config/security.py`
- `backend/api/views.py`: sign-in, `me`, `OwnedViewSet`, metrics, reflections, tasks, sessions and daily totals
- `backend/api/reflections.py`, `backend/reflections/services.py`, `backend/reflections/models.py`
- `backend/reflections/migrations/0003_reflection_revisions.py`
- `backend/api/serializers.py`: evidence and the constraint check
- `backend/api/exceptions.py`, `backend/api/archive.py`, `backend/api/urls.py`
- `backend/users/management/commands/erase_user.py`

**Phase 0C tests:**
- `test_login_security.py`, `test_security_logging.py`
- `test_reflection_revisions.py`, `test_reflection_migration.py`
- `test_metrics_limits.py`, `test_erase_user.py`

**Third-party source** (django-axes 9.1.0, `.venv`):
- `axes/helpers.py`: client IP, parameter cleansing, client string
- `axes/conf.py`: defaults
- `axes/handlers/database.py`: what is logged and stored

**Frontend:**
- `frontend/src/lib/api.ts`
- `frontend/src/features/focus/FocusBar.tsx`
- `frontend/src/features/profile/ProfileScreen.tsx` (create calls)
- `frontend/src/features/insights/InsightsScreen.tsx` (metrics call)

**Operations:**
- `ops/db/lib.sh`, `ops/db/backup.sh`, `ops/db/restore-drill.sh`
- `docs/api-contract.md`, `docs/migrations.md`, `docs/operations/backup-and-restore.md`

**Migration graph:** loaded offline for all apps, including the parked `feature/project-domain`'s migration list. That list was read from git objects only; the branch was not checked out.

## 4. Review findings

### How the review was done

Two throwaway probe files (kept outside the repository) exercised the running code in this checkout's own test database:
- sign-in, lockout and its expiry, stored attempt data;
- all loggers at DEBUG level;
- CSRF on writes;
- malformed bodies;
- concurrent creates and edits;
- erasure;
- metrics parameters.

Each finding was then traced to its line of code.

### Findings (facts)

| ID | Severity | Finding | Evidence | Status |
|---|---|---|---|---|
| F1 | Medium | A JSON array, string, number or `null` body caused an HTTP 500. Affected: `POST /auth/login` (before authentication), session `PATCH`, `/corrections`, reflection and weekly-review creates, water and nutrition creates. A non-text password raised `TypeError` in the hasher. | `AttributeError: 'list' object has no attribute 'get'` at `api/views.py:86`, `:612`, `:725`, `:453` and `api/reflections.py:39`. `TypeError` in `django/contrib/auth/hashers.py:108`. | Fixed (1) |
| F2 | Medium | Four identical daily-reflection creates sent at once answered `[201, 409 conflict, 409 conflict, 409 conflict]`. A retry racing the original got a generic error instead of the 200 the S8 contract promises. | Probe with 4 threads on a transactional test database | Fixed (2) |
| F3 | Medium, carried from 0B | Generic creates had no retry protection. Three task creates sent at once with the same `Idempotency-Key` stored three tasks. | Probe: `[201, 201, 201]`, 3 rows | Fixed (3, 4) |
| F4 | Low | `erase_user` left the erased account's `django_session` rows behind. They are authentication records of that account. | Probe: 1 session before erasure, 1 after | Fixed (5) |
| F5 | Low | django-axes stored the admin login form's `csrfmiddlewaretoken` in clear in `axes_accessattempt.post_data`. That table is visible in the admin and included in backups. The username and password were masked. | Probe: `username=****… \| password=****… \| csrfmiddlewaretoken=jG8n…` | Fixed (6) |
| F6 | Low (test gap) | The lock expiry was tested only at 16 minutes. Measured: still locked at 14m58s, open at 15m01s. An attempt during the lock is counted by django-axes, so the 15 minutes restart from the latest attempt. The docs did not say so. | Probes on fresh locks | Exact tests added (6); behaviour documented (9) |
| F7 | Low | `/analytics/metrics` silently ignored `start` when a named period was sent. With `start` present, it accepted an unknown period (`period=bogus` → 200). | Probe | Fixed (7) |
| F8 | High as a deployment risk; not exploitable while undeployed | Behind a reverse proxy, `REMOTE_ADDR` is the proxy. All users would then share one lockout per email, and one attacker could keep any account locked for everyone, because each attempt restarts the lock. The 0C operations note said to point axes at the forwarded-for header, which is unsafe if followed literally. | Code review (`get_client_ip_address` falls back to `REMOTE_ADDR`; django-ipware is not installed). Probe: forged `X-Forwarded-For` values were ignored (locked at the sixth attempt). | Fixed (8): resolver, off by default. Configuration documented. |
| F9 | Informational | Production settings trust `X-Forwarded-Proto` unconditionally (`SECURE_PROXY_SSL_HEADER`, pre-existing). That is safe only if Django can be reached solely through a proxy that overwrites the header. | `config/settings/production.py` | Documented in `docs/operations/reverse-proxy.md`; not changed |
| F10 | Informational | There is no general API rate limiting; only sign-in is throttled, by the lockout. | `REST_FRAMEWORK` has no throttle classes | Not changed (new feature) |
| F11 | Informational | `POST /plan-items` has its own create path and is not covered by `Idempotency-Key`. | `api/views.py` `PlanItemViewSet.create` | Documented |

### Reviewed with no defect found (facts)

**CSRF:**
- 403 without a token for sign-in, sign-out, `PATCH /me` and task create.
- No `csrf_exempt`. The only anonymous endpoints are `GET /auth/csrf` and `POST /auth/login`, which enforces CSRF itself. There is no registration endpoint.

**Lockout threshold:** five failures are answered 400, and the sixth is 429. This holds for the API and the admin.

**Enumeration:**
- Identical bodies for a wrong password and an unknown email.
- An identical lockout response for unknown accounts.
- `ModelBackend` hashes even for unknown users.

**Logs.** All loggers were captured at DEBUG during failures, a lockout, an admin failure and a success. None of the records contained the raw email, the raw IP addresses, the wrong password or the right password. django-axes's own messages are cleansed.

**Reflection edits.** Four concurrent `PATCH`es at version 1 answered `[200, 409, 409, 409]`, and exactly one revision was kept. The version check, the revision history and the refusal to overwrite different content all hold.

**Evidence.** Validation uses the stored record merged with the update, on create and on every update, so a partial update cannot bypass it. The 15 tests from 0C cover the paths.

**Metrics.** Ranges are limited to 366 days, with field errors; series are bounded to the window (0C tests).

**Migrations.**
- No conflicts across 0A, 0B and 0C.
- `reflections.0003` depends on `reflections.0002` and `users.0001`, and its reverse refuses while any revision exists.
- No migration names a database; the ops scripts refuse `DATABASE_URL` and need `--database`.

## 5. Changes and why

**1. Object-only JSON bodies (F1).**
- `api/parsers.py` adds `ObjectJSONParser`, which is now the default JSON parser. Any non-object body is a 400 parse error. No endpoint accepts a top-level array; form and multipart parsing are unchanged.
- Sign-in checks that `email` and `password` are text before calling `authenticate()`.
- Fixing it once at the parser covers current and future views that read `request.data.get(...)`.

**2. Reflection create race (F2).** When the period was free at lookup but another request stored it before this insert, the create looks again and applies the usual comparison:
- the same words get 200 with the stored record;
- different words get 409 `already_exists` with `existing_id`.

The other request's row shows up either as the constraint check's 400 or as an `IntegrityError`. Any other error is re-raised.

**3–4. Idempotency keys (F3, Priority B).** `api/idempotency.py` adds `IdempotentCreateMixin` on `OwnedViewSet`. The model is `api.IdempotencyKey`, created by migration `api.0001_idempotency_keys`.

*What counts as a retry:* the same user, the same `Idempotency-Key`, the same endpoint and the same parsed body. The fingerprint is SHA-256 of the method, the path and canonical JSON.
- A retry gets the first successful status and body again, with `Idempotent-Replayed: true`.
- The same key with anything different is 422 `idempotency_key_reused`, and nothing is created.

*Separate actions are never merged.* Requests without a key behave exactly as before. A new action uses a new key.

*Lifecycle:*
- Keys are 1–255 visible ASCII characters; anything else is 400 `invalid_idempotency_key`.
- Keys belong to one user.
- Expired keys (older than 24 hours) are purged each time a key is used.
- A failed create (any non-2xx answer) stores nothing, so the same key can be retried.
- Keys are deleted with the account by cascade, because they hold a copy of the created record.

*Concurrency.* The key row is inserted, inside a savepoint, in the same transaction as the create. A second request with the same key waits on the unique index until the first commits, then replays its answer. If the first rolls back, the second proceeds.

*Frontend.* `post()` takes an optional `idempotencyKey`. The focus finish sheet holds one key for its evidence save. The server does the enforcement; there is no frontend-only workaround.

*Coverage.* Tasks, evidence, accomplishments, meal, sleep and exercise logs, roadmaps and their nodes, categories, challenges and capacities. Not covered: plan items (F11). Endpoints that were already idempotent are unchanged.

**5. Sessions on erasure (F4).**
- `erase_user` finds the account's sessions by decoding them, lists them in the dry-run plan as `sessions.Session`, and deletes them in the same transaction.
- The deletion is checked against the plan.
- Other accounts' sessions are untouched.

**6. CSRF token in attempt records (F5), and lockout boundaries (F6).**
- `AXES_SENSITIVE_PARAMETERS` now also masks `csrfmiddlewaretoken`.
- New tests: locked at 14m58s, open at 15m01s, and an attempt during the lock restarts it.

**7. Metrics (F7).** `period` together with `start` or `end` is a 400 field error naming the date. The bundled client sends only `period`.

**8. Trusted proxies (F8).** `config/proxies.py` resolves the client address for django-axes (`AXES_CLIENT_IP_CALLABLE`) and for the security log. Section 9 has the details.

**9. Docs.**
- API contract and migration ledger updated.
- New `docs/operations/reverse-proxy.md`.
- The unsafe advice in `backup-and-restore.md` was replaced.

Every change was written test-first. Each new test was seen failing before its fix, except the boundary tests for F6, which close a coverage gap. Mutation checks removed a guard, saw its tests fail, then restored the file byte-identically:
- the idempotency mixin: 11 of 16 tests fail without it;
- session erasure;
- the axes client-IP callable.

## 6. Tests and exact results

All of these ran on `cb236c6`. The outputs are in `~/charityos-qa-evidence/20261126_phase-0c-review_cb236c6/`: `backend.txt`, `backend-groups.txt`, `frontend.txt`, `checks.txt`, `restore-drill.txt` and `databases-*.txt`.

| Check | Command | Result | Exit |
|---|---|---|---|
| Backend, full | `pytest -q -p no:cacheprovider` | `501 passed in 175.23s (0:02:55)` | 0 |
| Backup, archive, restore, erasure, admin and migration groups | `pytest -q -p no:cacheprovider` over 15 files: `test_ops_backup`, `test_ops_restore`, `test_ops_migrate`, `test_archive_api`, `test_archive_records_api`, `test_archive_migrations`, `test_task_archive_history`, `test_plan_history_api`, `test_history_restrict`, `test_erase_user`, `test_admin_no_delete`, `test_category_migration`, `test_task_status_migration`, `test_reflection_migration`, `test_idempotency_migration` | `144 passed in 144.40s (0:02:24)`, none skipped | 0 |
| Lint | `ruff check .` | `All checks passed!` | 0 |
| Format | `ruff format --check .` | `129 files already formatted` | 0 |
| Migrations complete | `makemigrations --check --dry-run` | `No changes detected` | 0 |
| Django system check | `manage.py check` | `System check identified no issues (1 silenced).` | 0 |
| Deploy check, production settings (throwaway values) | `manage.py check --deploy` | `System check identified no issues (1 silenced).` | 0 |
| The same with `CHARITYOS_TRUSTED_PROXIES=10.0.0.2` | `manage.py check --deploy` | `System check identified no issues (1 silenced).` | 0 |
| Refuses to trust everything | `CHARITYOS_TRUSTED_PROXIES=0.0.0.0/0 manage.py check` | `ImproperlyConfigured: … would trust every address.` | 1 (expected) |
| Migration graph | Offline loader | `conflicts: {}`; leaves include `api.0001_idempotency_keys` | 0 |
| Frontend lint | `npm run lint` | clean | 0 |
| Frontend typecheck | `npm run typecheck` | clean | 0 |
| Frontend tests | `npm run test` | `Test Files 10 passed (10)`, `Tests 57 passed (57)` | 0 |
| Production build | `npm run build` | `✓ built in 3.15s` | 0 |
| Restore drill | `ops/db/restore-drill.sh --migrate`, from a copy of `charityos_acceptance` | `DRILL PASSED`. Details below. | 0 |

**Restore drill details.**
- **Backup verified:** 35 tables and 499 rows, with every row's fingerprint, the schema and the 34 applied migrations checked.
- **Forward:** 25 migrations applied, including 0A–0C, django-axes and `api.0001`. All 32 data tables kept their exact row counts.
- **Backward:** back to the backup's 34 migrations, with the new tables removed and every row of every data table identical.
- **Forward again:** row counts kept.
- **Cleanup:** the drill's own database was dropped by the drill.

**Test counts.** The backend grew from 436 tests at `9dce88d` to 501. New tests:
- `test_malformed_bodies.py`: 17
- `test_reflection_create_race.py`: 3
- `test_idempotency_keys.py`: 16
- `test_idempotency_migration.py`: 2
- `test_client_ip.py`: 18
- `test_login_security.py`: 4 more
- `test_erase_user.py`: 1 more
- `test_metrics_limits.py`: 4 more

The frontend grew from 56 to 57 tests (`api.test.ts`). No test was deleted or weakened.

## 7. Remaining defects and release blockers

**Facts: still open.**
- List endpoints are unpaginated; `/tasks` returned 120 rows in the 24 Nov probe.
- Two error shapes coexist: DRF field errors and the `{"error": {...}}` envelope.
- There is no general API rate limiting (F10).
- Plan items are not covered by idempotency keys (F11).
- The bundled client sends a key only for evidence. Task creation UI is not on this branch: it is in the parked `feature/project-domain` work.
- `charityos` has never been backed up or drilled.
- The encrypted off-machine copy is on the same disk and predates 0B and 0C.
- CI has never run on this work, because nothing has been pushed.
- `charityos_restore_drill_ae_20261126t075039z` (the verifier's leftover) is still waiting for the owner.

**Release blockers (recommendations):**
- owner review and a merge decision for the 0A–0C stack;
- CI on that stack;
- HTTPS;
- a proxy configured per `docs/operations/reverse-proxy.md`, with `CHARITYOS_TRUSTED_PROXIES` set and the post-deploy check passed;
- log collection;
- a backup and restore drill of the real database before real data goes in.

**Integration note (fact).** The parked worktree's uncommitted task-placement edits touch three files:
- `backend/api/views.py`, the `TaskViewSet` hunk;
- `backend/api/serializers.py`;
- `backend/planning/services.py`.

This session changed other hunks of `api/views.py`: sign-in, `OwnedViewSet`'s base class, and metrics. *Assumption:* those hunks should merge without textual conflict. Behaviour must still be re-tested when the parked work is integrated.

## 8. Database and migration impact

**New migration.** `api.0001_idempotency_keys` creates `api_idempotencykey`, with:
- a user foreign key, `CASCADE`;
- the key, method, path, fingerprint, status and response body;
- `created_at`, indexed;
- a unique constraint on (user, key).

No existing table is altered. It is reversible (`migrate api zero`); the only loss is replay records, which expire after 24 hours anyway.

**Facts:**
- It was applied only in this checkout's own test database and in the drill's own copy, which was dropped.
- It was not applied to `charityos`, `charityos_acceptance` or any other existing database.
- `charityos_acceptance` was read only by the drill's `pg_dump`.
- **Databases, before and after:** the names and OIDs of all 8 databases are identical before and after, and identical to the list taken at the start of the session (`charityos` 16389, `charityos_acceptance` 28660, `charityos_gate` 57361, `charityos_p2` 66466, `charityos_restore_drill_ae_20261126t075039z` 344653, `postgres` 5, `test_charityos` 54475, `test_charityos_p2` 66467).
- **`charityos`** (read-only query): 34 migrations, last applied 24 Nov 16:37 (+03), 0 users. Unchanged.

**The drill's backup.** The drill wrote one new backup under `~/charityos-backups/charityos_acceptance/` (`20261126T162148Z_drill`). Drill backups are never pruned, and nothing was deleted.

## 9. Security implications

**Improved:**
- No unauthenticated 500 on sign-in.
- The admin CSRF token is no longer stored.
- Erasure removes sessions.
- The lock duration is pinned by tests.
- Retried creates can't duplicate records when a key is sent.

**Proxy safety.** Forwarded headers are believed only from proxies listed in `CHARITYOS_TRUSTED_PROXIES`, and only when `REMOTE_ADDR` is one of them.
- The header is read from the right, skipping trusted hops. Entries a client forged are ignored.
- Unusable entries fall back to the proxy address.
- The setting is parsed strictly at start-up and refuses `0.0.0.0/0` and `::/0`.
- With the default empty list, behaviour is unchanged.
- Tests show that one attacker behind a configured proxy no longer locks out the owner, and that forging the header does not escape a lock.

**New data held.** Idempotency records hold a copy of the created record for up to 24 hours. They are per user and are erased with the account.

**Assumptions:**
- The proxy guidance (nginx header directives, Caddy's default handling of client-sent forwarded headers) is from documentation knowledge. No proxy was run in this session. The doc tells the operator to confirm with a post-deploy check.
- That django-axes restarts the lock on an attempt during it was measured on django-axes 9.1.0 only.

## 10. Recommended next phase (recommendations)

1. **Owner review** of 0C and this follow-up, then a decision on merging the stacked `feature/data-safety` → `feature/data-integrity` → `feature/security-hardening`, and on where CI should first run (the GitHub repo is public).
2. **Deployment-readiness items before the private beta:**
   - proxy configuration and its check;
   - log collection;
   - a backup and drill of the real database;
   - an off-machine medium for encrypted copies.
3. **Then the approved Phase 2:**
   - integrate the parked task-placement work against this branch;
   - make the task-create UI send one `Idempotency-Key` per form submission;
   - pagination for list endpoints;
   - one error shape.

## 11. Actions not performed

- Nothing merged into `main` or any other branch.
- Nothing pushed to GitHub; no CI run.
- Nothing deployed or published. No proxy or production infrastructure configured.
- The `charityos` database was not migrated or modified. Only a read-only count query was made.
- No existing personal or shared database was modified. `charityos_acceptance` was only dumped, read-only, by the drill.
- `charityos_restore_drill_ae_20261126t075039z` was not dropped.
- No backup timer installed or enabled.
- No hosting purchased; no domain registered.
- `/home/user/Progress_tracker` was not modified: not its working tree, its index, its checked-out branch or its `.venv`. Its status was read with `--no-optional-locks`.
- The parked `feature/project-domain` worktree was neither checked out nor modified. Its uncommitted task-placement work is intact, and its status and diff were read with `--no-optional-locks`.
- No reset, clean, stash, rebase, amend, force-push or history rewrite.
- No backups, branches, worktrees or user data deleted.
- No other development process stopped.
- No test deleted or weakened.
