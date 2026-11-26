"""Move tasks from planned/completed/skipped to the workflow statuses.

docs/project-workspaces-design.md §13. Reversible:

forward   planned -> todo, completed -> done, skipped -> cancelled
          (skipped_at is renamed cancelled_at; values are kept)
backward  todo -> planned, done -> completed, cancelled -> skipped;
          backlog/in_progress/in_review/blocked did not exist before and
          become planned (open) with no terminal timestamps.

Data written before this migration round-trips unchanged. Only task
rows change; plan items, planning events (history), evidence, focus
sessions and schedule entries are not touched. Bulk updates leave
updated_at as it was.

Rollback: take a pg_dump, then `migrate planning 0006`.
"""

from django.db import migrations, models

OPEN = ("backlog", "todo", "in_progress", "in_review", "blocked")
NEW_ONLY_OPEN = ("backlog", "in_progress", "in_review", "blocked")
FORWARD = {"planned": "todo", "completed": "done", "skipped": "cancelled"}
BACKWARD = {"todo": "planned", "done": "completed", "cancelled": "skipped"}


def to_workflow(apps, schema_editor):
    Task = apps.get_model("planning", "Task")
    for old, new in FORWARD.items():
        Task.objects.filter(status=old).update(status=new)


def to_legacy(apps, schema_editor):
    Task = apps.get_model("planning", "Task")
    Task.objects.filter(status__in=NEW_ONLY_OPEN).update(
        status="planned", completed_at=None, cancelled_at=None
    )
    for new, old in BACKWARD.items():
        Task.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0006_default_categories"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="task", name="planning_task_status_valid"),
        migrations.RemoveConstraint(
            model_name="task", name="planning_task_terminal_fields_valid"
        ),
        migrations.RenameField(
            model_name="task", old_name="skipped_at", new_name="cancelled_at"
        ),
        migrations.AlterField(
            model_name="task",
            name="status",
            field=models.CharField(
                choices=[
                    ("backlog", "Backlog"),
                    ("todo", "To do"),
                    ("in_progress", "In progress"),
                    ("in_review", "In review"),
                    ("blocked", "Blocked"),
                    ("done", "Done"),
                    ("cancelled", "Cancelled"),
                ],
                default="todo",
                max_length=12,
            ),
        ),
        migrations.RunPython(to_workflow, to_legacy),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        (
                            "backlog",
                            "todo",
                            "in_progress",
                            "in_review",
                            "blocked",
                            "done",
                            "cancelled",
                        ),
                    )
                ),
                name="planning_task_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("cancelled_at__isnull", True),
                        ("completed_at__isnull", True),
                        ("status__in", OPEN),
                    ),
                    models.Q(
                        ("cancelled_at__isnull", True),
                        ("completed_at__isnull", False),
                        ("status", "done"),
                    ),
                    models.Q(
                        ("cancelled_at__isnull", False),
                        ("completed_at__isnull", True),
                        ("status", "cancelled"),
                    ),
                    _connector="OR",
                ),
                name="planning_task_terminal_fields_valid",
            ),
        ),
    ]
