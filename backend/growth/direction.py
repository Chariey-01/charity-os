"""Insights about direction: are goals, roadmaps and projects moving, and
what keeps being postponed? Built only from records; nothing estimated."""

from collections import Counter
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from planning.models import PlanningEvent, Task
from roadmaps.models import Roadmap
from scheduling.models import ScheduleEntry

from .models import ActivityEvent, Goal, Project
from .services import goal_progress

POSTPONE_WINDOW = timedelta(days=90)


def direction(user, today):
    now = timezone.now()
    since = now - timedelta(days=30)
    goals = []
    for goal in (
        Goal.objects.filter(user=user, archived_at__isnull=True, status__in=("active", "paused"))
        .prefetch_related("milestones", "tasks", "checkins")
        .order_by("target_date", "created_at")
    ):
        progress = goal_progress(goal, today)
        moved = ActivityEvent.objects.filter(
            user=user, occurred_at__gte=since
        ).filter(
            Q(subject_type="goal", subject_id=goal.pk)
            | Q(subject_type="milestone", data__goal_id=str(goal.pk))
        ).count() + PlanningEvent.objects.filter(
            user=user, task__goal=goal, created_at__gte=since, snapshot__to="done"
        ).count()
        goals.append(
            {
                "id": str(goal.pk),
                "title": goal.title,
                "status": goal.status,
                "ratio": progress["ratio"],
                "basis": progress["basis"],
                "overdue": progress["overdue"],
                "at_risk": progress["at_risk"],
                "days_left": progress["days_left"],
                "activity_30d": moved,
            }
        )
    roadmaps = []
    for roadmap in Roadmap.objects.filter(user=user, archived_at__isnull=True).exclude(status="completed"):
        stats = roadmap.progress()
        recent = ActivityEvent.objects.filter(
            user=user, subject_type="roadmap_item", data__roadmap_id=str(roadmap.pk), occurred_at__gte=since
        ).count()
        roadmaps.append(
            {
                "id": str(roadmap.pk),
                "title": roadmap.title,
                "status": roadmap.status,
                "done": stats["completed_eligible_items"],
                "total": stats["eligible_items"],
                "ratio": stats["progress_ratio"] if stats["eligible_items"] else None,
                "completed_30d": recent,
            }
        )
    projects = []
    for project in Project.objects.filter(user=user, archived_at__isnull=True).exclude(
        status__in=("completed", "cancelled")
    ).prefetch_related("tasks"):
        tasks = [t for t in project.tasks.all() if t.archived_at is None]
        done_recent = sum(1 for t in tasks if t.completed_at and t.completed_at >= since)
        projects.append(
            {
                "id": str(project.pk),
                "name": project.name,
                "status": project.status,
                "open": sum(1 for t in tasks if t.status not in ("done", "cancelled")),
                "done": sum(1 for t in tasks if t.status == "done"),
                "done_30d": done_recent,
                "overdue": sum(
                    1
                    for t in tasks
                    if t.due_date and t.due_date < today and t.status not in ("done", "cancelled")
                ),
            }
        )
    # What keeps moving: due dates pushed later, carried over, or rescheduled.
    window = now - POSTPONE_WINDOW
    counts = Counter()
    for task_id, snap in PlanningEvent.objects.filter(
        user=user, created_at__gte=window, event_type="due_changed"
    ).values_list("task_id", "snapshot"):
        old, new = (snap or {}).get("from"), (snap or {}).get("to")
        if old and (new is None or new > old):
            counts[task_id] += 1
    for task_id in PlanningEvent.objects.filter(
        user=user, created_at__gte=window, event_type="carried_over"
    ).values_list("task_id", flat=True):
        counts[task_id] += 1
    for task_id in ScheduleEntry.objects.filter(
        user=user, created_at__gte=window, status="rescheduled", task__isnull=False
    ).values_list("task_id", flat=True):
        counts[task_id] += 1
    titles = dict(
        Task.objects.filter(user=user, pk__in=[k for k in counts if k]).values_list("pk", "title")
    )
    statuses = dict(
        Task.objects.filter(user=user, pk__in=[k for k in counts if k]).values_list("pk", "status")
    )
    postponed = [
        {"id": str(task_id), "title": titles[task_id], "times": times, "status": statuses[task_id]}
        for task_id, times in counts.most_common(10)
        if task_id in titles and times >= 2
    ]
    return {"goals": goals, "roadmaps": roadmaps, "projects": projects, "postponed": postponed}
