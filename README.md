# CharityOS v0.1

CharityOS is a private, mobile-first personal scheduler and life tracker. It connects a time-based schedule for any activity (study, errands, exercise, sleep, appointments) with daily plans, authoritative focus time, learning roadmaps, evidence, reflection, and wellbeing. Challenges such as Road to 2027 are dated containers inside it. It intentionally has no composite productivity score.

## Architecture and features

- Django 5.2 + DRF, PostgreSQL, session authentication and CSRF under one origin.
- React 19, strict TypeScript, Vite and Tailwind; responsive installable PWA shell.
- Daily plans retain historical task appearances, atomically carry unfinished work forward, and enforce at most three primary outcomes.
- The server owns the focus timer clock and transition state. A partial unique constraint permits one open session per user; reloads reconstruct display time from server timestamps.
- Arbitrary-depth roadmap nodes (`section`, `topic`, `item`), informational prerequisites, multiple resources and leaf-item progress.
- Note/HTTPS evidence, accomplishments, sleep, exercise, meals, daily water/nutrition, daily reflection and Monday–Sunday weekly review.
- Live-derived focus and planned-appearance metrics. Cancelled time is retained but excluded from ordinary focus analytics.
- **Schedule entries** for any activity with local times in an IANA timezone, categories with colours, a full lifecycle (scheduled, in progress, paused, completed, partially completed, skipped, cancelled, rescheduled), overlap detection with explicit override, and rescheduling that keeps the original record. Focus-tracked entries use the existing server-authoritative `FocusSession`; other entries record actual start/end or minutes. Nothing is completed automatically and unknown actual time is never invented.
- **Mobile-first PWA**: Today, Schedule (day/week/month), Roadmaps, Insights and Profile; quick add; a persistent focus bar; installable with an offline app shell; light and dark themes; foreground reminders.
- **Insights** from real records grouped in the user's timezone: planned vs completed, time by category (each minute counted once), focus, weekly consistency, challenge progress, and a separate health section. Gentle, derived gamification (weekly milestones, balance badges, an optional weekly rhythm streak).

Design and decisions: [docs/scheduler-design.md](docs/scheduler-design.md). Acceptance run and screenshots: [docs/acceptance/](docs/acceptance/README.md).

## Local setup

Prerequisites: Python 3.12+, Node.js 24+, npm, and PostgreSQL 16+ (17 recommended).

```bash
cp .env.example .env
# Set a local secret and database credentials in .env.
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
(cd backend && ../.venv/bin/python manage.py migrate)
(cd frontend && npm ci)
```

The private developer cluster on the original implementation machine listens on `localhost:5433`; set `POSTGRES_PORT=5433` there. This is local guidance, not a production default. Never alter the system PostgreSQL cluster on 5432 for this project. A configured test role must be able to create test databases.

Each checkout runs its tests in its own database, `test_charityos_<hash of the checkout path>`, which pytest creates at the start of a run and drops at the end. Two checkouts can therefore test at the same time without touching each other. To run a second suite in the same checkout, set `CHARITYOS_TEST_DB=test_<name>`. The override is refused if it lacks the `test_` prefix, or if it uses the reserved `test_charityos*` namespace. That namespace holds the old shared database, other checkouts' automatic names and other sessions' databases. Pass `--reuse-db` yourself only when you know the schema has not changed.

Create the first local account without storing a password in source control:

```bash
(cd backend && ../.venv/bin/python manage.py bootstrap_charityos --email you@example.com --timezone Africa/Nairobi)
```

The command prompts securely, then creates a 96-day primary challenge and default categories (areas), including the scheduler's Social, Learning, Sleep and Custom categories with colours. Existing accounts receive any missing default categories through migration `planning.0006`; it never renames, recolours a chosen colour, unarchives, or re-creates a default you archived. **Profile → Categories → Restore any missing default categories** does the same on demand.

After the account exists, seed the personal development tracks from the roadmap polish pass:

```bash
(cd backend && ../.venv/bin/python manage.py seed_personal_roadmaps --email you@example.com)
```

This creates 13 roadmap containers with nested sections/items and skips any roadmap title that already exists. It never overwrites existing descriptions, progress, tasks, evidence, or nodes. Open the Roadmap tab to read each track's purpose, outcome, working instructions, evidence standard, completion definition, next actions, resources, linked tasks, focus time, and progress.

## Development and validation

```bash
# terminal 1
(cd backend && ../.venv/bin/python manage.py runserver)
# terminal 2 — Vite proxies /api to Django
(cd frontend && npm run dev)

.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
(cd backend && ../.venv/bin/python manage.py check)
(cd backend && ../.venv/bin/python manage.py makemigrations --check --dry-run)
(cd backend && ../.venv/bin/pytest)
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
```

## Production

Build `frontend/dist`, serve it and `/static/` through the same reverse proxy/origin, route `/api/` and `/admin/` to Django, and run Django through a production WSGI server. Before application startup, run `ops/db/migrate-with-backup.sh --database NAME`, which migrates only after a verified backup of that same database, and `python manage.py collectstatic --noinput`. Migration order, dependencies and rollback notes are in [docs/migrations.md](docs/migrations.md); backups, restores and the restore drill are in [docs/operations/backup-and-restore.md](docs/operations/backup-and-restore.md). Supply `DJANGO_SETTINGS_MODULE=config.settings.production`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, and PostgreSQL variables from the platform secret store. Production enables secure cookies, HTTPS redirect, proxy TLS recognition and HSTS.

Nothing is deployed yet. Before a first deployment, read the [deployment plan](docs/operations/deployment-plan.md) (requirements, prerequisites and the go-live gate), the [reverse-proxy guide](docs/operations/reverse-proxy.md) and the [private PWA release checklist](docs/operations/private-pwa-release-checklist.md).

## Reminders and installation

Install from the browser menu (Android/desktop Chrome offers an **Install app** button under Profile; on iOS use Share → Add to Home Screen). Reminders (before an activity, at its start, daily planning, weekly review) are configured under Profile → Reminders. They fire **only while CharityOS is open or briefly backgrounded**; a PWA cannot wake itself without Web Push, which is not implemented. With notification permission they appear as system notifications, otherwise as in-app messages.

## Deliberate v0.1 limits

No JWT, social auth, self-service password reset, recurrence (including repeating schedule entries), background push reminders, drag-and-drop calendar moves, Google Calendar sync, offline timer mutation, uploads/object storage, wearables, calorie counting, AI coach, social/team features, payments, immutable report snapshots, or composite score. See [the implementation report](docs/v0.1-implementation-report.md) and [API contract](docs/api-contract.md).
