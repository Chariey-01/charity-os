"""Permanently erase one account and everything it owns. Dry run by default.

    manage.py erase_user EMAIL                   # shows what would be erased
    manage.py erase_user EMAIL --confirm EMAIL   # erases it

This is the only way CharityOS deletes history (owner decision 4.3). The
plan comes from Django's own deletion collector, so the dry run lists
exactly what a real run removes. A real run:

* needs --confirm with the same email;
* refuses if any other user's record points into this user's data;
* runs in one transaction and rolls back unless the rows removed match
  the plan exactly and every other user's row count is unchanged.

Take a backup first (ops/db/backup.sh); an erasure cannot be undone except
by restoring that backup into a new database.
"""

import logging
from collections import Counter, defaultdict

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import router, transaction
from django.db.models import ProtectedError, RestrictedError
from django.db.models.deletion import Collector

from config.security import security_event


# Two-party records (community app): an accountability partnership belongs to
# both the person sharing and the partner, and its cheers to both as well, so
# erasing either person removes the relationship and nothing else of the other.
# A beta invite belongs to the admin who created it.
def _owners(obj, user_model):
    if isinstance(obj, user_model):
        return {obj.pk}
    label = obj._meta.label
    if label == "community.Partnership":
        return {obj.owner_id, obj.partner_id}
    if label == "community.Cheer":
        return {obj.sender_id, obj.partnership.owner_id, obj.partnership.partner_id}
    if label == "community.BetaInvite":
        return {obj.created_by_id}
    return {getattr(obj, "user_id", None)}


TWO_PARTY = {"community.Partnership", "community.Cheer", "community.BetaInvite"}

# Auto-created many-to-many link tables of two-party records: a link row goes
# when either side is erased (a shared goal, or the partnership itself).
LINK_TABLES = {"community.Partnership_goals", "community.Partnership_weekly_reviews"}


def erasure_plan(user):
    """{model label: rows} that deleting ``user`` would remove.

    Raises CommandError when another user's data is involved in any way.
    """
    user_model = type(user)
    collector = Collector(using=router.db_for_write(user_model, instance=user))
    try:
        collector.collect([user])
    except (ProtectedError, RestrictedError) as exc:
        blocked = getattr(exc, "protected_objects", None) or exc.restricted_objects
        kinds = Counter(obj._meta.label for obj in blocked)
        raise CommandError(
            "Refusing: records outside this account still point at its data "
            f"({dict(kinds)}). Nothing was deleted."
        ) from exc
    # The same row can be reached along several cascade paths (a prerequisite
    # link through its user and through its node), so count distinct rows.
    rows = defaultdict(set)
    foreign = Counter()
    for model, objects in collector.data.items():
        for obj in objects:
            rows[model._meta.label].add(obj.pk)
            if user.pk not in _owners(obj, user_model):
                foreign[model._meta.label] += 1
    for queryset in collector.fast_deletes:
        model = queryset.model
        if model._meta.label in TWO_PARTY:
            for obj in queryset:
                if obj.pk not in rows[model._meta.label] and user.pk not in _owners(
                    obj, user_model
                ):
                    foreign[model._meta.label] += 1
                rows[model._meta.label].add(obj.pk)
            continue
        owned = any(field.attname == "user_id" for field in model._meta.concrete_fields)
        pairs = (
            queryset.values_list("pk", "user_id")
            if owned
            else ((pk, None) for pk in queryset.values_list("pk", flat=True))
        )
        for pk, owner in pairs:
            linked = model._meta.label in LINK_TABLES
            if pk not in rows[model._meta.label] and owner != user.pk and not linked:
                foreign[model._meta.label] += 1
            rows[model._meta.label].add(pk)
    if collector.field_updates:
        foreign["(field updates)"] += 1
    foreign = {label: count for label, count in foreign.items() if count}
    if foreign:
        raise CommandError(
            "Refusing: erasing this account would also change records it does "
            f"not own ({foreign}). Nothing was deleted."
        )
    return {label: len(pks) for label, pks in sorted(rows.items()) if pks}


# django-axes keeps failed sign-in attempts by email (no foreign key), so the
# deletion collector cannot see them. They are personal data of the account.
LOGIN_RECORD_MODELS = ("axes.AccessAttempt", "axes.AccessFailureLog", "axes.AccessLog")


def login_records(email):
    """{label: queryset} of sign-in records kept under this email."""
    found = {}
    for label in LOGIN_RECORD_MODELS:
        try:
            model = apps.get_model(label)
        except LookupError:
            continue
        found[label] = model.objects.filter(username__iexact=email)
    return found


def session_records(user):
    """{label: queryset} of this account's sign-in sessions.

    Sessions hold the user id inside their encoded data, not in a column, so
    the deletion collector cannot see them either. Erasure is rare; reading
    every session to find the account's is acceptable.
    """
    try:
        model = apps.get_model("sessions.Session")
    except LookupError:
        return {}
    owned = [
        session.pk
        for session in model.objects.iterator()
        if session.get_decoded().get("_auth_user_id") == str(user.pk)
    ]
    return {model._meta.label: model.objects.filter(pk__in=owned)}


def other_users_rows(user_id):
    """Row counts of every per-user table, excluding ``user_id``'s rows."""
    user_model = get_user_model()
    counts = {user_model._meta.label: user_model.objects.exclude(pk=user_id).count()}
    for model in apps.get_models():
        if any(
            field.attname == "user_id" and field.related_model is user_model
            for field in model._meta.concrete_fields
            if field.is_relation
        ):
            counts[model._meta.label] = model.objects.exclude(user_id=user_id).count()
    return counts


class Command(BaseCommand):
    help = "Permanently erase one account and all its data (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "--confirm",
            metavar="EMAIL",
            help="Repeat the account's email to erase it for real.",
        )

    def handle(self, *args, email, confirm, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(email__iexact=email.strip())
        except user_model.DoesNotExist as exc:
            raise CommandError(f"No account with email {email!r}.") from exc
        if confirm is not None and confirm.strip().lower() != user.email.lower():
            raise CommandError(
                "--confirm does not match the account's email. Nothing was deleted."
            )

        with transaction.atomic():
            user = user_model.objects.select_for_update().get(pk=user.pk)
            plan = erasure_plan(user)
            records = {**login_records(user.email), **session_records(user)}
            plan.update(
                {
                    label: rows.count()
                    for label, rows in records.items()
                    if rows.exists()
                }
            )
            self._show(user, plan)
            if confirm is None:
                security_event("erasure_dry_run", user=user, rows=sum(plan.values()))
                self.stdout.write(
                    "DRY RUN: nothing was deleted.\n"
                    "Take a backup first:  ops/db/backup.sh --database <database>\n"
                    f"Then erase for real:  manage.py erase_user {user.email} "
                    f"--confirm {user.email}"
                )
                return
            user_id = user.pk
            others_before = other_users_rows(user_id)
            _, deleted = user.delete()
            for rows in records.values():
                for label, count in rows.delete()[1].items():
                    # Lockout expirations cascade with attempts; count only
                    # the planned tables.
                    if label in records:
                        deleted[label] = deleted.get(label, 0) + count
            deleted = {
                label: count for label, count in sorted(deleted.items()) if count
            }
            if deleted != plan:
                raise CommandError(
                    f"Rolled back: removed {deleted}, planned {plan}. Nothing was deleted."
                )
            if other_users_rows(user_id) != others_before:
                raise CommandError(
                    "Rolled back: other accounts' data would have changed. "
                    "Nothing was deleted."
                )
        security_event(
            "user_erased",
            email=user.email,
            user_id=user_id,
            rows=sum(plan.values()),
            level=logging.WARNING,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Erased {user.email}: {sum(plan.values())} rows.")
        )

    def _show(self, user, plan):
        self.stdout.write(f"Erasure plan for {user.email} (id {user.pk}):")
        width = max(len(label) for label in plan)
        for label, count in plan.items():
            self.stdout.write(f"  {label:<{width}}  {count}")
        self.stdout.write(
            f"  {'total':<{width}}  {sum(plan.values())} rows in {len(plan)} tables"
        )
