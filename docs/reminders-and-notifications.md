# Reminders, phone notifications and calendar

## What you get

- **Reminders** (Me → Reminders and calendar): once, every day, or on chosen weekdays, at a local time in your timezone. A reminder can open a goal, task or screen when tapped.
- **Activity start reminders, daily planning and weekly review** (Profile → Reminders): switch them on and they are also sent as phone notifications.
- **Snooze**: every notification has *Snooze 10 min*.
- **Your plan in Google Calendar**: a private, read-only `.ics` link of scheduled activities, task due dates, open milestones and goal target dates.

## How it works

```
Cloudflare cron (every minute) ──► Worker: is anything due? (Workers KV)
                                     │ only when due
                                     ▼
                     POST /api/v1/internal/reminders/dispatch  (cron secret)
                                     │
                    Django: claim a ReminderDelivery (unique key) ──► Web Push (VAPID)
                                     │                                   │
                                     ▼                                   ▼
                       next_due_at back to the Worker        Google / Mozilla / Apple push service
                                                                         │
                                                                         ▼
                                                     phone: service worker shows the notification
```

- The **server** decides when to send, so reminders arrive while CharityOS is closed. A browser timer cannot do this: Android suspends web pages.
- Each reminder is sent at most once. The delivery row's key is unique per user, so overlapping scheduler runs cannot double-send.
- A reminder more than 30 minutes late (for example, the backend was down) is recorded as *skipped* instead of arriving hours late.
- The Worker only wakes the backend when something is due (cached in Workers KV and cleared whenever reminders, schedule entries, preferences or devices change). That keeps Neon's free database asleep when idle.
- Push subscriptions are only accepted for the real push services (FCM, Mozilla, Apple, Windows), so the server never posts to arbitrary addresses.
- Snooze uses a signed, 24-hour token carried in the notification; it needs no cookie or CSRF token.

## Honest limits

- **A notification is not an alarm clock.** Android can delay notifications in battery saver or Doze mode, and users can mute them. For something that must not be missed, set an alarm in the phone's Clock app as well. Exact alarms need a native Android app (`AlarmManager`), which CharityOS does not have; see `docs/android-app.md`.
- The phone needs a connection when the reminder is sent; push services hold messages for up to an hour (`TTL=3600`).
- On iPhone, web push works only for an app added to the Home Screen (iOS 16.4+).
- Calendar apps refresh subscribed `.ics` links on their own schedule (Google: every few hours). For exact-time alerts use CharityOS reminders, not the calendar feed.
- The `.ics` link is a secret: anyone with it can read the titles in your plan. Make a new link to revoke the old one.

## Operating it

| Setting | Where | Notes |
|---|---|---|
| `CHARITYOS_VAPID_PUBLIC_KEY`, `CHARITYOS_VAPID_PRIVATE_KEY` | backend env | `manage.py generate_vapid_keys`. The private key is a secret. Replacing the keys silently invalidates every device subscription; users must turn notifications on again. |
| `CHARITYOS_VAPID_SUBJECT` | backend env | `https://` address of the app (default) or a `mailto:` contact. |
| `CHARITYOS_CRON_SECRET` | backend env **and** Worker secret `CRON_SECRET` | ≥ 32 characters, the same value in both. |
| `REMINDERS_KV` | Worker KV binding | Optional; strongly recommended on Neon Free. |

Without a cron (for example, local development) run `manage.py dispatch_reminders` from any scheduler every few minutes. It is safe to run repeatedly and concurrently.

Free-tier cost: Workers Free includes 100,000 requests/day; the cron uses 1,440 invocations/day plus at most one KV read each (KV Free: 100,000 reads and 1,000 writes per day). Web Push services are free.

## Verified

- Backend: `tests/test_notifications.py` (scheduling across DST, send-once under repeated dispatch, late skip, gone devices, start reminders, ownership, allow-listed endpoints, snooze, cron secret, encrypted payload decrypts with the device key, `.ics` privacy, escaping and line folding, erasure).
- Worker: `cloudflare/test/scheduler.test.mjs`.
- Service worker: `frontend/src/swPush.test.ts`.
- Real browser, 27 Nov 2026: Chrome subscribed through `fcm.googleapis.com`; the backend sent a test; the service worker displayed it with Open and Snooze. A real Android phone has **not** been tested yet.
