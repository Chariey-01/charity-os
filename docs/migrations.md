# Migration ledger

Every migration that changes data or constraints, in apply order, with its dependencies and rollback notes. In any environment that holds real records, migrate only through the wrapper. It takes a verified `pre-migrate` backup and refuses to migrate if that backup fails ([backup and restore](operations/backup-and-restore.md)):

```bash
ops/db/migrate-with-backup.sh            # database from POSTGRES_DB
```

## Mobile scheduler (merged into `main` at `4ad209d`)

| Migration | Depends on | Effect | Reversible | Rollback notes |
|---|---|---|---|---|
| `planning.0005_area_health_kind` | `planning.0004` | Adds `Area.health_kind` and its check constraint | Yes | Drops the column; health kinds are lost |
| `planning.0006_default_categories` | `planning.0005`, `users.0001` | Data only: adds missing default categories for existing users. Never renames, recolours a chosen colour, unarchives, or re-creates an archived default | Yes (reverse is a no-op) | Created categories stay; delete them manually if unwanted |
| `users.0002_userpreferences` | `users.0001` | Adds `UserPreferences` | Yes | Drops preferences |
| `scheduling.0001_initial` | `planning.0006`, `execution.0002`, `roadmaps.0001` | Adds `ScheduleEntry` and its constraints | Yes | **Drops all schedule entries** |

Verified: rolled back to the pre-scheduler schema and re-applied on a copy of real-shaped data, with every pre-scheduler row intact.

## Task status workflow (P1, branch `feature/task-status-workflow`)

| Migration | Depends on | Effect | Reversible | Rollback notes |
|---|---|---|---|---|
| `planning.0007_task_status_workflow` | `planning.0006` | `planned→todo`, `completed→done`, `skipped→cancelled`; `skipped_at` renamed `cancelled_at`; both task constraints rebuilt for the seven workflow states | Yes | Existing data round-trips exactly (`updated_at` included). Tasks in `backlog`, `in_progress`, `in_review` or `blocked` become `planned`. Only task rows change |
| `planning.0008_planningevent_status_changed` | `planning.0007` | Adds the `status_changed` event choice; emits no SQL | Yes | `status_changed` rows remain as plain strings |

Order of operations inside `0007`:

1. Drop the two status constraints.
2. Rename the column.
3. Widen the choices.
4. Remap the data.
5. Recreate the constraints.

The remap therefore always runs with no status constraint active, in both directions.

Verified:
- `tests/test_task_status_migration.py` goes forward, back and forward again with history, plan items, evidence, a focus session and a schedule entry attached. The test was mutation-checked against a broken reverse mapping.
- A copy of real-shaped data was migrated to `0008` and back to `0006`: task rows were byte-identical and history events were preserved.

Application compatibility: the bundled client accepts both status vocabularies (shipped before `0007`). The API accepts legacy input values and reports a deprecated `legacy_status` for one release.
