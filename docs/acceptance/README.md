# Mobile scheduler acceptance

Run on 2026-11-24 against the production build (`vite preview`, which proxies `/api` to Django) with a separate `charityos_acceptance` PostgreSQL database. Browser: Chrome 151, 390×844 phone viewport, touch enabled.

The script picks an IANA timezone where it is currently morning, runs the browser in that zone, and switches the user's profile to it through **Profile → Use this device's timezone**. The run below used `America/New_York` at 07:xx local time, so the "morning" study session was real, not simulated.

## Scenario and result

| Step | What was checked | Result |
|---|---|---|
| 1. Install / open | Manifest is `standalone` with 192/512 and maskable icons; service worker active at `/` | Pass |
| 2. Morning study | Quick add: Learning, 08:00–09:30, focus timer on | Pass |
| 3. Afternoon shopping | Quick add: Personal, 14:00–15:00 | Pass |
| 4. Evening exercise | Quick add: Exercise, 18:00–19:00 | Pass |
| (extra) Overlap | A clashing 18:30 call is flagged and not saved unless confirmed | Pass |
| 5. Start study | Entry in progress, linked server `FocusSession` created | Pass |
| (extra) Timer reachable | Focus bar with live timer shown on Schedule | Pass |
| 6. Pause and resume | Paused clock does not advance; resume continues | Pass |
| 7. Finish with outcome | Outcome and learning stored on entry and session | Pass |
| 8. Shopping done | Marked done with "As planned · 1h" explicitly chosen | Pass |
| 9. Exercise duration | Recorded 45 minutes | Pass |
| 10. Day progress | Today shows 3 of 3 done; agenda, timeline and day views | Pass |
| 11. Week and month | Week grid and month grid render all three | Pass |
| 12. Refresh | Reload keeps 3 of 3 done | Pass |
| 13. Accuracy | See below | Pass |

Accuracy assertions (from the API after reload):

- Study `actual_seconds` equals the linked focus session's `duration_seconds` (9 s in this run).
- Shopping actual = 60 min (explicitly confirmed), exercise actual = 45 min.
- `/insights?period=7d`: today planned 3, completed 3; health exercise history 45 min today.
- Time by category = session minutes + 60 + 45: each minute counted once.
- Weekly milestone of 3 reached.

The only console errors were the expected 403 from the pre-login session check and the deliberate 409 from the overlap test.

## Widths

`responsive` sweep at 360, 375, 390 and 430 px, at 1280 px desktop, and in dark mode at 390 px, across Today, week, month, quick add and Insights: **0 px horizontal overflow on all 36 combinations.**

## Screenshots

Curated 1× copies are in [`screenshots/`](screenshots/): numbered steps (`01-…` to `24-…`) and `width-…` captures for each viewport and dark mode.

## Re-running

```bash
# 1. A throwaway database (never your real one)
createdb -h localhost -p 5433 -O charityos charityos_acceptance
(cd backend && POSTGRES_DB=charityos_acceptance ../.venv/bin/python manage.py migrate)
(cd backend && ACCEPT_PW='choose-one' POSTGRES_DB=charityos_acceptance \
  ../.venv/bin/python manage.py bootstrap_charityos --email acceptance@example.com \
  --display-name Charity --timezone Africa/Nairobi --challenge-name "Road to 2027" --password-env ACCEPT_PW)

# 2. Servers
(cd backend && POSTGRES_DB=charityos_acceptance DJANGO_SETTINGS_MODULE=config.settings.development \
  DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:4173 ../.venv/bin/python manage.py runserver 127.0.0.1:8000)
(cd frontend && npm run build && npx vite preview --host 127.0.0.1 --port 4173)

# 3. Run (playwright-core is not a project dependency; install it anywhere)
mkdir -p /tmp/e2e && (cd /tmp/e2e && npm i --no-save playwright-core@1.56)
cp docs/acceptance/acceptance.mjs /tmp/e2e/ && echo 'choose-one' > /tmp/e2e/pw
./docs/acceptance/reset-acceptance-db.sh          # refuses any DB not named *acceptance*
(cd /tmp/e2e && CHROME_PATH=$(which google-chrome) node acceptance.mjs /tmp/e2e/shots /tmp/e2e/pw)
```

## Life OS, private beta, push and demo journeys (28 Nov 2026)

Four more scripts drive real Chrome (playwright-core, `--no-save`) against a throwaway database. They read the demo password from a file and never contain one.

| Script | What it checks | Last result (production build, `vite preview`) |
|---|---|---|
| `life-os.mjs <base> <shots> <pw-file> [width]` | Vision (evidence rule), goal + milestones (progress), AI Engineering template, resources, project + task + checklist, challenge pause/resume, My Journey, Me/Plan hubs, older screens, refresh; horizontal overflow on every screen | 16/16 at 360, 390, 430, 820 and 1280 px |
| `beta.mjs <base> <pw-file> <shots>` | Two sessions: beta invite → sign-up → reuse refused → partner invite/accept → share one goal → partner sees only it (API-checked) and cheers → feedback → reset link | 11/11 |
| `push.mjs <base> <pw-file> <shots>` | Real Web Push: Chrome subscribes through `fcm.googleapis.com`, the backend sends a test, the service worker shows it with Open and Snooze. Needs VAPID keys in the backend's environment and `http://localhost` (a secure context) | Passed on 6 of 8 runs; the 2 failures were Chrome's first push-service registration stalling in a brand-new headless profile (the app now reports this after 30 s) |
| `demo.mjs <base> <pw-file> <out>` | Records the 2-minute product demonstration (`charityos-demo.webm`) with captions and a DEMO DATA badge | 12/12 scenes |

`acceptance.mjs` was updated for the five-tab shell (Settings and Insights are under **Me**) and passed 16/16 again on the production build.
