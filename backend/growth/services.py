"""State changes for vision, goals, milestones and projects.

Every status change goes through here so that it writes exactly one
append-only ActivityEvent with a snapshot taken at that moment. My Journey
reads those snapshots, so renaming a goal or moving a task to another
workstream later never rewrites what was achieved, or where.
"""

from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    ActivityEvent,
    Goal,
    GoalCheckIn,
    JournalEntry,
    Milestone,
    Project,
    VisionItem,
    VisionRevision,
)


def area_snapshot(area):
    if area is None:
        return None
    return {"id": str(area.pk), "label": area.name, "color": area.color}


def record(*, user, subject_type, subject, kind, title, data=None, when=None):
    return ActivityEvent.objects.create(
        user=user,
        subject_type=subject_type,
        subject_id=subject.pk,
        kind=kind,
        title=title[:200],
        data=data or {},
        occurred_at=when or timezone.now(),
    )


def _lock(model, user, obj):
    return model.objects.select_for_update().get(pk=obj.pk, user=user)


def _https(url, field):
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError({field: "Links must use HTTPS."})


# --- Vision ------------------------------------------------------------------

VISION_TEXT_FIELDS = ("title", "statement", "success_looks_like")


@transaction.atomic
def revise_vision(*, user, vision, changes):
    """Apply ``changes``; if the wording changes, keep the old wording first."""
    vision = _lock(VisionItem, user, vision)
    wording_changed = any(
        field in changes and changes[field] != getattr(vision, field)
        for field in VISION_TEXT_FIELDS
    )
    if wording_changed:
        VisionRevision.objects.create(
            user=user,
            vision=vision,
            version=vision.version,
            title=vision.title,
            statement=vision.statement,
            success_looks_like=vision.success_looks_like,
        )
        vision.version += 1
    for field, value in changes.items():
        setattr(vision, field, value)
    vision.full_clean(exclude=("user",))
    vision.save()
    if wording_changed:
        record(
            user=user,
            subject_type="vision",
            subject=vision,
            kind="revised",
            title=vision.title,
            data={"version": vision.version},
        )
    return vision


@transaction.atomic
def realise_vision(*, user, vision, note="", evidence_url="", confirm=False):
    """Mark an intention realised. Needs evidence or an explicit confirmation.

    A manifestation is an intention, not an assumed achievement: nothing in
    CharityOS realises one automatically.
    """
    note = (note or "").strip()
    evidence_url = (evidence_url or "").strip()
    _https(evidence_url, "evidence_url")
    if not evidence_url and not confirm:
        raise ValidationError(
            {
                "confirm": "Add evidence (a link) or confirm explicitly that this "
                "has come true."
            }
        )
    vision = _lock(VisionItem, user, vision)
    if vision.status == VisionItem.Status.REALISED:
        return vision
    vision.status = VisionItem.Status.REALISED
    vision.realised_at = timezone.now()
    vision.realised_note = note
    vision.realised_evidence_url = evidence_url
    vision.save()
    record(
        user=user,
        subject_type="vision",
        subject=vision,
        kind="realised",
        title=vision.title,
        data={
            "kind": vision.kind,
            "theme": vision.theme,
            "note": note,
            "evidence_url": evidence_url,
            "confirmed_without_evidence": not evidence_url,
        },
    )
    return vision


@transaction.atomic
def set_vision_status(*, user, vision, status):
    """Back to working towards it, or let it go. Realising uses realise_vision."""
    if status not in (VisionItem.Status.ACTIVE, VisionItem.Status.RELEASED):
        raise ValidationError({"status": "Use active or released here."})
    vision = _lock(VisionItem, user, vision)
    if vision.status == status:
        return vision
    previous = vision.status
    vision.status = status
    vision.realised_at = None
    vision.save()
    record(
        user=user,
        subject_type="vision",
        subject=vision,
        kind="status_changed",
        title=vision.title,
        data={"from": previous, "to": status},
    )
    return vision


# --- Goals -------------------------------------------------------------------


def _goal_snapshot(goal):
    return {
        "area": area_snapshot(goal.area),
        "vision": goal.vision.title if goal.vision_id else None,
        "kind": goal.kind,
        "target_value": str(goal.target_value) if goal.target_value is not None else None,
        "metric_unit": goal.metric_unit,
    }


@transaction.atomic
def set_goal_status(*, user, goal, status, note=""):
    if status not in Goal.Status.values:
        raise ValidationError({"status": "Choose a valid goal status."})
    goal = _lock(Goal, user, goal)
    previous = goal.status
    if previous == status:
        return goal
    goal.status = status
    if status == Goal.Status.COMPLETED:
        goal.completed_at = timezone.now()
        goal.completion_note = (note or "").strip()
    else:
        goal.completed_at = None
    goal.save()
    kind = (
        "completed"
        if status == Goal.Status.COMPLETED
        else "reopened"
        if previous == Goal.Status.COMPLETED
        else "status_changed"
    )
    record(
        user=user,
        subject_type="goal",
        subject=goal,
        kind=kind,
        title=goal.title,
        data={**_goal_snapshot(goal), "from": previous, "to": status, "note": note},
    )
    return goal


@transaction.atomic
def check_in(*, user, goal, local_date, value=None, note=""):
    goal = _lock(Goal, user, goal)
    note = (note or "").strip()
    if goal.kind == Goal.Kind.MEASURABLE and value is None:
        raise ValidationError({"value": "Record the measured value for this goal."})
    if value is None and not note:
        raise ValidationError({"note": "Write a short progress note."})
    checkin = GoalCheckIn.objects.create(
        user=user, goal=goal, local_date=local_date, value=value, note=note
    )
    record(
        user=user,
        subject_type="goal",
        subject=goal,
        kind="checkin",
        title=goal.title,
        data={
            "value": str(value) if value is not None else None,
            "unit": goal.metric_unit,
            "note": note,
            "local_date": local_date.isoformat(),
        },
    )
    return checkin


@transaction.atomic
def carry_forward_goal(*, user, goal, target_date, note=""):
    """Deliberately continue an unfinished goal into a new period."""
    goal = _lock(Goal, user, goal)
    if goal.status == Goal.Status.COMPLETED:
        raise ValidationError({"status": "This goal is already completed."})
    previous = goal.target_date
    goal.target_date = target_date
    if goal.status != Goal.Status.ACTIVE:
        goal.status = Goal.Status.ACTIVE
    goal.full_clean(exclude=("user",))
    goal.save()
    record(
        user=user,
        subject_type="goal",
        subject=goal,
        kind="carried_forward",
        title=goal.title,
        data={
            "from": previous.isoformat() if previous else None,
            "to": target_date.isoformat(),
            "note": (note or "").strip(),
        },
    )
    return goal


def goal_progress(goal, today=None):
    """How far a goal has come, from records only. Never invented.

    Measurable goals use the latest check-in against baseline and target.
    Qualitative goals use completed milestones. With neither, ``ratio`` is
    None and the app says that no measure exists yet.
    """
    today = today or date.today()
    milestones = [m for m in goal.milestones.all() if m.archived_at is None]
    done_milestones = sum(1 for m in milestones if m.status == Milestone.Status.DONE)
    tasks = [t for t in goal.tasks.all() if t.archived_at is None]
    done_tasks = sum(1 for t in tasks if t.status == "done")
    latest = None
    ratio = None
    basis = "none"
    if goal.kind == Goal.Kind.MEASURABLE and goal.target_value is not None:
        checkins = sorted(
            (c for c in goal.checkins.all() if c.value is not None),
            key=lambda c: (c.local_date, c.created_at),
        )
        if checkins:
            latest = checkins[-1].value
            base = goal.baseline_value or Decimal(0)
            span = goal.target_value - base
            if span != 0:
                ratio = float(max(Decimal(0), min(Decimal(1), (latest - base) / span)))
            basis = "measure"
    elif milestones:
        ratio = done_milestones / len(milestones)
        basis = "milestones"
    if goal.status == Goal.Status.COMPLETED:
        ratio = 1.0 if ratio is None else ratio
    overdue = bool(
        goal.target_date
        and goal.status == Goal.Status.ACTIVE
        and goal.target_date < today
    )
    at_risk = False
    if (
        not overdue
        and goal.status == Goal.Status.ACTIVE
        and goal.start_date
        and goal.target_date
        and ratio is not None
        and goal.target_date > goal.start_date
    ):
        elapsed = (today - goal.start_date).days / (goal.target_date - goal.start_date).days
        # More than a fifth of the time ahead of the measured progress.
        at_risk = elapsed - ratio > 0.2 and elapsed > 0.25
    return {
        "ratio": ratio,
        "basis": basis,
        "latest_value": str(latest) if latest is not None else None,
        "milestones_total": len(milestones),
        "milestones_done": done_milestones,
        "tasks_total": len(tasks),
        "tasks_done": done_tasks,
        "overdue": overdue,
        "at_risk": at_risk,
        "days_left": (goal.target_date - today).days if goal.target_date else None,
    }


# --- Milestones --------------------------------------------------------------


def _milestone_snapshot(milestone):
    parent = milestone.goal or milestone.project
    return {
        "goal": milestone.goal.title if milestone.goal_id else None,
        "goal_id": str(milestone.goal_id) if milestone.goal_id else None,
        "project": milestone.project.name if milestone.project_id else None,
        "project_id": str(milestone.project_id) if milestone.project_id else None,
        "area": area_snapshot(getattr(parent, "area", None)),
    }


@transaction.atomic
def set_milestone_status(*, user, milestone, status, note=""):
    if status not in Milestone.Status.values:
        raise ValidationError({"status": "Use open or done."})
    milestone = _lock(Milestone, user, milestone)
    if milestone.status == status:
        return milestone
    milestone.status = status
    if status == Milestone.Status.DONE:
        milestone.completed_at = timezone.now()
        milestone.completion_note = (note or "").strip()
    else:
        milestone.completed_at = None
    milestone.save()
    record(
        user=user,
        subject_type="milestone",
        subject=milestone,
        kind="completed" if status == Milestone.Status.DONE else "reopened",
        title=milestone.title,
        data={**_milestone_snapshot(milestone), "note": note},
    )
    return milestone


# --- Projects ----------------------------------------------------------------


@transaction.atomic
def set_project_status(*, user, project, status, note=""):
    if status not in Project.Status.values:
        raise ValidationError({"status": "Choose a valid project status."})
    project = _lock(Project, user, project)
    previous = project.status
    if previous == status:
        return project
    project.status = status
    project.completed_at = timezone.now() if status == Project.Status.COMPLETED else None
    project.save()
    record(
        user=user,
        subject_type="project",
        subject=project,
        kind="completed"
        if status == Project.Status.COMPLETED
        else "reopened"
        if previous == Project.Status.COMPLETED
        else "status_changed",
        title=project.name,
        data={
            "from": previous,
            "to": status,
            "note": (note or "").strip(),
            "area": area_snapshot(project.area),
            "goal": project.goal.title if project.goal_id else None,
        },
    )
    return project


# --- Journal -----------------------------------------------------------------


@transaction.atomic
def edit_journal_entry(*, user, entry, changes):
    """Edits keep the previous wording; history is never silently rewritten."""
    entry = _lock(JournalEntry, user, entry)
    if any(
        field in changes and changes[field] != getattr(entry, field)
        for field in ("title", "body")
    ):
        entry.revisions = [
            *entry.revisions,
            {
                "title": entry.title,
                "body": entry.body,
                "replaced_at": timezone.now().isoformat(),
            },
        ]
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.save()
    return entry
