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

Task transitions are `planned -> completed|skipped` and `completed|skipped -> planned` via reopen. There are no active/paused task transitions and no recurrence contract.

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

Health-log and reflection DELETE operations are explicit permanent deletion. Account erasure is a separately protected operation to be specified operationally before external beta; it cascades active user-owned database rows.

## Deferred contract surface

No endpoints are defined for life modes, recurrence, upload intents/files/images/photos, offline mutation replay, JWT refresh, report snapshots/exports, or object storage. Search remains a capability, but v0.1 does not promise full-text ranking/index semantics.
