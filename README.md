# CharityOS v0.1

CharityOS is a private, mobile-first personal execution system connecting daily plans, authoritative focus time, learning roadmaps, evidence, reflection, and wellbeing. It intentionally has no composite productivity score.

## Architecture and features

- Django 5.2 + DRF, PostgreSQL, session authentication and CSRF under one origin.
- React 19, strict TypeScript, Vite and Tailwind; responsive installable PWA shell.
- Daily plans retain historical task appearances, atomically carry unfinished work forward, and enforce at most three primary outcomes.
- The server owns the focus timer clock and transition state. A partial unique constraint permits one open session per user; reloads reconstruct display time from server timestamps.
- Arbitrary-depth roadmap nodes (`section`, `topic`, `item`), informational prerequisites, multiple resources and leaf-item progress.
- Note/HTTPS evidence, accomplishments, sleep, exercise, meals, daily water/nutrition, daily reflection and Monday–Sunday weekly review.
- Live-derived focus and planned-appearance metrics. Cancelled time is retained but excluded from ordinary focus analytics.

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

Create the first local account without storing a password in source control:

```bash
(cd backend && ../.venv/bin/python manage.py bootstrap_charityos --email you@example.com --timezone Africa/Nairobi)
```

The command prompts securely, then creates a 96-day primary challenge and default Area data.

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

Build `frontend/dist`, serve it and `/static/` through the same reverse proxy/origin, route `/api/` and `/admin/` to Django, and run Django through a production WSGI server. Before application startup run `python manage.py migrate --noinput` and `python manage.py collectstatic --noinput`. Supply `DJANGO_SETTINGS_MODULE=config.settings.production`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, and PostgreSQL variables from the platform secret store. Production enables secure cookies, HTTPS redirect, proxy TLS recognition and HSTS.

## Deliberate v0.1 limits

No JWT, social auth, self-service password reset, recurrence, offline timer mutation, uploads/object storage, wearables, calorie counting, AI coach, social/team features, payments, immutable report snapshots, or composite score. See [the implementation report](docs/v0.1-implementation-report.md) and [API contract](docs/api-contract.md).
