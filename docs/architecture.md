# CharityOS v0.1 architecture

**Status:** Phase 0 reviewed architecture; Phase 1 foundation authorized 2026-09-25.

## System shape

CharityOS v0.1 is a same-origin modular monolith: a React/TypeScript PWA and a Django/DRF backend are served under one origin, with PostgreSQL as the system of record. Django session authentication and CSRF protection are used. There is no JWT refresh-token infrastructure, object storage, queue, event bus, or separate search service in v0.1.

Backend domains are `users`, `challenges`, `planning`, `roadmaps`, `tasks`, `sessions`, `evidence`, `health`, `reflections`, and read-only `analytics`. Cross-domain writes use explicit transactional services. Business invariants do not depend on signals.

## Authentication and privacy

- Email/password login uses Django's custom user model, server-side session cookies (`Secure`, `HttpOnly`, `SameSite=Lax` in production), CSRF tokens, TLS, and same-origin routing.
- Private alpha has no public signup or self-service password recovery. Staff perform manual resets. The user model and login identifier must permit a later recovery flow without schema replacement.
- Every query and relationship mutation is scoped to the authenticated owner; client-supplied ownership is ignored.
- Full account erasure deletes active user-owned database data. Backup and object-storage retention policy is deferred until external beta.
- Health logs and reflections support explicit permanent deletion; no trash system is added.

## Roadmaps and work

`RoadmapNode` is an adjacency-list tree of arbitrary depth with types `section`, `topic`, and `item`. Sections may contain sections. Items are measurable learning leaves; an item is not an executable `Task`. Multiple tasks may link to one roadmap item, and a node may have multiple `RoadmapResource` rows.

Prerequisites are informational in v0.1: the API reports unmet prerequisites but never blocks work or completion. Roadmap progress is completed eligible leaf items divided by eligible leaf items. Skipped leaves are excluded from that denominator and reported separately. Time invested is a separate focus-session metric.

Tasks have only `planned`, `completed`, and `skipped` states. Reopening returns a task to `planned`; active/paused belong only to `FocusSession`. An unfinished task can have at most one current planned appearance. Historical plan items remain visible. Carry-over marks the source occurrence as carried forward, creates one destination occurrence, and appends a planning-history event.

## Timer and exercise

The server owns one timer state machine: `FocusSession` plus `SessionPause`. Start, pause, resume, finish, and cancel require connectivity. The database retains:

```sql
UNIQUE (user_id) WHERE status IN ('active', 'paused')
```

Area is required at session start. The session snapshots area label, timezone, title, selected deep-work classification, and original roadmap ancestry. Historical analytics default to those historical labels and original ancestors.

Task deep-work classification is only a start-form default; each session stores the explicit selection. Cancelled sessions retain duration but are excluded from normal focus analytics.

Finished sessions may be corrected through an explicit service that requires a reason and appends an immutable `FocusSessionCorrection` containing before/after values. Corrections never silently overwrite history.

Exercise does not have a second live timer. Timed exercise uses `FocusSession`; an `ExerciseLog` stores health metadata and may reference the session. Manually entered exercise remains a log, not a timer state machine. Exercise logs may not overlap other exercise logs.

### Timer idempotency

No `sessions_command_receipt` table is proposed. For the private alpha, clients generate the UUID for a new session and pause interval. Retrying creation with the same UUID returns the same owned resource. Resume/finish/cancel are locked, version-checked state transitions and repeat requests return the already-reached state without applying payload twice. The one-open-session partial unique index remains the final race guard. This is materially simpler than retaining request/response receipts while still covering double taps and lost responses.

## Time and analytics

Instants are UTC. Day-scoped records snapshot their IANA timezone and local date. Existing daily plans keep their stored date/timezone after a user timezone change. Sleep is reported using its creation-time timezone snapshot and `wake_local_date`. Weeks run Monday through Sunday; the initial user's `week_starts_on` is `1` (Monday), with Sunday as close/review day.

Daily and 96-day reports are live-derived. Closing a reflection does not freeze facts, and late data may change reports. Weekly factual snapshots and report-snapshot tables are deferred.

Published metrics remain separate:

- roadmap progress: completed eligible leaf items / eligible leaf items, plus skipped count;
- planned completion: completed eligible planned appearances / eligible planned appearances;
- focus time and deep-work time from eligible completed sessions, excluding cancelled sessions;
- focused days, primary outcomes completed, target-hour adherence, exercise days, and roadmap progress.

There is no composite productivity or consistency score. Search starts with indexed relational filters and simple case-insensitive matching; full-text indexes are deferred.

## PWA and connectivity

The service worker may cache the application shell and static assets. It must not cache authentication responses or private API data by default. A running timer may continue to render from its last server timestamp while offline, but all timer mutations are disabled until connectivity returns. Offline mutation queues are deferred.

## URL and evidence policy

Alpha evidence kinds are `url`, `github`, and `note`. File/image evidence, meal photos, uploads, and object storage are deferred. Production evidence and roadmap-resource URLs require HTTPS. Development may allow loopback/localhost HTTP only.

## Deployment and verification

Production uses same-origin routing to Django and PostgreSQL. Tests must cover PostgreSQL constraints, ownership/IDOR, timer concurrency and retries, corrections, timezone boundaries, non-overlapping sleep/exercise, carry-over, roadmap cycles/progress, and analytics denominators.

The authoritative entity/invariant inventory is in `schema-v1-decision-record.md`. Phase 1 authorization is limited to the foundation and custom User model; the remaining domain entities are not authorized for implementation.
