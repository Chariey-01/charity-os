# Open questions and architectural risks

## Blocking status

No unresolved Schema v1 modeling ambiguity remains from the senior review. The architecture owner accepted the four recorded PRD/architecture differences, froze Schema v1, and authorized Phase 1 foundation work on 2026-09-25. Product-domain implementation remains outside this phase.

## Decisions now closed

The following are no longer open: flexible roadmap depth/types; roadmap item versus Task; multiple resources; progress math; original ancestry; informational prerequisites; task lifecycle/reopen; one current unfinished-task appearance; carry-over history; recurrence deferral; audited finished-session corrections; cancelled-duration treatment; required session area; explicit deep-work selection; one timer for exercise; connected-only timer mutations; alpha evidence types; HTTPS URLs; historical labels; timezone snapshots; Monday–Sunday week; appearance-based planned completion; separate metrics; separate nutrition rating; daily water total; sleep/exercise non-overlap; primary challenge cardinality; live reports; same-origin Django sessions; alpha recovery; erasure/deletion; and service-layer enforcement of three primaries.

## Principal risks and controls

| Risk | Control |
|---|---|
| Timer races/retries | Client-generated session/pause UUIDs, row locks, expected versions, idempotent target states, and the partial unique open-session index |
| Incorrect corrections | Terminal-only correction service, mandatory reason, immutable before/after audit row |
| Timezone/history drift | Persist local date/timezone and historical labels; report by snapshots by default |
| Tree/prerequisite cycles | Transactional locked cycle checks for parent moves and prerequisite edges |
| Misleading progress | Publish numerator/denominator; separate skips and time; use plan appearances rather than unique tasks |
| Health interval conflicts | Transactional validation backed by PostgreSQL range/exclusion constraints where practical |
| Private-data exposure | Same-origin sessions/CSRF, owner-scoped queries, no private API caching, no file uploads in alpha |
| PRD drift | Resolve the three documented contradictions before implementation authorization |
| Deferred recovery/retention work forgotten | Make recovery an external-testing gate and formal retention an external-beta gate |

## Non-blocking implementation details

These may be settled during authorized implementation without changing Schema v1: exact field length limits; UI wording for eligible/skipped; search ranking after full-text work is reconsidered; correction permission UX; and operational cadence for pruning application logs (not user records).
