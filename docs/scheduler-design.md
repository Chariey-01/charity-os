# Mobile scheduler and life tracker — design

**Status:** Stage A design, implemented on `feature/mobile-scheduler`.

CharityOS is a permanent personal operating system. Challenges are dated containers inside it. This phase adds a phone-first scheduler that can hold any activity (study, shopping, exercise, sleep, appointments), track what really happened, and report on it without a composite score.

## 1. Audit summary

| Existing piece | What it is | Fit for scheduling |
|---|---|---|
| `planning.Task` | Durable work to accomplish (`planned`/`completed`/`skipped`) | No time, wrong lifecycle for appointments. Keep as "work". |
| `planning.DailyPlan` / `DailyPlanItem` | A task's appearance on a local date, max three primaries | Date only, task-only. Keep for outcome planning. |
| `execution.FocusSession` | Server-authoritative actual focus time with pauses, versions and idempotent ids | Reuse for timed focus work. Not a plan. |
| `planning.Area` | Per-user name/slug/color/icon/order/archive | Already a category. Reuse; do not add a parallel model. |
| `health.ExerciseLog` / `SleepLog` | Health records with non-overlap exclusion constraints | Remain the health source of truth. |
| `planning.DailyCapacity` | Available minutes per local date | Feeds "available capacity" on Today. |

Gaps found and fixed as part of this work:

- Django `ValidationError` raised from services surfaced as HTTP 500. A DRF exception handler now maps it to a 400 with `{"error": {...}, "detail": ...}`.
- `/daily-plans/today` used the server's UTC date instead of the user's timezone.
- The manifest had no icons and there was no service worker, so the PWA was not installable.

## 2. Domain model

### `scheduling.ScheduleEntry` (new)

A planned block of time for any activity. It is **not** a Task and does not require one.

| Field | Notes |
|---|---|
| `id` | UUID. Clients may supply it on create for idempotent retries on flaky mobile networks. |
| `title`, `description`, `notes`, `outcome` | Only `title` is required. |
| `area` → `Area` | Category and color. `area_label_snapshot` keeps history if an area is later removed. |
| `start_at`, `end_at` | UTC instants. `end_at > start_at`, at most 24 h (sleep may cross midnight). |
| `timezone_name`, `local_date` | IANA zone used to interpret the wall-clock input; `local_date` is the start's local date. |
| `status` | `scheduled`, `in_progress`, `paused`, `completed`, `partially_completed`, `skipped`, `cancelled`, `rescheduled`. |
| `tracking` | `manual` (record actual start/end or minutes) or `focus` (timed by `FocusSession`). |
| `task`, `roadmap_node` | Optional links, owner-validated. |
| `focus_session` | Optional one-to-one link created when a `focus` entry is started. |
| `rescheduled_from` | One-to-one link from the replacement to the original. |
| `actual_started_at`, `actual_ended_at`, `actual_duration_seconds`, `paused_at`, `paused_seconds` | Manual tracking only. |
| `closed_at`, `version` | Terminal timestamp and optimistic-concurrency counter. |

Planned duration is derived from `end_at - start_at` (instants, so DST-correct). It is never stored twice.

**No double counting.** A database constraint forbids manual actual fields on an entry linked to a `FocusSession`. A linked entry's actual time *is* the session's duration. Analytics count linked entries via the session and only add focus sessions that are **not** linked to an entry.

### `users.UserPreferences` (new)

One row per user: reminder opt-in and lead time, start-time reminders, daily-planning and weekly-review reminder times, `show_streaks` (off by default), `celebrations_enabled`, and `default_today_view`.

### `planning.Area.health_kind` (new field)

`""`, `exercise` or `sleep`. It lets completed activities in those categories appear in health history without guessing from names.

### Default categories

Software Engineering, Computer Science, Career, Freelancing, Projects, Exercise, Nutrition, Recovery, Personal, Social, Learning, Sleep and Custom, each with a color. A data migration adds only the missing ones for existing users, and fills a color only where the area still has the untouched model default. The bootstrap command and `POST /areas/ensure-defaults` use the same idempotent service.

## 3. Lifecycle

```text
scheduled ──start──▶ in_progress ◀─resume── paused
    │                   │  └──────pause──────▲
    │                   ├─complete / partial──▶ completed / partially_completed
    │                   └─cancel────────────▶ cancelled
    ├─complete / partial (record actuals after the fact)
    ├─skip──────▶ skipped ──reschedule──▶ rescheduled (+ new scheduled entry)
    ├─cancel────▶ cancelled ─reschedule─▶ rescheduled (+ new scheduled entry)
    └─reschedule▶ rescheduled (+ new scheduled entry)
```

- Nothing is ever completed automatically because its end time passed.
- Rescheduling never rewrites the original. It closes it as `rescheduled` and creates a linked replacement. Repeating the call returns the same replacement.
- A `scheduled` entry may be *moved* (PATCH times) without history, because it is still only a plan. Anything else must be rescheduled.
- Notes and outcome stay editable after completion. Times, title and category lock once an entry is closed.
- Transitions lock the row (`SELECT … FOR UPDATE`), accept an optional `expected_version` (409 on mismatch), and are idempotent when the entry is already in the target state.
- Focus entries delegate start/pause/resume/finish/cancel to the existing `execution.services`. When the generic `/sessions/{id}/…` endpoints change a linked session, the entry is synchronised in the same transaction.
- Completing a never-started entry records only what the user supplies (minutes, or start and end). With nothing supplied, actual time stays unknown rather than being copied from the plan.

## 4. Overlaps and concurrency

Create, move and reschedule check for overlaps with the user's other open entries (`scheduled`, `in_progress`, `paused`). An overlap returns **409 `schedule_overlap`** listing the conflicts. The client may retry with `allow_overlap: true` once the user confirms. The user row is locked for the write so two concurrent creates cannot both pass the check.

## 5. Timezones

Clients send wall-clock values (`start_local: "2026-11-24T09:00"`) plus an IANA `timezone_name` (defaulting to the user's). The server converts with `zoneinfo`, rejects wall-clock times that do not exist (DST gaps), and resolves ambiguous times to the first occurrence. Responses include both UTC instants and local wall-clock strings. Day ranges are computed in the user's timezone and match entries by overlap, so a 22:30–06:30 sleep block appears on both days.

## 6. API (all under `/api/v1`, session auth + CSRF, owner-scoped)

```text
GET  /schedule-entries?start=YYYY-MM-DD&end=YYYY-MM-DD[&include=all]
POST /schedule-entries                         (201; 200 on idempotent replay)
GET/PATCH /schedule-entries/{id}
POST /schedule-entries/{id}/start|pause|resume|complete|skip|cancel|reschedule
GET  /schedule/day?date=YYYY-MM-DD             Today payload: entries, progress, capacity, unscheduled tasks, challenge, week summary
GET  /insights?period=7d|30d|90d|challenge|year|all
GET/PATCH /preferences
POST /areas/ensure-defaults
```

`DELETE` is not offered for schedule entries; cancel preserves history.

## 7. Insights

Built only from stored records, grouped by the user's timezone:

- **Schedule:** planned vs completed per day and per week, rescheduled/skipped/cancelled counts, completion history.
- **Time by category:** planned minutes, plus actual minutes from manual actuals, linked focus sessions, and unlinked focus sessions, each counted once.
- **Focus:** daily and weekly minutes from completed sessions. Cancelled sessions are excluded, as before.
- **Consistency:** active days per week. There is no penalty language and no composite score.
- **Health (separate section):** exercise minutes and sleep hours from health logs, plus completed `exercise`/`sleep` category activities that do not overlap a log of the same kind.
- **Challenge:** day N of M and activity inside the challenge window.

Gamification is derived, never stored: completion celebrations, weekly milestones (3, 7, 12 completed activities), balance-oriented badges (no "most hours" badges), and an optional **weekly** consistency streak (weeks with ≥3 active days). A missed day never resets anything.

## 8. Mobile experience

- Bottom navigation: **Today · Schedule · Roadmaps · Insights · Profile**, with a floating quick-add button and a persistent focus bar while a session is open.
- **Today:** date, challenge chip, compact progress and capacity, current activity, then Agenda / Timeline / Day switcher; completed and unscheduled-task sections are collapsible.
- **Schedule:** Day (hour grid, tap a slot to add), Week (7-column grid), Month (date grid with category dots).
- **Quick add:** bottom sheet with Title → Category → Date → Start → End → Save; optional fields are tucked away.
- Health log, reflection, history, challenges, categories and reminders live under Profile.
- Hash-based routes so the Android back button and deep links work in the installed app.

## 9. PWA and reminders

- Manifest with PNG and maskable icons, `standalone` display, shortcuts. A service worker caches the app shell only; it never caches `/api/`.
- Offline: a banner appears, cached shell still opens, and mutations are disabled (the server owns the timer).
- **Reminders are foreground-only.** While CharityOS is open (or recently backgrounded), it shows system notifications through the service worker if permission is granted, and in-app toasts otherwise. Background push needs Web Push (VAPID keys and a push sender), which is out of scope. The UI says so plainly.

## 10. Calendar integration path

`ScheduleEntry` is the provider-neutral "planned block" proposed in [calendar-integration.md](calendar-integration.md). A future `CalendarLink(entry, provider_account, external_event_id, revision)` can attach to it without changing its meaning. No OAuth in this phase.
