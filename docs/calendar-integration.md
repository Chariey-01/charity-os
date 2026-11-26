# Calendar integration design

CharityOS remains the source of truth for **what** the user intends to do and **why** it matters. A calendar is the source of truth for **when** a block is scheduled. A CharityOS `FocusSession` records **what actually happened**.

> **Update (scheduler phase):** `scheduling.ScheduleEntry` now exists and is the provider-neutral planned block described below as `CalendarBlock`. A future `CalendarLink` should reference a schedule entry rather than introduce a second block model. See [scheduler-design.md](scheduler-design.md).

## Proposed boundary

- `Task` and `RoadmapNode`: durable work identity and context.
- `DailyPlanItem`: the task's appearance on a particular local day.
- Future `CalendarLink`: provider, provider account, external event id, CharityOS task, optional daily-plan item, last provider revision, sync state, and timestamps.
- Future `CalendarBlock`: planned start/end, IANA timezone, source, cancellation state, and optional link to a focus session.
- `FocusSession`: server-authoritative actual start, pause intervals, end, and duration. Calendar changes never rewrite focus history.

## Google Calendar first

OAuth credentials should be encrypted at rest and isolated from the session-auth system. The integration should request the narrowest practical calendar scopes. OAuth callbacks create a provider account record; they do not create a second CharityOS identity.

Outbound sync creates or updates an event with a stable CharityOS identifier in private extended properties. Inbound sync imports only opted-in calendars/events. A unique `(provider_account, external_event_id)` constraint and the private CharityOS identifier prevent duplicates.

## Update and cancellation rules

- CharityOS title or planned-time edits update a linked event unless the link is disconnected.
- Calendar time edits update the planned block, never the Task's meaning or actual FocusSession.
- Calendar cancellation marks the block cancelled; it does not delete the Task, evidence, or history.
- CharityOS task completion may annotate the event but should not delete it.
- Provider revisions/ETags and webhook message ids make updates idempotent.
- Conflicts retain both revisions for audit and ask the user which planned time to keep.

## Timezones

Store timestamps in UTC and retain the event's IANA timezone. Render and group using the user's selected timezone. All-day events remain local dates and must not be converted into midnight UTC blocks. DST transitions use timezone-aware datetimes; planned duration is derived from instants, not wall-clock text.

## Planned versus actual

Calendar duration is planned time. Focus duration is actual, calculated from backend timestamps minus pauses. Analytics may compare these values, but must not treat calendar attendance as evidence of completed work.

## Low-risk `.ics` export

An export endpoint can later generate a single `VEVENT` for a chosen task and planned block with a stable UID, escaped text, UTC timestamps, and CharityOS task URL. This requires no OAuth and does not establish two-way sync. It should be added only after users can explicitly choose a planned start, duration, and timezone.

## Delivery sequence

1. Add provider-neutral calendar link/block models and audit events.
2. Add `.ics` export.
3. Add Google OAuth and outbound create/update/cancel.
4. Add webhooks plus periodic reconciliation.
5. Add opt-in inbound import and conflict UI.

Historical CharityOS records remain independent of provider availability, token expiry, challenge boundaries, and calendar deletion.
