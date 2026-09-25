# Schema v1 decision record

**Record status:** Approved architecture decisions incorporated in Phase 0.  
**Implementation status:** Schema v1 frozen; Phase 1 foundation and the initial custom User/framework migrations were authorized 2026-09-25. Remaining domain entities are not authorized in Phase 1.  
**PRD status:** `docs/PRD.md` is unchanged.

## 1. Approved architecture decisions

1. `RoadmapNode` uses an arbitrary-depth adjacency list with types `section`, `topic`, and `item`. Sections may contain sections. Items are measurable learning leaves; there is no fixed track/module/topic/task sequence.
2. A roadmap item is not an executable `Task`. They remain separate, and multiple tasks may reference one roadmap item.
3. A node may have multiple ordered `RoadmapResource` records.
4. Roadmap progress is `completed eligible leaf items / eligible leaf items`. Skipped items are excluded from the denominator and reported separately. Time invested is a separate metric.
5. A focus session snapshots the item's original ordered roadmap ancestry; historical time stays attributed to those ancestors after moves.
6. Prerequisites are informational in v0.1. Unmet prerequisites are shown but do not block starting or completing work.
7. Task status is only `planned`, `completed`, or `skipped`. Reopening a terminal task returns it to `planned`. FocusSession alone owns active/paused execution state.
8. An unfinished task may have at most one active/current `DailyPlanItem`. Historical occurrences remain stored and visible.
9. Carry-over marks the source occurrence as `carried_forward`, creates exactly one destination occurrence, and appends a planning-history event in the same transaction.
10. Recurring tasks are deferred; Schema v1 has no recurrence fields or API.
11. A finished focus session may be explicitly corrected. A correction requires a reason and appends an immutable before/after `FocusSessionCorrection` audit row in the same transaction.
12. Cancelled sessions retain terminal duration but are excluded from normal focus analytics.
13. Area is required when starting a focus session or spontaneous activity. Area IDs/labels are snapshotted so historical data survives taxonomy archival/deletion.
14. Deep-work classification is explicit per session. A task value is only the start-form default.
15. Focus and exercise may conceptually overlap, but FocusSession is the sole live timer. Timed exercise uses it; `ExerciseLog` stores health metadata and may reference the session.
16. Timer mutations are online-only in v0.1. Start, pause, resume, finish, and cancel require connectivity; offline mutation/replay is deferred.
17. Alpha evidence kinds are URL, GitHub URL, and note. Image/file evidence and meal photos are deferred.
18. Evidence and roadmap-resource URLs require HTTPS in production. Explicit development configuration may allow HTTP only for localhost/loopback.
19. Historical analytics group/display historical area labels by default.
20. A daily plan stores its local date and timezone snapshot; later user-timezone changes do not reinterpret it.
21. Sleep stores the timezone snapshot captured at creation and is attributed to the derived `wake_local_date` in that zone.
22. Weeks run Monday through Sunday; Sunday is close/review day. The initial user has `week_starts_on = 1` (ISO Monday).
23. Planned task completion is `completed eligible planned appearances / eligible planned appearances`; unique-task completion is not substituted.
24. There is no composite productivity/consistency score. Focused days, primary outcomes completed, target-hour adherence, exercise days, and roadmap progress are separate metrics.
25. Daily nutrition rating is a separate `DailyNutritionRating`, not part of `DailyReflection`.
26. Water is one `DailyWaterTotal` per local day, not consumption events.
27. Sleep intervals may not overlap other sleep intervals for the user. Exercise intervals may not overlap other exercise intervals for the user.
28. Challenges may overlap. A partial unique constraint permits at most one primary challenge per user; zero is valid before setup.
29. Daily reports are live-derived. Closing a reflection does not freeze facts; late records may update the report.
30. The 96-day report is initially live. No report snapshot table is added; downloadable/frozen completion export is deferred.
31. Production uses same-origin deployment and Django session authentication with CSRF protection. No JWT refresh-token infrastructure is designed for v0.1.
32. Private alpha has no self-service password recovery; admin/manual reset is sufficient. The identity design must allow recovery to be added before external testing.
33. Full account erasure deletes active user-owned database data. Formal backup/object-storage retention policy is deferred until external beta.
34. Health logs and reflections may be permanently deleted on explicit user request. No trash system is added for them.
35. The maximum three current primary outcomes is enforced by a transactional service with plan-row locking, not a PostgreSQL constraint trigger.

### Timer idempotency simplification

`sessions_command_receipt` is removed from the proposal. The private-alpha design uses client-generated UUIDs for FocusSession start and SessionPause creation, making create retries address the same resource. Resume, finish, and cancel lock the session, check an expected version, and return the existing representation when the requested target state is already reached; a conflicting terminal target returns a conflict. The database one-open-session invariant remains the race backstop. This avoids a receipt table, response-body storage, hashes, expiry cleanup, and replay retention.

## 2. Features deferred from v0.1

- `LifeMode` table and life-mode endpoints/default presets.
- Recurring tasks and recurrence generation/edit-series semantics.
- Image/file evidence, meal photos, upload intents, file metadata, and malware pipeline.
- Object storage and its retention/deletion policy.
- Full-text/trigram search indexes; v0.1 may use bounded case-insensitive search.
- Offline mutations, pending command queues, clock-drift/replay rules, and offline timer start/pause/resume/finish/cancel.
- Immutable weekly factual snapshots.
- Report snapshot tables and frozen/downloadable 96-day completion exports.
- Formal backup/object-storage retention policy until external beta.
- Self-service password recovery during private alpha (required for reconsideration before external testing).
- Background workers, materialized analytics, calendar integrations, AI features, social/team features, payments, and native apps.

## 3. Final proposed Schema v1 entities

| Entity | Purpose |
|---|---|
| `User` | Custom Django identity, timezone and week preference |
| `Challenge` | Inclusive challenge dates and optional primary designation |
| `Area` | User-owned work/health taxonomy |
| `DailyCapacity` | Date/timezone-snapshotted planning capacity |
| `Roadmap` | Curriculum container |
| `RoadmapNode` | Arbitrary-depth section/topic/item hierarchy |
| `RoadmapNodePrerequisite` | Informational directed prerequisite edge |
| `RoadmapResource` | Ordered labeled URL; multiple per node |
| `Task` | Executable intended work with three-state lifecycle |
| `DailyPlan` | Stored local day and timezone plan |
| `DailyPlanItem` | Historical dated appearance of a task |
| `PlanningEvent` | Append-only plan/carry-over/lifecycle history |
| `FocusSession` | Sole live execution timer and frozen attribution |
| `SessionPause` | Pause interval within a focus session |
| `FocusSessionCorrection` | Immutable audit of explicit terminal-session correction |
| `Evidence` | URL, GitHub URL, or note attached to one parent |
| `Accomplishment` | Independently recorded win/outcome |
| `SleepLog` | Non-overlapping sleep interval with wake-date attribution |
| `ExerciseLog` | Non-overlapping exercise metadata, optionally linked to timer |
| `MealLog` | Meal description/classification without photos |
| `DailyWaterTotal` | One daily water volume total |
| `DailyNutritionRating` | Separate daily nutrition score/notes |
| `DailyReflection` | Daily subjective reflection |
| `WeeklyReview` | Monday–Sunday subjective review/closure without fact snapshot |

Django framework session, migration, permission, and content-type tables are infrastructure tables, not Schema v1 domain entities.

## 4. Final relationships

- User owns every domain aggregate and dependent record; account erasure cascades all active user-owned database data.
- User has many challenges, with zero or one primary; many challenges may overlap.
- User has many areas, capacities, roadmaps, tasks, plans, sessions, evidence records, accomplishments, health logs, and reflections.
- Roadmap has many nodes. A node belongs to one roadmap and optionally one parent node in that same owned roadmap.
- A node has many resources and directed prerequisite edges. Both ends of an edge are in the same roadmap.
- Many tasks may reference one roadmap node, and that target must be an `item`. A task references at most one roadmap item in v0.1.
- DailyPlan has many DailyPlanItems. An item references one task while active/history snapshots survive permitted task deletion.
- PlanningEvent optionally references task, source occurrence, and destination occurrence and retains snapshots.
- FocusSession optionally references task and roadmap item, requires area, has many pauses/corrections, and snapshots original attribution.
- Evidence belongs to exactly one of Task, FocusSession, RoadmapNode, or Accomplishment.
- ExerciseLog may reference one FocusSession; a FocusSession may supply timing to exercise metadata without creating another timer.
- DailyWaterTotal, DailyNutritionRating, and DailyReflection are each unique by user/local date. WeeklyReview is unique by user/week start.

## 5. Final database-level invariants

- Primary keys are UUIDs; ownership FKs are non-null and account-erasure cascades are defined.
- Unique normalized user email.
- At most one primary challenge per user via partial unique constraint; challenge end date is not before start date.
- Area active names/slugs are unique per user as specified by final field design.
- DailyCapacity and DailyPlan are unique by `(user_id, local_date)`; stored timezone is non-null.
- Roadmap sibling positions are unique among non-archived siblings, including roots; node type/state values are checked; `parent_id != id`.
- Roadmap prerequisite pairs are unique and cannot self-reference.
- RoadmapResource positions are unique per node.
- Task status is constrained to `planned|completed|skipped`; terminal timestamp/status combinations are consistent.
- At most one current appearance of a task via a partial unique constraint on `DailyPlanItem(task_id)` for `state = 'current'`; source/destination plan positions are unique where current.
- Focus session status is constrained to `active|paused|completed|cancelled`; terminal timestamps/durations are consistent and non-negative.
- Required invariant: `UNIQUE (user_id) WHERE FocusSession.status IN ('active', 'paused')`.
- At most one open SessionPause per FocusSession; pause/session chronology checks apply.
- FocusSessionCorrection is append-only and has non-empty reason plus before/after JSON objects.
- Evidence kind is `url|github|note`, has exactly one parent, and has kind-appropriate non-empty URL/text fields.
- Date/time/rating/duration bounds are checked where row-local.
- One DailyWaterTotal, DailyNutritionRating, DailyReflection per user/local date; one WeeklyReview per user/Monday week start.
- Sleep intervals and exercise intervals do not overlap same-kind intervals for a user, using PostgreSQL exclusion constraints/ranges where feasible; end follows start.
- Deleting a user cascades all active user-owned database rows. No database report-snapshot or command-receipt table exists.

## 6. Final application/service-level invariants

- All reads/writes and relationship assignments are owner-scoped; cross-user IDs are rejected without disclosure.
- Roadmap parent moves and prerequisite edges remain same-roadmap, and locked cycle detection rejects hierarchy/prerequisite cycles.
- Arbitrary section nesting is permitted. Only `item` nodes are progress-eligible leaves and valid task-link targets.
- Unmet prerequisites are returned for display and never used as authorization/state-transition gates.
- Roadmap progress, skipped count, and time invested are calculated separately with published definitions.
- Task reopen changes terminal state to planned and clears terminal markers according to the audit event; it never creates active/paused task state.
- A plan mutation locks the plan/task as needed and enforces at most three current primary outcomes.
- Carry-over is atomic and retry-safe: mark one source carried forward, create/reuse one destination, append one event.
- Session start requires connectivity, area, explicit deep-work choice, and attribution snapshots. Task defaults do not silently override the chosen classification.
- Timer transitions use server timestamps, row locks, expected versions, and client-generated resource IDs for create retries. No offline mutation is accepted.
- Finished-session correction requires reason, validates chronology/duration, and appends audit before committing changed values.
- Normal focus analytics include eligible completed sessions and exclude cancelled sessions; cancelled duration remains available for audit-specific views.
- Historical analytics default to stored area labels, timezone/local dates, and original roadmap ancestry.
- Production URL validation requires HTTPS; only explicit development localhost/loopback exceptions are accepted.
- Sleep `wake_local_date` is derived once from the creation-time timezone snapshot. Existing daily plan dates/timezones are never reinterpreted after preference changes.
- Weekly windows are Monday–Sunday; closing a review/reflection never freezes report facts.
- Planned completion uses eligible occurrences, never distinct tasks. No composite score is emitted.
- Exercise time may come from a linked FocusSession; ExerciseLog never exposes timer transitions.
- Health/reflection explicit permanent deletion and full-account erasure use protected, auditable service operations.

## 7. Authorization status

No unresolved Schema v1 modeling question remains. On 2026-09-25, the architecture owner accepted the four recorded PRD/architecture differences as intentional v0.1 decisions, froze Schema v1, and authorized Phase 1 foundation work. That authorization does not extend to the remaining Schema v1 domain models or product endpoints.

## 8. Accepted differences from the approved PRD

| PRD statement | Approved Schema v1 decision | Effect / required disposition |
|---|---|---|
| Roadmaps are `roadmap -> track -> module -> item` | Nodes are arbitrary-depth `section|topic|item`; sections may nest | Direct terminology and hierarchy contradiction. PRD must be amended or an authorized exception recorded before implementation. |
| V0.1 includes “daily capacity and a configurable life mode” | `LifeMode` table is deferred | Direct v0.1 scope contradiction. DailyCapacity remains; configurable reusable life modes do not. PRD must be amended or an exception recorded. |
| PWA has “reasonable offline behavior” and resilient display under intermittent connectivity | All timer mutations require connectivity; offline mutations are deferred | Potential scope tension, not a timer-data ambiguity. v0.1 can still cache the shell and render the last known running timer, but must describe commands as online-only. Product owner should confirm this satisfies the PRD or amend it. |

The PRD's reference to explicit handling of uploaded evidence is non-operative for v0.1 under the approved deferral of all file/image evidence and object storage; if it was intended to mandate uploads, it should be clarified with the same reconciliation.
