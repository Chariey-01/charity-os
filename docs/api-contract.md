# API contract v1

**Status:** Phase 0 contract; endpoints are not authorized for implementation.

## General rules

- Base path `/api/v1`; JSON `snake_case`; RFC 3339 UTC timestamps; ISO local dates.
- Django session cookie authentication under the same origin. Unsafe methods require CSRF. There are no refresh-token endpoints.
- All object lookup and relationship validation is owner-scoped.
- Errors use `{ "error": { "code", "message", "fields", "request_id" } }`.
- Mutable resources expose a version/ETag where concurrent edits matter.
- Production URL inputs require HTTPS; an explicit development setting may allow loopback/localhost HTTP.

## Endpoint inventory

```text
POST   /auth/login                    POST   /auth/logout
GET/PATCH /me                         GET    /bootstrap

GET/POST /challenges                 GET/PATCH /challenges/{id}
GET/POST /areas                      GET/PATCH /areas/{id}
GET/PUT  /capacity/{local_date}
GET/PUT  /daily-plans/{local_date}
POST     /daily-plans/{date}/items
PATCH    /daily-plans/{date}/items/{id}
DELETE   /daily-plans/{date}/items/{id}
POST     /daily-plan-items/{id}/carry-over

GET/POST /tasks                      GET/PATCH /tasks/{id}
POST     /tasks/{id}/complete        POST /tasks/{id}/skip
POST     /tasks/{id}/reopen          POST /tasks/{id}/archive
POST     /tasks/{id}/transition

GET/POST /roadmaps                   GET/PATCH /roadmaps/{id}
GET      /roadmaps/{id}/tree         POST /roadmaps/{id}/nodes
GET/PATCH /roadmap-nodes/{id}        POST /roadmap-nodes/{id}/move
POST/DELETE /roadmap-nodes/{id}/prerequisites/{prerequisite_id}
POST     /roadmap-nodes/{id}/complete
POST     /roadmap-nodes/{id}/skip    POST /roadmap-nodes/{id}/reopen
GET/POST /roadmap-nodes/{id}/resources
PATCH/DELETE /roadmap-resources/{id}

GET      /sessions/active            GET /sessions
GET      /sessions/{id}              POST /sessions/start
POST     /sessions/{id}/pause        POST /sessions/{id}/resume
POST     /sessions/{id}/finish       POST /sessions/{id}/cancel
POST     /sessions/{id}/corrections  PATCH /sessions/{id}/notes

POST     /evidence                   PATCH/DELETE /evidence/{id}
POST     /accomplishments            GET/PATCH /accomplishments/{id}

GET/POST /sleep-logs                 GET/PATCH/DELETE /sleep-logs/{id}
GET/POST /exercise-logs              GET/PATCH/DELETE /exercise-logs/{id}
GET/POST /meal-logs                  GET/PATCH/DELETE /meal-logs/{id}
GET/PUT  /water/{local_date}         DELETE /water/{local_date}
GET/PUT  /nutrition/{local_date}     DELETE /nutrition/{local_date}
GET/PUT  /daily-reflections/{date}   DELETE /daily-reflections/{date}
GET/PUT  /weekly-reviews/{week_start}
POST     /weekly-reviews/{week_start}/close
DELETE   /weekly-reviews/{week_start}

GET /reports/daily/{local_date}      GET /reports/weekly/{week_start}
GET /reports/challenges/{id}/96-day
GET /analytics/time                  GET /analytics/planned-completion
GET /analytics/roadmaps              GET /analytics/health
GET /analytics/metrics               GET /search
```

## Behavioral contracts

### Planning and tasks

Adding/reordering plan items enforces no more than three current primary outcomes in one locked transaction. An unfinished task may have only one current planned appearance. Carry-over accepts a destination date, marks the source item `carried_forward`, creates exactly one destination item, and appends a planning event atomically. A retry returns that same result. Historical source items are never deleted by carry-over.

Task transitions follow the workflow in "Task statuses" below (any status to any other, through one service, with history). The legacy `planned -> completed|skipped` and reopen endpoints remain as aliases. There is no recurrence contract.

Planned completion responses define numerator and denominator in appearances: completed eligible planned appearances divided by eligible planned appearances.

### Roadmaps

Create/move accepts `node_type` of `section`, `topic`, or `item`. It validates same-owner/same-roadmap parenting, arbitrary nesting, cycles, and sibling ordering; it does not enforce fixed levels. Tasks may link only to items. Tree/read responses include `unmet_prerequisite_ids`, but commands never reject start or completion solely because a prerequisite is unmet.

Roadmap analytics return `completed_eligible_items`, `eligible_items`, `skipped_items`, `progress_ratio`, and a separate `time_invested_seconds` value.

### Sessions

`POST /sessions/start` requires a client-generated session `id`, `area_id`, title/task context, and explicit `is_deep_work` (pre-filled from the task default if applicable). Connectivity is required. The server snapshots historical labels, timezone, and original roadmap ancestry.

Pause requires a client-generated pause `id`. Repeating start/pause with the same owned ID returns the resource. Resume, finish, and cancel lock the session and are idempotent for an already-reached target state; conflicting terminal targets return `409`. Every transition checks the expected version. The partial unique open-session index is authoritative under races.

Finish may atomically record outcome, learning, difficulty, URL/GitHub/note evidence, and optionally complete the task. Cancel freezes duration but ordinary focus analytics exclude it.

Correction is allowed only for terminal sessions, requires a non-empty reason and expected version, validates corrected chronology, applies the change atomically, and appends immutable before/after audit data. Corrections cannot rewrite prior audit rows.

### Health, reporting, and deletion

Timed exercise starts/uses a normal focus session and associates an exercise log; `/exercise-logs` has no pause/resume timer actions. Sleep writes reject overlap with existing sleep intervals; exercise writes reject overlap with existing exercise intervals.

Daily and challenge reports are live-derived and may change after late writes. Closing a reflection/review records only subjective closure; it does not freeze analytics. The 96-day endpoint does not create a snapshot/export.

Health logs and reflections are archived, not deleted (see [Archive, removal and erasure](#archive-removal-and-erasure-implemented-phase-0a)). Permanent deletion exists only as whole-account erasure through the dry-run-first `manage.py erase_user` command.

## Deferred contract surface

No endpoints are defined for life modes, recurrence, upload intents/files/images/photos, offline mutation replay, JWT refresh, report snapshots/exports, or object storage. Search remains a capability, but v0.1 does not promise full-text ranking/index semantics.

## Scheduler endpoints (implemented)

All are owner-scoped, session-authenticated and CSRF-protected. Domain errors return `{"detail", "error": {"code", "message", "fields"}}`: 400 for validation, 404 for another user's or a missing record, 409 for `version_conflict` and `schedule_overlap` (which also lists `conflicts`).

```text
GET   /schedule-entries?start=YYYY-MM-DD&end=YYYY-MM-DD[&include=all]   overlap with local days, max 93 days
POST  /schedule-entries        {id?, title, start_local, end_local, timezone_name?, area?, task?, roadmap_node?, tracking?, notes?, allow_overlap?}
GET   /schedule-entries/{id}
PATCH /schedule-entries/{id}   {expected_version?, allow_overlap?, title?, area?, notes?, outcome?, tracking?, start_local?, end_local?, timezone_name?}
POST  /schedule-entries/{id}/start      {expected_version?, session_id?}
POST  /schedule-entries/{id}/pause      {expected_version?, pause_id?}
POST  /schedule-entries/{id}/resume     {expected_version?}
POST  /schedule-entries/{id}/complete   {partial?, outcome?, learning?, notes?, actual_minutes? | actual_started_at?+actual_ended_at?, complete_task?, expected_version?}
POST  /schedule-entries/{id}/skip       {note?, expected_version?}
POST  /schedule-entries/{id}/cancel     {note?, expected_version?}
POST  /schedule-entries/{id}/reschedule {id?, start_local, end_local, timezone_name?, allow_overlap?, expected_version?} → {original, entry}
GET   /schedule/day?date=YYYY-MM-DD
GET   /insights?period=7d|30d|90d|challenge|year|all
GET   /preferences    PATCH /preferences
POST  /areas/ensure-defaults
```

`start_local`/`end_local` are wall-clock times without an offset, interpreted in `timezone_name` (default: the user's). Entries cannot be deleted; cancel them instead. `/sessions/*` endpoints keep a linked entry in sync, and focus sessions now include `schedule_entry`.

## Task statuses (implemented, migration `planning.0007`)

Tasks use the workflow `backlog`, `todo`, `in_progress`, `in_review`, `blocked`, `done`, `cancelled`. Only `done` (`completed_at`) and `cancelled` (`cancelled_at`, formerly `skipped_at`) carry a timestamp, and both timestamps are read-only.

- `POST /tasks/{id}/transition {status, reason?}` moves a task to any status. Repeating a transition is a no-op that keeps the original timestamp. Every change appends a history event with `from`, `to` and the reason.
- `POST /tasks` and `PATCH /tasks/{id}` accept `status`. Every status change goes through the same transition rules; unknown values return 400.
- **Compatibility:**
  - `complete`, `skip` and `reopen` still map to `done`, `cancelled` and `todo`.
  - The legacy input values `planned`, `completed` and `skipped` are still accepted.
  - Responses include a deprecated read-only `legacy_status` (`planned`, `completed` or `skipped`) for one release.
- **Breaking:** response `status` values and the `cancelled_at` field name changed. See [migrations.md](migrations.md).

## Archive, removal and erasure (implemented, Phase 0A)

Records with history are never deleted through the API (owner decisions 4.1–4.3, 25 Nov 2026).

| Resources | DELETE | Instead |
|---|---|---|
| `/areas`, `/tasks`, `/challenges`, `/roadmaps`, `/roadmap-nodes`, `/roadmap-resources`, `/evidence`, `/accomplishments`, `/sleep-logs`, `/exercise-logs`, `/meal-logs`, `/water`, `/nutrition`, `/daily-reflections`, `/weekly-reviews` | `405`, `error.code = "archive_instead"` | `POST /<resource>/<id>/archive`, `POST /<resource>/<id>/restore` |
| `/daily-plan-items` | `405`, `"remove_instead"` | `POST /daily-plan-items/<id>/remove` (optional `reason`) |
| `/daily-plans`, `/capacities` | `405`, `"edit_instead"` | `PATCH` |
| `/roadmap-prerequisites` | `204` | Prerequisite links are pure structure and stay deletable |
| `/sessions`, `/schedule-entries` | `405` (unchanged) | Cancel, finish or correct |

For a refused DELETE, the `Allow` header leaves out `DELETE`.

**Archiving:**

- Archive and restore lock the row and are idempotent. Restoring a record whose name is now used by an active record answers `409` with code `restore_conflict`.
- Archiving a task appends an `archived` planning event; restoring appends `restored`.
- Archiving a challenge ends its primacy but keeps its status. An archived challenge cannot be made primary.
- Archiving a roadmap node archives its not-yet-archived descendants with the same timestamp. Restoring brings back exactly those. A node under an archived parent cannot be restored: `409`, code `parent_archived`.
- `archived_at` is read-only. Sending it in a create or update is rejected with a field error.

**Lists and working views:**

- Lists accept `?archived=exclude|include|only`, defaulting to `exclude`. Any other value is a `400`. Detail endpoints return archived records too.
- Working views leave archived records out:
  - Today's plan items and tasks;
  - next actions, where an archived prerequisite no longer blocks;
  - roadmap progress;
  - the roadmap tree, unless `?archived=include`;
  - the metrics roadmap list.

**Tracked time is never removed:** Insights, metrics and a node's `time_invested_seconds` still count archived tasks, categories, nodes and health logs.

**Plan items:**

- `remove` moves a current item to `removed` and appends a `removed` planning event.
- A plan item's `state` is read-only. Writing it is rejected with a field error naming `remove` and `carry-over`.

**Deletes blocked by history:** if a delete ever reaches a record that still has history, it answers `409` with code `has_history`. `error.blocking` lists the kinds and counts of what still points at it.

**Erasure:**

- Permanent deletion of an account and everything it owns is `manage.py erase_user EMAIL`. It is a dry run unless `--confirm EMAIL` repeats the address, and it runs in one transaction.
- It refuses, or rolls back, if anything outside the account would change, or if what it removes differs from the plan it showed.
- Django admin cannot delete records.


## Data integrity (implemented, Phase 0B)

**Roadmap trees.** Creating or moving a node validates its parent under the roadmap's row lock. Each of these answers 400 with `error.fields.parent`:
- a parent in another roadmap;
- the node itself or one of its descendants;
- an archived parent;
- a node that is part of a cycle left in old data.

A node's `roadmap` cannot change after creation; this answers 400 on `roadmap`. Two concurrent opposite moves cannot both succeed.

**Focus-session versions.** `expected_version` is a whole number; a string such as `"2"` is accepted. Anything else is a 400 field error. A stale version answers 409 with code `version_conflict` and changes nothing.

**Editing a session (PATCH).**
- Requires `expected_version`, and increments the version.
- An open session may change `title`, `notes`, `outcome` and `learning`; an ended session only `notes`, `outcome` and `learning`.
- `area`, `task`, `roadmap_item` and `is_deep_work` are refused in every state with code `use_correction`.
- Any other field is refused by name.

**Correcting an ended session.** `POST /sessions/<id>/corrections` takes `reason` and `expected_version`, plus any of:
- `started_at`, `ended_at`;
- `area` (one of the user's active categories);
- `task`, `roadmap_item` (the user's own, or `null`);
- `is_deep_work`.

Rules:
- A correction must change something.
- The end may be at most 5 minutes in the future, and a session at most 24 hours long.
- Only the part of each pause inside the corrected window is subtracted.
- Before and after values go to the session's corrections record.
- The linked schedule entry takes the corrected category, label, task and roadmap item in the same transaction, even when it is closed. Insights therefore counts the corrected minutes once, under the corrected category.
- If any step fails, nothing is written.

**Linked schedule entries.** An entry with a linked focus session refuses a *change* of `area`, `task` or `roadmap_node`, with a 400 field error. Re-sending the current value is accepted.

**Duplicates and invalid combinations.**
- Every database constraint is validated before saving: unique (including case-insensitive and conditional), check and overlap constraints. A violation is a 400 field error with a specific message, and nothing is written.
- If two requests race past validation, the database answers. A unique, overlap or foreign-key violation then answers 409 with code `conflict`; a check violation answers 400. Never 500.
- `water` and `nutrition` hold one total per day. A second `POST` for the same `local_date` updates that day's entry (200). If the existing entry is archived, the `POST` is refused.
- Plan items sent without a `position` are appended after the plan's last current item.
- A taken position, or a task already current on a plan, is a 400 field error.
- Carry-over appends after the destination's last item.

**Add to Today.** `POST /roadmap-nodes/<id>/add-to-today` does all of this in one transaction:
1. Reuses the item's open task, creating one only if none exists.
2. Plans it for today (in the user's timezone), after the last item. If it is planned for another day, it carries it over.
3. With `{"start_focus": true, "session_id": <uuid>, "area": <id>}`, also starts the focus session. `area` defaults to the roadmap's category.

Any failure rolls back every write. A repeated request returns the same task and plan item. The response is `{task, plan_item, session, created_task}`.

**Integrity check.** `manage.py check_data_integrity` is read-only and exits 1 on any finding. It reports:
- roadmap cycles;
- cross-roadmap parents;
- links between different users' records;
- linked entries that disagree with their focus session.
