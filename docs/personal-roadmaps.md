# Personal roadmap workflow

The personal roadmap seed is intentionally user-scoped. It is not a global fixture and does not run during migrations.

```bash
(cd backend && ../.venv/bin/python manage.py seed_personal_roadmaps --email you@example.com)
```

The command creates the following tracks when they do not already exist:

- Software Engineering
- TypeScript
- Node.js
- GitHub & Open Source
- Jobs Club
- Interview Preparation
- Career & Applications
- Computer Science Foundations
- AI Engineering
- Freelancing
- Projects
- Exercise
- Recovery

Each roadmap uses the existing `Roadmap.description` field for five guidance blocks: PURPOSE, OUTCOME, HOW TO WORK THIS TRACK, EVIDENCE, and COMPLETION. Nested `RoadmapNode` sections and item nodes hold the actionable curriculum. The command is idempotent by `(user, title)` and deliberately skips existing roadmaps so personal edits are preserved.

Roadmap progress remains the frozen definition: completed eligible item nodes divided by eligible item nodes. Skipped items are excluded from the denominator and shown separately. The Roadmap screen's NEXT UP list is deterministic: planned tasks linked to items rank first, then prerequisite-ready planned items, with stable roadmap/position/title ordering. It does not create tasks or schedules automatically.

Use the UI's item actions to create a Task or mark an item complete. Add evidence through the existing Evidence API, and attach HTTPS/GitHub URLs or notes to the relevant parent. Add exact Jobs Club material later by creating nodes/resources inside that existing container; reseeding will not replace it.
