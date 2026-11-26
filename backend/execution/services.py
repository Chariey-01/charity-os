from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import FocusSession, FocusSessionCorrection, SessionPause


def _ancestry(node):
    result = []
    seen = set()
    while node and node.pk not in seen:  # stops at a parent cycle in old data
        seen.add(node.pk)
        result.append({"id": str(node.id), "title": node.title, "type": node.node_type})
        node = node.parent
    return list(reversed(result))


@transaction.atomic
def start_session(
    *, user, session_id, area, title, is_deep_work, task=None, roadmap_item=None
):
    existing = FocusSession.objects.filter(pk=session_id, user=user).first()
    if existing:
        return existing
    if (
        area.user_id != user.id
        or (task and task.user_id != user.id)
        or (roadmap_item and roadmap_item.user_id != user.id)
    ):
        raise ValidationError("Related objects must belong to the current user.")
    try:
        return FocusSession.objects.create(
            id=session_id,
            user=user,
            area=area,
            task=task,
            roadmap_item=roadmap_item,
            title=title,
            is_deep_work=is_deep_work,
            started_at=timezone.now(),
            timezone_snapshot=user.timezone,
            area_label_snapshot=area.name,
            task_type_snapshot=task.task_type if task else "",
            roadmap_ancestry_snapshot=_ancestry(roadmap_item),
        )
    except IntegrityError as error:
        raise ValidationError("A focus session is already open.") from error


class SessionVersionConflict(ValidationError):
    """Answered as HTTP 409 with error.code "version_conflict"."""

    code_name = "version_conflict"
    http_status = 409

    def __init__(self):
        super().__init__(
            "This focus session changed on another device. Refresh and try again."
        )


def parse_version(value):
    """``expected_version`` as an int, or None when absent. Never a raw string:
    "2" and 2 are the same version, and "two" is a field error, not a 500."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValidationError({"expected_version": "Send a whole number."})
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_version": "Send a whole number."}) from exc
    if number < 1 or str(number) != str(value).strip():
        raise ValidationError({"expected_version": "Send a whole number."})
    return number


def _locked(user, session_id):
    return FocusSession.objects.select_for_update().get(pk=session_id, user=user)


def _version(session, expected_version):
    expected = parse_version(expected_version)
    if expected is not None and session.version != expected:
        raise SessionVersionConflict()


class AttributionLocked(ValidationError):
    """Answered as HTTP 400 with error.code "use_correction"."""

    code_name = "use_correction"


ATTRIBUTION_FIELDS = ("area", "task", "roadmap_item", "is_deep_work")
EDITABLE_WHILE_OPEN = ("title", "notes", "outcome", "learning")
EDITABLE_AFTER_END = ("notes", "outcome", "learning")


@transaction.atomic
def update_session_details(*, user, session_id, expected_version, changes):
    """Edit a session's own words. Version-checked; attribution never changes here.

    Open sessions may change title, notes, outcome and learning; ended ones
    only notes, outcome and learning. Category, task, roadmap item and the
    deep-work flag change only through correct_session, which is audited and
    keeps the linked schedule entry in step.
    """
    session = _locked(user, session_id)
    expected = parse_version(expected_version)
    if expected is None:
        raise ValidationError(
            {"expected_version": "Send the session's current version to edit it."}
        )
    if session.version != expected:
        raise SessionVersionConflict()
    locked = [field for field in ATTRIBUTION_FIELDS if field in changes]
    if locked:
        raise AttributionLocked(
            {
                field: "Change this with POST /api/v1/sessions/<id>/corrections."
                for field in locked
            }
        )
    open_session = session.status in (
        FocusSession.Status.ACTIVE,
        FocusSession.Status.PAUSED,
    )
    allowed = EDITABLE_WHILE_OPEN if open_session else EDITABLE_AFTER_END
    refused = sorted(set(changes) - set(allowed))
    if refused:
        reason = (
            "Cannot be changed here."
            if open_session
            else "An ended session can only change notes, outcome and learning."
        )
        raise ValidationError({field: reason for field in refused})
    for field, value in changes.items():
        if not isinstance(value, str):
            raise ValidationError({field: "Send text."})
        if field == "title":
            value = value.strip()
            if not value or len(value) > 200:
                raise ValidationError({"title": "Give the session a title (200 max)."})
        setattr(session, field, value)
    if not changes:
        return session
    session.version += 1
    session.save(update_fields=(*changes, "version", "updated_at"))
    return session


@transaction.atomic
def pause_session(*, user, session_id, pause_id, expected_version=None):
    session = _locked(user, session_id)
    existing = SessionPause.objects.filter(
        pk=pause_id, user=user, session=session
    ).first()
    if existing:
        return session
    _version(session, expected_version)
    if session.status != FocusSession.Status.ACTIVE:
        raise ValidationError("Only an active session can be paused.")
    SessionPause.objects.create(
        id=pause_id, user=user, session=session, started_at=timezone.now()
    )
    session.status, session.version = FocusSession.Status.PAUSED, session.version + 1
    session.save(update_fields=("status", "version", "updated_at"))
    return session


@transaction.atomic
def resume_session(*, user, session_id, expected_version=None):
    session = _locked(user, session_id)
    _version(session, expected_version)
    if session.status == FocusSession.Status.ACTIVE:
        return session
    if session.status != FocusSession.Status.PAUSED:
        raise ValidationError("Only a paused session can be resumed.")
    pause = session.pauses.select_for_update().get(ended_at__isnull=True)
    pause.ended_at = timezone.now()
    pause.save(update_fields=("ended_at",))
    session.status, session.version = FocusSession.Status.ACTIVE, session.version + 1
    session.save(update_fields=("status", "version", "updated_at"))
    return session


@transaction.atomic
def end_session(
    *, user, session_id, target, expected_version=None, outcome="", learning=""
):
    session = _locked(user, session_id)
    _version(session, expected_version)
    if session.status == target:
        return session
    if session.status in (FocusSession.Status.COMPLETED, FocusSession.Status.CANCELLED):
        raise ValidationError("Session has already ended with a different state.")
    now = timezone.now()
    if session.status == FocusSession.Status.PAUSED:
        pause = session.pauses.select_for_update().get(ended_at__isnull=True)
        pause.ended_at = now
        pause.save(update_fields=("ended_at",))
    session.ended_at = now
    session.duration_seconds = session.elapsed_seconds(at=now)
    session.status = target
    session.outcome = outcome
    session.learning = learning
    session.version += 1
    session.save(
        update_fields=(
            "ended_at",
            "duration_seconds",
            "status",
            "outcome",
            "learning",
            "version",
            "updated_at",
        )
    )
    return session


@transaction.atomic
def correct_session(
    *, user, session_id, reason, started_at=None, ended_at=None, expected_version=None
):
    session = _locked(user, session_id)
    _version(session, expected_version)
    if session.status not in (
        FocusSession.Status.COMPLETED,
        FocusSession.Status.CANCELLED,
    ):
        raise ValidationError("Only a terminal session can be corrected.")
    if not reason.strip():
        raise ValidationError("A correction reason is required.")
    before = {
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat(),
        "duration_seconds": session.duration_seconds,
    }
    session.started_at = started_at or session.started_at
    session.ended_at = ended_at or session.ended_at
    if session.ended_at <= session.started_at:
        raise ValidationError("The corrected end must follow the start.")
    session.duration_seconds = session.elapsed_seconds(at=session.ended_at)
    session.version += 1
    after = {
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat(),
        "duration_seconds": session.duration_seconds,
    }
    session.save(
        update_fields=(
            "started_at",
            "ended_at",
            "duration_seconds",
            "version",
            "updated_at",
        )
    )
    FocusSessionCorrection.objects.create(
        user=user, session=session, reason=reason.strip(), before=before, after=after
    )
    return session
