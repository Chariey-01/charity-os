"""Reflection edits never overwrite earlier words (Phase 0C, S8).

Each real change stores the record's previous content as a ReflectionRevision
first, under a row lock and a version check, so two devices cannot silently
overwrite each other and every earlier wording stays readable.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from execution.services import parse_version

from .models import DailyReflection, ReflectionRevision, WeeklyReview

EDITABLE = {
    DailyReflection: ("went_well", "learned", "improve", "mood", "closed_at"),
    WeeklyReview: ("wins", "lessons", "next_week", "closed_at"),
}
PARENT_FIELD = {DailyReflection: "daily_reflection", WeeklyReview: "weekly_review"}


class ReflectionVersionConflict(ValidationError):
    """Answered as HTTP 409 with error.code "version_conflict"."""

    code_name = "version_conflict"
    http_status = 409

    def __init__(self):
        super().__init__(
            "This reflection changed on another device. Refresh and try again."
        )


def content(record):
    """The editable words of a reflection, JSON-ready."""
    values = {}
    for field in EDITABLE[type(record)]:
        value = getattr(record, field)
        values[field] = value.isoformat() if hasattr(value, "isoformat") else value
    return values


@transaction.atomic
def revise(*, user, record, expected_version, changes):
    """Apply ``changes`` (already validated values) to a reflection.

    Needs the current version (409 if stale). Stores the previous content as a
    revision before changing anything. An edit that changes nothing writes
    nothing and keeps the version.
    """
    model = type(record)
    record = model.objects.select_for_update().get(pk=record.pk, user=user)
    expected = parse_version(expected_version)
    if expected is None:
        raise ValidationError(
            {"expected_version": "Send the current version to edit this."}
        )
    if record.version != expected:
        raise ReflectionVersionConflict()
    if record.archived_at is not None:
        raise ValidationError("This is archived. Restore it before editing.")
    refused = sorted(set(changes) - set(EDITABLE[model]))
    if refused:
        raise ValidationError({field: "This cannot be changed." for field in refused})
    before = content(record)
    for field, value in changes.items():
        setattr(record, field, value)
    if content(record) == before:
        return model.objects.get(pk=record.pk)
    ReflectionRevision.objects.create(
        user=user,
        version=record.version,
        content=before,
        **{PARENT_FIELD[model]: record},
    )
    record.version += 1
    record.save(update_fields=(*changes, "version"))
    return record


def history(record):
    """Earlier versions of a reflection, newest first."""
    return [
        {
            "version": revision.version,
            "content": revision.content,
            "replaced_at": revision.created_at,
        }
        for revision in ReflectionRevision.objects.filter(
            **{PARENT_FIELD[type(record)]: record}
        ).order_by("-version")
    ]
