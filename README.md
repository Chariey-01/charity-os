# CharityOS

CharityOS is a personal execution system for turning long-term goals into daily action. Phase 1 establishes the production-oriented application foundation; product features and the remaining Schema v1 entities are deliberately not implemented yet.

## Foundation

- Backend: Python 3.12, Django 5.2, Django REST Framework, PostgreSQL
- Frontend: React 19, strict TypeScript, Vite, Tailwind CSS 4
- Quality: Ruff, pytest/pytest-django, ESLint, Vitest, React Testing Library
- Authentication direction: Django sessions and CSRF under one production origin (no auth endpoints yet)

The only CharityOS domain table currently authorized is the custom `users.User`. The public infrastructure check is `GET /api/v1/health`.

## Local setup

Prerequisites are Python 3.12+, Node.js 24+, npm, and PostgreSQL 17+. Docker Compose is optional but is the shortest path to a matching local database.

```bash
cp .env.example .env
# Edit .env; use a real random DJANGO_SECRET_KEY and local database password.
docker compose up -d postgres

python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
(cd backend && ../.venv/bin/python manage.py migrate)

(cd frontend && npm ci)
```

The Compose defaults use database/user `charityos` and password `charityos-local`. If those defaults are used, set the same values in `.env`. An externally managed PostgreSQL instance is equally valid; set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` accordingly. Backend tests create and use a PostgreSQL test database, so the configured role needs permission to create databases.

## Run the applications

Use separate terminals:

```bash
cd backend
../.venv/bin/python manage.py runserver
```

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. Vite proxies same-origin `/api` requests to Django on `127.0.0.1:8000`; frontend code never needs a development-only cross-origin API URL.

## Common commands

```bash
# Migrations
(cd backend && ../.venv/bin/python manage.py makemigrations --check --dry-run)
(cd backend && ../.venv/bin/python manage.py migrate)

# Backend validation
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
(cd backend && ../.venv/bin/python manage.py check)
(cd backend && ../.venv/bin/pytest)

# Frontend validation and production bundle
(cd frontend && npm run lint)
(cd frontend && npm run typecheck)
(cd frontend && npm test)
(cd frontend && npm run build)
```

Production must supply `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and all PostgreSQL variables. Production settings enable secure session/CSRF cookies and HTTPS redirection. Secrets belong in the runtime secret store, never in source control or `VITE_*` variables.

## Tooling choices

Ruff provides one fast Python lint/format workflow, while pytest-django makes database-backed Django tests explicit. ESLint covers TypeScript/React correctness, and Vitest plus React Testing Library tests behavior through the same Vite module pipeline. Tailwind uses the v4 Vite plugin rather than a legacy PostCSS configuration. Dependency lockfiles and pinned Python requirements make CI and local installs repeatable.

See [ADR 0001](docs/adr/0001-phase-1-technology-foundation.md) for the foundation decision and [the architecture](docs/architecture.md) for the approved system direction.

