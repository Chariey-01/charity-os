# ADR 0001: Phase 1 technology foundation

- Status: Accepted
- Date: 2026-09-25

## Context

CharityOS needs a production-oriented foundation for a private, browser-based alpha while preserving the approved same-origin modular-monolith architecture. Phase 1 is intentionally limited to infrastructure and identity; product domains remain unimplemented.

## Decision

- Use Django and Django REST Framework for the backend, with PostgreSQL as the system of record.
- Use a custom Django user model from the first migration and Django's password/authentication infrastructure.
- Use React, strict TypeScript, and Vite for the frontend.
- Use Tailwind CSS through its supported Vite plugin integration.
- Use Django server-side sessions and CSRF protection. Do not add JWT refresh-token infrastructure.
- Target one production origin for the frontend and `/api` routes. Vite proxies `/api` to Django during local development.
- Use Ruff for Python linting/formatting, pytest with pytest-django for backend tests, ESLint for frontend linting, and Vitest with React Testing Library for frontend tests.

## Consequences

The browser can use first-party cookies and Django's CSRF model without cross-origin credential handling. Local development uses two processes but preserves same-origin request paths through Vite. PostgreSQL is required for backend tests so test behavior does not silently diverge from production database behavior.

