# Implementation milestones

Every milestone has a demonstration and test gate. Schema v1 was frozen and Phase 1 foundation work was authorized on 2026-09-25.

## Phase 0 — Architecture review (complete)

- Record the approved Schema v1 decisions and complete entity/relationship/invariant inventory.
- Reconcile architecture, domain, API, risks, and milestone documents.
- Identify contradictions with the unchanged approved PRD.

Exit: an authorized reviewer resolves the recorded PRD contradictions and explicitly authorizes Phase 1. Documentation completion alone does not satisfy this gate.

## Phase 1A — Foundation (authorized, narrowed)

- Same-origin React/Django/PostgreSQL skeleton, CI, custom user, and Django session/CSRF infrastructure only.
- Challenge, areas, daily capacity, seed data, authentication endpoints, and product UI are deferred to later implementation work.

Exit: both applications build and test, the custom user migration is ready, and the frontend reaches the infrastructure health endpoint through the local same-origin proxy.

## Phase 1B — Daily execution (not authorized)

- Tasks with the three-state lifecycle, daily plans, appearance history, three-primary service rule, carry-over audit, capacity, and quick capture.
- Connected-only focus start/pause/resume/restore/finish/cancel, simple idempotent retries, concurrency guard, audited correction, URL/GitHub/note evidence.

Exit: plan → focus → restore → finish → prove works on mobile, including duplicate requests and one-open-session races.

## Phase 1C — Flexible roadmaps (not authorized)

- Variable-depth `section|topic|item` tree, ordering/moves, informational prerequisites, multi-resource nodes, multi-task item links, leaf progress, original-ancestry time attribution.

Exit: nested sections work without fixed-depth validation; progress/skips/time are independently correct.

## Phase 1D — Health and reflection (not authorized)

- Sleep overlap prevention and wake-date attribution; exercise metadata linked to the sole focus timer; meal logs; daily water total; separate nutrition rating; accomplishments and deletable reflections/reviews.

Exit: a full day can be recorded without a second timer or frozen report facts.

## Phase 1E — Live reports and history (not authorized)

- Live daily/weekly/96-day reports, focus/deep-work, appearance-based planned completion, health, and the separate focused-days/primary-outcomes/target-hours/exercise-days/roadmap metrics.
- Simple user-scoped search without launch-time full-text indexes.

Exit: hand-calculated fixtures match timezone snapshots, late records, skips, cancellations, corrections, pauses, and midnight boundaries.

## Phase 1F — PWA and alpha hardening (not authorized)

- Installable shell, safe static caching, explicit connected-only mutation UX, accessibility, observability, database backup/restore drill, same-origin deployment, security/concurrency suites.

Exit: the connected critical journey survives refresh, lock, and multi-tab use; offline mode never claims a timer mutation succeeded.

## Deferred beyond v0.1

Life modes; recurrence; image/file evidence; meal photos; uploads/object storage; full-text indexes; offline mutations; immutable weekly factual snapshots; report snapshot/export infrastructure; background workers/materialized analytics; self-service password recovery (before external testing); formal backup/object retention policy (before external beta); AI, calendar, social, payment, team, and native-app features.
