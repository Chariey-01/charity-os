# CharityOS v0.1 — Product requirements

## Product statement

CharityOS is a mobile-first personal execution system. Its loop is:

> Plan → Start → Focus → Finish → Prove → Reflect → Improve

The first product experiment has one real user and one database-driven challenge:

- Name: Road to 2027
- Start date: 2026-09-27
- End date: 2026-12-31
- Duration: 96 inclusive calendar days

Its primary question is whether consistent use improves execution, learning, health awareness, and satisfaction with daily progress.

## V0.1 capabilities

1. Customizable life areas without database enums.
2. Roadmaps organized as roadmap → track → module → item, with prerequisites and progress.
3. Daily plans with no more than three primary outcomes and optional secondary tasks.
4. Rich tasks linked optionally to an area and roadmap item.
5. Timestamp-backed focus sessions that survive refreshes and closed browsers.
6. A finish flow recording outcome, learning, evidence, difficulty, and optional task completion.
7. Quick capture of unplanned tasks, activities, logs, and accomplishments.
8. Lightweight exercise, meal/water, sleep, daily reflection, and weekly review records.
9. Daily reports and mobile-friendly analytics derived from source records.
10. Search across sessions, notes, evidence, tasks, roadmap content, and accomplishments.
11. Daily capacity and a configurable life mode.
12. An installable, responsive PWA with reasonable offline behavior.

## Product rules

- A challenge's displayed day is inclusive: `local_date - start_date + 1`.
- Primary outcomes are ordered and limited to three per user per local date.
- Planned work and actual work remain distinct. A session may be spontaneous.
- Recorded timestamps, not client-side counters, are the source of truth for time.
- Time must be attributable to the area at the time it occurred, even if a task changes later.
- Reports and analytics describe relationships; they do not make health diagnoses.
- Employment or other commitments reduce planned capacity, not sleep expectations.

## Out of scope

Payments, subscriptions, social features, teams, public profiles, messaging, leaderboards, an AI coach, wearables, calories, a gamification economy, and native mobile apps are excluded.

## Non-functional requirements

- Mobile-first and touch-friendly.
- WCAG-conscious keyboard, contrast, focus, and reduced-motion behavior.
- Secure single-user-ready authentication that can grow to multiple users.
- All mutable user-owned records enforce ownership server-side.
- PostgreSQL in production; test setup must exercise PostgreSQL-specific behavior.
- Fast initial shell and resilient timer display under intermittent connectivity.
- Private-by-default data and explicit handling of uploaded evidence.
