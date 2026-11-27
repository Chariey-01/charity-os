"""Pre-deploy step: run before a release starts serving (Render's preDeployCommand).

If this command fails, the release does not go live and the previous one keeps
serving. Steps:

1. ``check --deploy``: settings, HTTPS, the built frontend. Errors stop it.
2. List the migrations this release would apply. None: done.
3. No accounts in the database yet (the first deployment): migrate.
4. Accounts exist: migrate **only** when ``CHARITYOS_APPROVE_MIGRATIONS``
   equals the approval code printed for exactly these migrations. Otherwise
   stop and print the list, the code and what to do. A code approves one set of
   migrations; a release that brings a different set needs a new approval.

Before migrating a database with accounts it prints the time (UTC) to give the
platform's point-in-time recovery if the release has to be undone; see
``docs/operations/production-runbook.md``.
"""

import hashlib
import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

APPROVAL_VARIABLE = "CHARITYOS_APPROVE_MIGRATIONS"


def run_checks():
    call_command("check", deploy=True, fail_level="ERROR")


def pending_migrations():
    """``app.name`` labels of unapplied migrations, in the order they would run."""
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if any(backwards for _, backwards in plan):
        raise CommandError("This release would reverse migrations; refusing.")
    return [f"{migration.app_label}.{migration.name}" for migration, _ in plan]


def has_accounts():
    if "users_user" not in connection.introspection.table_names():
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM users_user)")
        return cursor.fetchone()[0]


def approval_code(labels):
    return hashlib.sha256("\n".join(labels).encode()).hexdigest()[:12]


def migrate():
    call_command("migrate", interactive=False)


class Command(BaseCommand):
    help = "Deploy checks, then migrations only when safe or approved."

    def handle(self, *args, **options):
        run_checks()
        labels = pending_migrations()
        if not labels:
            self.stdout.write("predeploy: no migrations to apply.")
            return
        listing = "\n".join(f"  {label}" for label in labels)
        if not has_accounts():
            self.stdout.write(
                f"predeploy: no accounts yet; applying {len(labels)} migrations."
            )
            migrate()
            return
        code = approval_code(labels)
        if os.environ.get(APPROVAL_VARIABLE, "").strip() != code:
            raise CommandError(
                f"This release would migrate a database that holds accounts:\n"
                f"{listing}\n"
                f"Nothing was changed. To approve exactly these migrations, take "
                f"a backup (docs/operations/production-runbook.md), set "
                f"{APPROVAL_VARIABLE}={code} and deploy again."
            )
        recovery_point = timezone.now().replace(microsecond=0).isoformat()
        self.stdout.write(
            f"predeploy: approved migrations ({code}):\n{listing}\n"
            f"predeploy: recovery point before migrating: {recovery_point}"
        )
        migrate()
        self.stdout.write(
            f"predeploy: migrations applied. Remove {APPROVAL_VARIABLE} now."
        )
