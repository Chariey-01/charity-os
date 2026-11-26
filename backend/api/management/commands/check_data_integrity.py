"""Read-only check of the relationships Phase 0 relies on (Phase 0B, B5).

    manage.py check_data_integrity

Runs inside a READ ONLY transaction, so it cannot change anything. Prints one
line per check and exits with status 1 if any check finds a problem, so it can
gate a restore drill or a deployment.

Checks:
* roadmap parent cycles (nodes whose ancestry loops back on itself);
* parents in a different roadmap;
* links between records owned by different users, for every foreign key
  between per-user models;
* linked schedule entries whose category, task or roadmap item differ from
  their focus session's (decision 4.5), or whose status does not mirror it.
"""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, models, transaction
from django.db.models import F

from roadmaps.models import RoadmapNode
from scheduling.models import ScheduleEntry
from scheduling.services import SESSION_TO_ENTRY

SAMPLE = 10


def _owned(model):
    return any(
        field.name == "user" and field.related_model is get_user_model()
        for field in model._meta.concrete_fields
        if field.is_relation
    )


def roadmap_cycles():
    parents = dict(RoadmapNode.objects.values_list("pk", "parent_id"))
    in_cycle = set()
    for start in parents:
        seen = []
        cursor = start
        while cursor is not None and cursor not in seen:
            seen.append(cursor)
            cursor = parents.get(cursor)
        if cursor is not None:  # walked back into a node already on this path
            in_cycle.update(seen[seen.index(cursor) :])
    return sorted(str(pk) for pk in in_cycle)


def cross_roadmap_parents():
    return [
        str(pk)
        for pk in RoadmapNode.objects.filter(parent__isnull=False)
        .exclude(parent__roadmap_id=F("roadmap_id"))
        .values_list("pk", flat=True)
    ]


def cross_user_links():
    found = []
    for model in apps.get_models():
        if not _owned(model):
            continue
        for field in model._meta.concrete_fields:
            if (
                not isinstance(field, models.ForeignKey)
                or field.name == "user"
                or not _owned(field.related_model)
            ):
                continue
            rows = model.objects.filter(**{f"{field.name}__isnull": False}).exclude(
                **{f"{field.name}__user_id": F("user_id")}
            )
            found += [
                f"{model._meta.label}.{field.name}:{pk}"
                for pk in rows.values_list("pk", flat=True)
            ]
    return found


def linked_entry_mismatches():
    """Entries whose attribution or status differs from their focus session.

    Compared in Python, field by field: a negated ORM comparison would treat
    two NULL tasks as different.
    """
    attribution, status = [], []
    skipped = (
        ScheduleEntry.Status.PARTIALLY_COMPLETED,
        ScheduleEntry.Status.SKIPPED,
        ScheduleEntry.Status.RESCHEDULED,
    )
    for entry in ScheduleEntry.objects.filter(
        focus_session__isnull=False
    ).select_related("focus_session"):
        session = entry.focus_session
        if (entry.area_id, entry.task_id, entry.roadmap_node_id) != (
            session.area_id,
            session.task_id,
            session.roadmap_item_id,
        ):
            attribution.append(str(entry.pk))
        if (
            entry.status not in skipped
            and SESSION_TO_ENTRY[session.status] != entry.status
        ):
            status.append(str(entry.pk))
    return sorted(attribution), sorted(status)


class Command(BaseCommand):
    help = "Read-only check of roadmap trees, ownership links and linked entries."

    def handle(self, *args, **options):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            attribution, status = linked_entry_mismatches()
            results = [
                ("roadmap parent cycles", roadmap_cycles()),
                ("parents in another roadmap", cross_roadmap_parents()),
                ("links between different users' records", cross_user_links()),
                (
                    "linked entries attributed differently from their session",
                    attribution,
                ),
                ("linked entries whose status does not mirror their session", status),
            ]
        problems = 0
        for label, found in results:
            if found:
                problems += len(found)
                sample = ", ".join(found[:SAMPLE])
                more = f" (+{len(found) - SAMPLE} more)" if len(found) > SAMPLE else ""
                self.stdout.write(f"FOUND {len(found):>4}  {label}: {sample}{more}")
            else:
                self.stdout.write(f"OK          {label}")
        if problems:
            raise CommandError(
                f"{problems} integrity problem(s) found. Nothing was changed.",
                returncode=1,
            )
        self.stdout.write(self.style.SUCCESS("All integrity checks passed."))
