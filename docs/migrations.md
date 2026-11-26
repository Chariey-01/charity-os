# Migration ledger

Every migration that changes data or constraints, in apply order, with its dependencies and rollback notes. In any environment that holds real records, migrate only through the wrapper. It takes a verified `pre-migrate` backup and refuses to migrate if that backup fails ([backup and restore](operations/backup-and-restore.md)):

```bash
ops/db/migrate-with-backup.sh --database NAME   # the target is always named explicitly
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

## Phase 0A data safety (branch `feature/data-safety`, based on `1ceba99`)

Apply these with `ops/db/migrate-with-backup.sh --database NAME`.

| Migration | Depends on | Effect | Reversible | Rollback notes |
|---|---|---|---|---|
| `planning.0009_planningevent_archive_events` | `planning.0008` | Adds the `archived` and `restored` event choices. Emits no SQL | Yes | Those rows remain as plain strings |
| `roadmaps.0002_archived_at` | `roadmaps.0001` | Adds nullable `archived_at` to `Roadmap`, `RoadmapNode` and `RoadmapResource`. A roadmap with the legacy status `archived` gets `archived_at = updated_at` and status `active`, and the `archived` choice is removed | **Refuses while any archived row exists** | Restore archived rows first; otherwise they would silently become visible |
| `records.0002_archived_at` | `records.0001` | Nullable `archived_at` on `Accomplishment` and `Evidence` | Refuses while archived rows exist | As above |
| `reflections.0002_archived_at` | `reflections.0001` | Nullable `archived_at` on `DailyReflection` and `WeeklyReview` | Refuses while archived rows exist | As above |
| `health.0002_archived_at` | `health.0001` | Nullable `archived_at` on the five health logs | Refuses while archived rows exist | As above |
| `planning.0010_restrict_history_deletes` | `planning.0009`, `challenges.0001`, `roadmaps.0002` | History links become `RESTRICT`. State only: Django enforces `on_delete`, so no SQL | Yes | None |
| `roadmaps.0003_restrict_history_deletes` | `roadmaps.0002`, `planning.0010` | As above. Prerequisite links stay `CASCADE` | Yes | None |
| `execution.0003_restrict_history_deletes` | `execution.0002`, `planning.0010`, `roadmaps.0003` | As above. `FocusSession.area` changes from `PROTECT`, which made user erasure impossible, to `RESTRICT` | Yes | None |
| `records.0003_restrict_history_deletes` | `records.0002`, `execution.0003`, `planning.0010`, `roadmaps.0003` | As above | Yes | None |
| `health.0003_restrict_history_deletes` | `health.0002`, `execution.0003` | As above | Yes | None |
| `scheduling.0002_restrict_history_deletes` | `scheduling.0001`, `execution.0003`, `planning.0010`, `roadmaps.0003` | As above | Yes | None |

Verified:

- **`archived_at` migrations:** the `sqlmigrate` output for each is plain `ADD COLUMN "archived_at" timestamp with time zone NULL`, with no default and no `UPDATE`, so no table is rewritten.
- **Restrict migrations:** none of them emits SQL.
- **Old-shape data:** `tests/test_archive_migrations.py` and `tests/test_history_restrict.py` take one of every history-bearing record, linked together, through every migration forward, back and forward again. Every column of every row is unchanged. Each reverse guard is tested, and was mutation-checked by removing it.
- **Real-shaped data:** the restore drill (`ops/db/restore-drill.sh --migrate`) applies all eleven migrations to a restored copy of `charityos_acceptance`, plus `planning.0007`/`0008`, which that database lacks. It then reverses them and re-applies them. Every row of every data table is byte-identical after the reversal. The drill report is in `~/charityos-backups/drill-reports/`.

### Integrating with the parked `feature/project-domain`

That branch, built on the same base, adds `planning.0009_task_project_fields`, `planning.0010_planningevent_project` and `projects.0001_initial`. Its specification also reserves `records.0002_evidence_milestone`. When the branches are joined:

1. **`planning`** will have two separate migration chains. Add a merge migration (`makemigrations --merge planning`) and do not renumber either branch's committed migrations.
2. **`records.0002_evidence_milestone`** is not built yet. Generate it after Phase 0, on top of `records.0003`. It rebuilds the evidence "exactly one parent" constraint, so the new milestone link must also be `RESTRICT`, and the structural test in `tests/test_history_restrict.py` must pass.
3. **Two rules in the Phase 2 specification conflict with the owner's decisions** and need amending first:
   - Rule V6 lets personal tasks be deleted; decision 4.2 says tasks are archived instead.
   - §15 freezes an entry's `task` once a session is linked; decision 4.5 makes the audited correction the one exception.
4. **Before merging,** run the forward and reverse migration tests and `erase_user` against the joined graph.

