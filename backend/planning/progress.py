"""Task progress that stays true over time.

Everything here is derived from records that are never rewritten: tasks,
append-only PlanningEvents (status, due-date, archive and plan changes),
schedule entries and focus sessions. A past week is judged **as it stood at
the end of that week**, not by what tasks look like today, so completing,
deferring or archiving something later never changes an earlier week.

Definitions (also shown to the user):

* **Overall** (now): tasks that are not archived. Done / (done + open);
  cancelled tasks are left out. Overdue: open with a due date before today.
* **A week's planned workload**, as of the end of the week (or now, for the
  current week): tasks that existed, were not archived, not cancelled and
  not already done before the week began, and that were planned into the
  week in at least one way:
    1. their due date fell in the week;
    2. they had a schedule entry in the week that had not been cancelled
       or moved elsewhere;
    3. they were on a daily plan in the week and had not been carried over
       or removed.
  Each task counts once, however many ways it was planned.
* **Completed in a week**: done at the end of the week, with its last
  completion inside the week. Completions of unplanned tasks are reported
  separately and are not part of the weekly percentage.
* **Weekly completion %** = planned tasks completed in the week / planned
  workload. With no planned workload there is no percentage.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from execution.models import FocusSession
from records.models import Accomplishment, Evidence
from roadmaps.models import RoadmapNode
from scheduling.insights import category_time, local_bounds, week_start
from scheduling.models import ScheduleEntry

from .models import DailyPlanItem, PlanningEvent, Task

OPEN = frozenset(Task.OPEN_STATUSES)
DONE = Task.Status.DONE
CANCELLED = Task.Status.CANCELLED
# Events written before the workflow statuses carry no "to"; their meaning is fixed.
EVENT_STATUS = {"completed": DONE, "skipped": CANCELLED, "reopened": Task.Status.TODO}
STATUS_EVENTS = frozenset(("completed", "skipped", "reopened", "status_changed"))
NO_AREA = {"area": None, "label": "No workstream", "color": "#94A3B8"}


def _date(value):
    return date.fromisoformat(value) if value else None


@dataclass
class History:
    """One task's reconstructable past."""

    task: Task
    statuses: list = field(default_factory=list)  # (when, from, to)
    dues: list = field(default_factory=list)  # (when, from, to)
    archives: list = field(default_factory=list)  # (when, archived?)

    def exists(self, moment):
        return self.task.created_at <= moment

    def status_at(self, moment):
        before = [change for change in self.statuses if change[0] <= moment]
        if before:
            return before[-1][2]
        if self.statuses:
            return self.statuses[0][1] or Task.Status.TODO
        # No events: only the terminal timestamps say when it changed.
        task = self.task
        if task.status == DONE and task.completed_at and task.completed_at > moment:
            return Task.Status.TODO
        if (
            task.status == CANCELLED
            and task.cancelled_at
            and task.cancelled_at > moment
        ):
            return Task.Status.TODO
        return task.status

    def completed_at(self, moment):
        """When the task last became done, as known at ``moment``."""
        if self.status_at(moment) != DONE:
            return None
        done = [when for when, _, to in self.statuses if to == DONE and when <= moment]
        if done:
            return done[-1]
        return self.task.completed_at

    def due_at(self, moment):
        before = [change for change in self.dues if change[0] <= moment]
        if before:
            return before[-1][2]
        if self.dues:
            return self.dues[0][1]
        return self.task.due_date

    def archived_at(self, moment):
        before = [archived for when, archived in self.archives if when <= moment]
        if before:
            return before[-1]
        if self.archives:
            return not self.archives[0][1]
        return self.task.archived_at is not None and self.task.archived_at <= moment


def histories(user, created_before):
    tasks = {
        task.id: History(task)
        for task in Task.objects.filter(
            user=user, created_at__lt=created_before
        ).select_related("area")
    }
    events = PlanningEvent.objects.filter(user=user, task_id__in=tasks).order_by(
        "created_at", "id"
    )
    for event in events:
        history = tasks[event.task_id]
        snap = event.snapshot or {}
        kind = event.event_type
        if kind in STATUS_EVENTS:
            to = snap.get("to") or EVENT_STATUS.get(kind)
            if to:
                history.statuses.append((event.created_at, snap.get("from"), to))
        elif kind == PlanningEvent.EventType.DUE_CHANGED:
            history.dues.append(
                (event.created_at, _date(snap.get("from")), _date(snap.get("to")))
            )
        elif kind == PlanningEvent.EventType.ARCHIVED:
            history.archives.append((event.created_at, True))
        elif kind == PlanningEvent.EventType.RESTORED:
            history.archives.append((event.created_at, False))
    return tasks


def _area(task):
    if task.area is None:
        return dict(NO_AREA)
    return {
        "area": str(task.area_id),
        "label": task.area.name,
        "color": task.area.color,
    }


def _scheduled_in(user, start, end, as_of):
    """Task ids with a schedule entry in the week that, at ``as_of``, still stood."""
    entries = ScheduleEntry.objects.filter(
        user=user, task__isnull=False, local_date__range=(start, end)
    ).exclude(status=ScheduleEntry.Status.CANCELLED)
    moved = dict(
        ScheduleEntry.objects.filter(
            user=user, rescheduled_from__in=entries
        ).values_list("rescheduled_from_id", "created_at")
    )
    return {
        entry.task_id
        for entry in entries
        if entry.status != ScheduleEntry.Status.RESCHEDULED
        or moved.get(entry.id, as_of) > as_of
    }


def _plan_items_in(user, start, end, as_of):
    """Task ids on a daily plan in the week, not carried over or removed by ``as_of``."""
    items = DailyPlanItem.objects.filter(
        plan__user=user, task__isnull=False, plan__local_date__range=(start, end)
    )
    left = set(
        PlanningEvent.objects.filter(
            user=user,
            source_item__in=items,
            event_type__in=("carried_over", "removed"),
            created_at__lte=as_of,
        ).values_list("source_item_id", flat=True)
    )
    return {item.task_id for item in items if item.id not in left}


def week_of(user, day):
    start = week_start(day, user.week_starts_on)
    return start, start + timedelta(days=6)


def _summary(history, moment, zone, planned):
    task = history.task
    completed = history.completed_at(moment)
    return {
        "id": str(task.id),
        "title": task.title,
        **_area(task),
        "due_date": history.due_at(moment),
        "status": history.status_at(moment),
        "status_now": task.status,
        "archived_now": task.archived_at is not None,
        "planned": planned,
        "completed_on": timezone.localtime(completed, zone).date()
        if completed
        else None,
    }


def week_tasks(user, start, end, now=None):
    """The week's planned workload and completions, as of the week's end."""
    zone = ZoneInfo(user.timezone)
    now = now or timezone.now()
    lower, upper = local_bounds(start, end, zone)
    as_of = min(upper, now)
    all_tasks = histories(user, created_before=min(upper, now + timedelta(seconds=1)))
    by_schedule = _scheduled_in(user, start, end, as_of)
    by_plan = _plan_items_in(user, start, end, as_of)

    planned, completed, unplanned = [], [], []
    for task_id, history in all_tasks.items():
        if not history.exists(as_of) or history.archived_at(as_of):
            continue
        status = history.status_at(as_of)
        done_at = history.completed_at(as_of)
        done_in_week = (
            status == DONE and done_at is not None and lower <= done_at < upper
        )
        due = history.due_at(as_of)
        is_planned = (
            status != CANCELLED
            and not (status == DONE and done_at is not None and done_at < lower)
            and (
                (due is not None and start <= due <= end)
                or task_id in by_schedule
                or task_id in by_plan
            )
        )
        if is_planned:
            planned.append(_summary(history, as_of, zone, True))
        if done_in_week:
            completed.append(_summary(history, as_of, zone, is_planned))
            if not is_planned:
                unplanned.append(task_id)
    return {
        "as_of": as_of,
        "planned": planned,
        "completed": completed,
        "unplanned_completed": len(unplanned),
    }


def _percent(part, whole):
    return round(part * 100 / whole) if whole else None


def weekly_numbers(tasks):
    planned = len(tasks["planned"])
    done = sum(
        1
        for task in tasks["planned"]
        if task["status"] == DONE and task["completed_on"]
    )
    return {
        "planned": planned,
        "completed": done,
        "outstanding": planned - done,
        "completion_percent": _percent(done, planned),
        "unplanned_completed": tasks["unplanned_completed"],
        "completed_total": len(tasks["completed"]),
    }


def overall(user, today):
    active = Task.objects.filter(user=user, archived_at__isnull=True)
    done = active.filter(status=DONE).count()
    open_tasks = active.filter(status__in=OPEN)
    remaining = open_tasks.count()
    return {
        "completed": done,
        "remaining": remaining,
        "overdue": open_tasks.filter(due_date__lt=today).count(),
        "due_today": open_tasks.filter(due_date=today).count(),
        "completion_percent": _percent(done, done + remaining),
    }


def _workstreams(tasks):
    rows = {}
    for task in tasks["completed"]:
        key = task["area"] or "none"
        row = rows.setdefault(
            key,
            {
                "area": task["area"],
                "label": task["label"],
                "color": task["color"],
                "count": 0,
            },
        )
        row["count"] += 1
    return sorted(rows.values(), key=lambda row: (-row["count"], row["label"]))


def _accomplishments(user, start, end, as_of, zone, tasks):
    lower, upper = local_bounds(start, end, zone)
    upper = min(upper, as_of)
    nodes = list(
        RoadmapNode.objects.filter(
            roadmap__user=user,
            state=RoadmapNode.State.COMPLETED,
            completed_at__gte=lower,
            completed_at__lt=upper,
        )
        .select_related("roadmap")
        .order_by("completed_at")
    )
    sessions = FocusSession.objects.filter(
        user=user,
        status=FocusSession.Status.COMPLETED,
        started_at__gte=lower,
        started_at__lt=upper,
    )
    focus_seconds = sum(session.duration_seconds or 0 for session in sessions)
    roadmaps = {node.roadmap_id: node.roadmap.title for node in nodes}
    for session in sessions.filter(roadmap_item__isnull=False).select_related(
        "roadmap_item__roadmap"
    ):
        roadmaps[session.roadmap_item.roadmap_id] = session.roadmap_item.roadmap.title
    linked_done = Task.objects.filter(
        id__in=[task["id"] for task in tasks["completed"]], roadmap_item__isnull=False
    ).count()
    return {
        "completed_tasks": tasks["completed"],
        "milestones": [
            {
                "id": str(node.id),
                "title": node.title,
                "kind": node.node_type,
                "roadmap": node.roadmap.title,
                "completed_on": timezone.localtime(node.completed_at, zone).date(),
            }
            for node in nodes
        ],
        "focus_minutes": round(focus_seconds / 60),
        "focus_sessions": sessions.count(),
        "roadmaps_advanced": sorted(roadmaps.values()),
        "learning": {
            "roadmap_items_completed": sum(
                1 for node in nodes if node.node_type == "item"
            ),
            "roadmap_tasks_completed": linked_done,
        },
        "evidence_recorded": Evidence.objects.filter(
            user=user, created_at__gte=lower, created_at__lt=upper
        ).count(),
        "accomplishments": [
            {"id": str(item.id), "title": item.title, "local_date": item.local_date}
            for item in Accomplishment.objects.filter(
                user=user, local_date__range=(start, end), archived_at__isnull=True
            ).order_by("local_date")
        ],
    }


def progress(user, day=None, now=None):
    """The ``GET /progress`` payload for the week containing ``day``."""
    zone = ZoneInfo(user.timezone)
    now = now or timezone.now()
    today = timezone.localtime(now, zone).date()
    start, end = week_of(user, day or today)
    tasks = week_tasks(user, start, end, now)
    previous = week_tasks(
        user, start - timedelta(days=7), start - timedelta(days=1), now
    )
    current = weekly_numbers(tasks)
    before = weekly_numbers(previous)
    return {
        "today": today,
        "week": {
            "start": start,
            "end": end,
            "is_current": start <= today <= end,
            "is_future": start > today,
            "as_of": tasks["as_of"],
        },
        "overall": overall(user, today),
        "weekly": {**current, "previous": before},
        "workstreams": {
            "completed_tasks": _workstreams(tasks),
            "time": [
                {key: row[key] for key in ("area", "label", "color", "actual_minutes")}
                for row in category_time(user, start, end)
                if row["actual_minutes"] > 0
            ],
        },
        "tasks": {"planned": tasks["planned"], "completed": tasks["completed"]},
        "accomplishments": _accomplishments(
            user, start, end, tasks["as_of"], zone, tasks
        ),
    }
