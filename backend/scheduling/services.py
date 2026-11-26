"""Transactional schedule-entry services.

Every mutation locks the entry row, checks an optional ``expected_version``
and is idempotent when the entry already reached the requested state. Focus
entries delegate all clock changes to ``execution.services`` so the
server-authoritative timer stays the only source of focused time.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from execution.models import FocusSession
from execution.services import end_session, pause_session, resume_session, start_session
from planning.models import Task
from planning.services import transition_task

from .models import MAX_ENTRY_SECONDS, ScheduleEntry

Status = ScheduleEntry.Status
Tracking = ScheduleEntry.Tracking


class ScheduleConflict(ValidationError):
    """Base for errors the API reports as HTTP 409."""

    code_name = "conflict"


class VersionConflict(ScheduleConflict):
    code_name = "version_conflict"

    def __init__(self):
        super().__init__(
            "This activity changed on another device. Refresh and try again."
        )


class ScheduleOverlap(ScheduleConflict):
    code_name = "schedule_overlap"

    def __init__(self, conflicts):
        self.conflicts = list(conflicts)
        titles = ", ".join(entry.title for entry in self.conflicts[:3])
        super().__init__(f"This time overlaps with {titles}.")


# --------------------------------------------------------------------------
# Time handling


def validate_timezone_name(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise ValidationError(
            {"timezone_name": "Timezone must be a valid IANA zone name."}
        ) from error


def resolve_local(value, tz_name, field="start_local"):
    """Convert a naive wall-clock datetime in ``tz_name`` to an aware instant.

    Wall-clock times inside a DST gap do not exist and are rejected. Ambiguous
    times (DST fold) resolve to their first occurrence.
    """
    zone = validate_timezone_name(tz_name)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValidationError({field: "Use YYYY-MM-DDTHH:MM."}) from error
    if value.tzinfo is not None:
        raise ValidationError(
            {field: "Send a local wall-clock time without an offset."}
        )
    aware = value.replace(tzinfo=zone, fold=0)
    round_trip = aware.astimezone(ZoneInfo("UTC")).astimezone(zone)
    if round_trip.replace(tzinfo=None) != value:
        raise ValidationError(
            {field: f"{value:%Y-%m-%d %H:%M} does not exist in {tz_name} (DST)."}
        )
    return aware


def local_date_for(instant, tz_name):
    return instant.astimezone(ZoneInfo(tz_name)).date()


def _validate_window(start_at, end_at):
    if end_at <= start_at:
        raise ValidationError({"end_local": "The end must be after the start."})
    if (end_at - start_at).total_seconds() > MAX_ENTRY_SECONDS:
        raise ValidationError({"end_local": "An activity can last at most 24 hours."})


def find_overlaps(user, start_at, end_at, exclude_ids=()):
    return (
        ScheduleEntry.objects.filter(
            user=user,
            status__in=ScheduleEntry.OPEN_STATUSES,
            start_at__lt=end_at,
            end_at__gt=start_at,
        )
        .exclude(pk__in=[pk for pk in exclude_ids if pk])
        .order_by("start_at")
    )


def _lock_user(user):
    """Serialise schedule writes per user so overlap checks cannot race."""
    get_user_model().objects.select_for_update().filter(pk=user.pk).first()


def _check_owner(user, **related):
    for name, value in related.items():
        if value is not None and value.user_id != user.id:
            raise ValidationError({name: "Choose one of your own records."})


def _locked(user, entry_id):
    try:
        return (
            ScheduleEntry.objects.select_for_update(of=("self",))
            .select_related("focus_session")
            .get(pk=entry_id, user=user)
        )
    except (ScheduleEntry.DoesNotExist, ValidationError, ValueError) as error:
        raise ScheduleEntry.DoesNotExist("Activity not found.") from error


def _check_version(entry, expected_version):
    if expected_version not in (None, "") and int(expected_version) != entry.version:
        raise VersionConflict()


def _save(entry, *fields):
    entry.version += 1
    entry.save(update_fields=(*fields, "version", "updated_at"))
    return entry


# --------------------------------------------------------------------------
# Create / update


@transaction.atomic
def create_entry(
    *,
    user,
    title,
    start_at,
    end_at,
    timezone_name,
    entry_id=None,
    area=None,
    task=None,
    roadmap_node=None,
    tracking=Tracking.MANUAL,
    description="",
    notes="",
    allow_overlap=False,
    rescheduled_from=None,
):
    """Create an entry. Replaying the same ``entry_id`` returns the original."""
    _lock_user(user)
    if entry_id:
        existing = ScheduleEntry.objects.filter(pk=entry_id).first()
        if existing:
            if existing.user_id != user.id:
                raise ValidationError({"id": "This id is already in use."})
            existing._replayed = True
            return existing
    if not (title or "").strip():
        raise ValidationError({"title": "Give the activity a title."})
    validate_timezone_name(timezone_name)
    _check_owner(user, area=area, task=task, roadmap_node=roadmap_node)
    if area is not None and area.archived_at is not None:
        raise ValidationError({"area": "This category is archived."})
    _validate_window(start_at, end_at)
    if not allow_overlap:
        exclude = (rescheduled_from.pk,) if rescheduled_from else ()
        conflicts = list(find_overlaps(user, start_at, end_at, exclude)[:5])
        if conflicts:
            raise ScheduleOverlap(conflicts)
    return ScheduleEntry.objects.create(
        id=entry_id or uuid.uuid4(),
        user=user,
        title=title.strip(),
        description=description,
        notes=notes,
        area=area,
        area_label_snapshot=area.name if area else "",
        start_at=start_at,
        end_at=end_at,
        timezone_name=timezone_name,
        local_date=local_date_for(start_at, timezone_name),
        tracking=tracking,
        task=task,
        roadmap_node=roadmap_node,
        rescheduled_from=rescheduled_from,
    )


ALWAYS_EDITABLE = ("notes", "outcome")
OPEN_EDITABLE = ("title", "description", "area", "task", "roadmap_node")
SCHEDULED_EDITABLE = ("tracking", "start_at", "end_at", "timezone_name")


@transaction.atomic
def update_entry(
    *, user, entry_id, changes, expected_version=None, allow_overlap=False
):
    """Edit an entry. Times may only move while it is still ``scheduled``."""
    _lock_user(user)
    entry = _locked(user, entry_id)
    _check_version(entry, expected_version)
    for field in changes:
        if field in ALWAYS_EDITABLE:
            continue
        if field in OPEN_EDITABLE and entry.status in ScheduleEntry.OPEN_STATUSES:
            continue
        if field in SCHEDULED_EDITABLE and entry.status == Status.SCHEDULED:
            continue
        if field in SCHEDULED_EDITABLE:
            raise ValidationError(
                {field: "Only a scheduled activity can be moved. Reschedule it."}
            )
        raise ValidationError({field: "A closed activity can only change notes."})
    if "title" in changes and not (changes["title"] or "").strip():
        raise ValidationError({"title": "Give the activity a title."})
    _check_owner(
        user,
        area=changes.get("area"),
        task=changes.get("task"),
        roadmap_node=changes.get("roadmap_node"),
    )
    if changes.get("area") is not None and changes["area"].archived_at is not None:
        raise ValidationError({"area": "This category is archived."})
    if "timezone_name" in changes:
        validate_timezone_name(changes["timezone_name"])
    for field, value in changes.items():
        setattr(entry, field, value.strip() if field == "title" else value)
    if "area" in changes:
        entry.area_label_snapshot = entry.area.name if entry.area else ""
    moved = bool({"start_at", "end_at", "timezone_name"} & changes.keys())
    if moved:
        _validate_window(entry.start_at, entry.end_at)
        entry.local_date = local_date_for(entry.start_at, entry.timezone_name)
        if not allow_overlap:
            conflicts = list(
                find_overlaps(user, entry.start_at, entry.end_at, (entry.pk,))[:5]
            )
            if conflicts:
                raise ScheduleOverlap(conflicts)
    fields = set(changes) | ({"area_label_snapshot"} if "area" in changes else set())
    if moved:
        fields.add("local_date")
    return _save(entry, *sorted(fields))


# --------------------------------------------------------------------------
# Lifecycle


@transaction.atomic
def start_entry(*, user, entry_id, expected_version=None, session_id=None):
    entry = _locked(user, entry_id)
    if entry.status in ScheduleEntry.RUNNING_STATUSES:
        return entry
    _check_version(entry, expected_version)
    if entry.status != Status.SCHEDULED:
        raise ValidationError("Only a scheduled activity can be started.")
    now = timezone.now()
    if entry.tracking == Tracking.FOCUS:
        if entry.area is None:
            raise ValidationError(
                {"area": "Choose a category before starting a focus session."}
            )
        if FocusSession.objects.filter(
            user=user, status__in=("active", "paused")
        ).exists():
            raise ValidationError(
                "Finish or pause your current focus session before starting another."
            )
        session = start_session(
            user=user,
            session_id=session_id or uuid.uuid4(),
            area=entry.area,
            title=entry.title,
            is_deep_work=True,
            task=entry.task,
            roadmap_item=entry.roadmap_node,
        )
        if ScheduleEntry.objects.filter(focus_session=session).exists():
            raise ValidationError({"session_id": "This focus session is in use."})
        entry.focus_session = session
        entry.status = Status.IN_PROGRESS
        return _save(entry, "focus_session", "status")
    entry.actual_started_at = now
    entry.status = Status.IN_PROGRESS
    return _save(entry, "actual_started_at", "status")


@transaction.atomic
def pause_entry(*, user, entry_id, expected_version=None, pause_id=None):
    entry = _locked(user, entry_id)
    if entry.status == Status.PAUSED:
        return entry
    _check_version(entry, expected_version)
    if entry.status != Status.IN_PROGRESS:
        raise ValidationError("Only an activity in progress can be paused.")
    if entry.focus_session_id:
        pause_session(
            user=user,
            session_id=entry.focus_session_id,
            pause_id=pause_id or uuid.uuid4(),
        )
        entry.status = Status.PAUSED
        return _save(entry, "status")
    entry.paused_at = timezone.now()
    entry.status = Status.PAUSED
    return _save(entry, "paused_at", "status")


def _close_manual_pause(entry, now):
    if entry.paused_at is not None:
        entry.paused_seconds += max(0, int((now - entry.paused_at).total_seconds()))
        entry.paused_at = None


@transaction.atomic
def resume_entry(*, user, entry_id, expected_version=None):
    entry = _locked(user, entry_id)
    if entry.status == Status.IN_PROGRESS:
        return entry
    _check_version(entry, expected_version)
    if entry.status != Status.PAUSED:
        raise ValidationError("Only a paused activity can be resumed.")
    if entry.focus_session_id:
        resume_session(user=user, session_id=entry.focus_session_id)
        entry.status = Status.IN_PROGRESS
        return _save(entry, "status")
    _close_manual_pause(entry, timezone.now())
    entry.status = Status.IN_PROGRESS
    return _save(entry, "paused_at", "paused_seconds", "status")


@transaction.atomic
def complete_entry(
    *,
    user,
    entry_id,
    partial=False,
    outcome="",
    learning="",
    notes=None,
    actual_minutes=None,
    actual_started_at=None,
    actual_ended_at=None,
    complete_task=False,
    expected_version=None,
):
    """Close an entry as completed or partially completed.

    Actual time is taken from the timer when the entry was started. For an
    entry that was never started, only values the user supplies are recorded;
    without them the actual time stays unknown.
    """
    target = Status.PARTIALLY_COMPLETED if partial else Status.COMPLETED
    entry = _locked(user, entry_id)
    if entry.status == target:
        return entry
    _check_version(entry, expected_version)
    if entry.status not in ScheduleEntry.OPEN_STATUSES:
        raise ValidationError("This activity is already closed.")
    manual_values = (actual_minutes, actual_started_at, actual_ended_at)
    if actual_minutes is not None and not 0 <= int(actual_minutes) <= 24 * 60:
        raise ValidationError({"actual_minutes": "Use 0 to 1440 minutes."})
    now = timezone.now()
    fields = ["status", "outcome", "closed_at"]
    if entry.focus_session_id:
        if any(value is not None for value in manual_values):
            raise ValidationError(
                "Focus time comes from the timer. Correct the focus session instead."
            )
        end_session(
            user=user,
            session_id=entry.focus_session_id,
            target="completed",
            outcome=outcome,
            learning=learning,
        )
    elif entry.status in ScheduleEntry.RUNNING_STATUSES:
        if actual_started_at is not None or actual_ended_at is not None:
            raise ValidationError(
                "This activity was timed. Adjust the minutes instead of the times."
            )
        _close_manual_pause(entry, now)
        entry.actual_ended_at = now
        measured = int((now - entry.actual_started_at).total_seconds())
        entry.actual_duration_seconds = (
            int(actual_minutes) * 60
            if actual_minutes is not None
            else min(MAX_ENTRY_SECONDS, max(0, measured - entry.paused_seconds))
        )
        fields += [
            "paused_at",
            "paused_seconds",
            "actual_ended_at",
            "actual_duration_seconds",
        ]
    else:
        if (actual_started_at is None) != (actual_ended_at is None):
            raise ValidationError("Provide both the actual start and end, or neither.")
        if actual_started_at is not None:
            if actual_ended_at <= actual_started_at:
                raise ValidationError(
                    {"actual_ended_at": "The actual end must follow the start."}
                )
            if actual_ended_at > now + timedelta(minutes=5):
                raise ValidationError(
                    {"actual_ended_at": "The actual end cannot be in the future."}
                )
            span = int((actual_ended_at - actual_started_at).total_seconds())
            if span > MAX_ENTRY_SECONDS:
                raise ValidationError(
                    {"actual_ended_at": "An activity can last at most 24 hours."}
                )
            entry.actual_started_at = actual_started_at
            entry.actual_ended_at = actual_ended_at
            entry.actual_duration_seconds = span
        if actual_minutes is not None:
            entry.actual_duration_seconds = int(actual_minutes) * 60
        fields += ["actual_started_at", "actual_ended_at", "actual_duration_seconds"]
    entry.status = target
    entry.outcome = outcome or entry.outcome
    if notes is not None:
        entry.notes = notes
        fields.append("notes")
    entry.closed_at = now
    _save(entry, *fields)
    if complete_task and entry.task_id:
        task = Task.objects.get(pk=entry.task_id, user=user)
        if task.status in Task.OPEN_STATUSES:
            transition_task(user=user, task=task, target=Task.Status.DONE)
    return entry


@transaction.atomic
def skip_entry(*, user, entry_id, note="", expected_version=None):
    entry = _locked(user, entry_id)
    if entry.status == Status.SKIPPED:
        return entry
    _check_version(entry, expected_version)
    if entry.status != Status.SCHEDULED:
        raise ValidationError("Only a scheduled activity can be skipped.")
    entry.status = Status.SKIPPED
    entry.closed_at = timezone.now()
    if note:
        entry.notes = note
    return _save(entry, "status", "closed_at", "notes")


@transaction.atomic
def cancel_entry(*, user, entry_id, note="", expected_version=None):
    """Cancel an open entry. Cancelled time is kept for audit, not counted."""
    entry = _locked(user, entry_id)
    if entry.status == Status.CANCELLED:
        return entry
    _check_version(entry, expected_version)
    if entry.status not in ScheduleEntry.OPEN_STATUSES:
        raise ValidationError("Only an open activity can be cancelled.")
    now = timezone.now()
    fields = ["status", "closed_at", "notes"]
    if entry.focus_session_id:
        end_session(user=user, session_id=entry.focus_session_id, target="cancelled")
    elif entry.status in ScheduleEntry.RUNNING_STATUSES:
        _close_manual_pause(entry, now)
        entry.actual_ended_at = now
        fields += ["paused_at", "paused_seconds", "actual_ended_at"]
    entry.status = Status.CANCELLED
    entry.closed_at = now
    if note:
        entry.notes = note
    return _save(entry, *fields)


RESCHEDULABLE = (Status.SCHEDULED, Status.SKIPPED, Status.CANCELLED)


@transaction.atomic
def reschedule_entry(
    *,
    user,
    entry_id,
    start_at,
    end_at,
    timezone_name=None,
    new_entry_id=None,
    allow_overlap=False,
    expected_version=None,
):
    """Close the original as ``rescheduled`` and create a linked replacement."""
    _lock_user(user)
    original = _locked(user, entry_id)
    if original.status == Status.RESCHEDULED:
        return original.rescheduled_to
    _check_version(original, expected_version)
    if original.status not in RESCHEDULABLE:
        raise ValidationError("Finish or cancel this activity before rescheduling it.")
    replacement = create_entry(
        user=user,
        entry_id=new_entry_id,
        title=original.title,
        description=original.description,
        notes=original.notes,
        area=original.area,
        task=original.task,
        roadmap_node=original.roadmap_node,
        tracking=original.tracking,
        start_at=start_at,
        end_at=end_at,
        timezone_name=timezone_name or original.timezone_name,
        allow_overlap=allow_overlap,
        rescheduled_from=original,
    )
    original.status = Status.RESCHEDULED
    original.closed_at = original.closed_at or timezone.now()
    _save(original, "status", "closed_at")
    return replacement


SESSION_TO_ENTRY = {
    FocusSession.Status.ACTIVE: Status.IN_PROGRESS,
    FocusSession.Status.PAUSED: Status.PAUSED,
    FocusSession.Status.COMPLETED: Status.COMPLETED,
    FocusSession.Status.CANCELLED: Status.CANCELLED,
}


@transaction.atomic
def sync_entry_from_session(*, user, session):
    """Mirror a linked session's state after it changed via /sessions/."""
    entry = (
        ScheduleEntry.objects.select_for_update()
        .filter(user=user, focus_session_id=session.pk)
        .first()
    )
    if entry is None or entry.status in (
        Status.PARTIALLY_COMPLETED,
        Status.SKIPPED,
        Status.RESCHEDULED,
    ):
        return entry
    target = SESSION_TO_ENTRY[session.status]
    if entry.status == target:
        return entry
    fields = ["status"]
    entry.status = target
    if target in (Status.COMPLETED, Status.CANCELLED):
        entry.closed_at = session.ended_at or timezone.now()
        fields.append("closed_at")
        if target == Status.COMPLETED and not entry.outcome and session.outcome:
            entry.outcome = session.outcome
            fields.append("outcome")
    return _save(entry, *fields)


@transaction.atomic
def sync_entry_attribution(*, user, session):
    """Give a linked entry its corrected session's category, task and roadmap
    item (owner decision 4.5). Insights reads linked time through the entry,
    so the two must never disagree. Closed entries included."""
    entry = (
        ScheduleEntry.objects.select_for_update()
        .filter(user=user, focus_session_id=session.pk)
        .first()
    )
    if entry is None:
        return None
    wanted = {
        "area_id": session.area_id,
        "area_label_snapshot": session.area_label_snapshot,
        "task_id": session.task_id,
        "roadmap_node_id": session.roadmap_item_id,
    }
    changed = [
        field for field, value in wanted.items() if getattr(entry, field) != value
    ]
    if not changed:
        return entry
    for field in changed:
        setattr(entry, field, wanted[field])
    return _save(entry, *(field.removesuffix("_id") for field in changed))
