"""My Journey: the permanent record of growth, one chapter per calendar year.

Read-only. Every entry comes from an append-only or user-authored record:

* ActivityEvent snapshots (goals, milestones, projects, vision, roadmap items,
  challenges), taken at the moment something happened;
* task completion events (PlanningEvent), with the workstream fixed at
  completion time (TD-1);
* accomplishments, evidence, journal entries and weekly reviews;
* completed focus sessions, for time.

Nothing is estimated or invented. Years are calendar years in the user's
timezone, so the 96-day challenge and every later challenge sit inside one
lifetime history that never resets.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q

from challenges.models import Challenge
from execution.models import FocusSession
from planning.models import PlanningEvent
from records.models import Accomplishment, Evidence
from reflections.models import WeeklyReview

from .models import ActivityEvent, JournalEntry

MILESTONE_KINDS = {
    ("goal", "completed"): "goal_completed",
    ("milestone", "completed"): "milestone_completed",
    ("project", "completed"): "project_completed",
    ("vision", "realised"): "vision_realised",
    ("roadmap_item", "completed"): "learning_completed",
    ("roadmap", "completed"): "roadmap_completed",
    ("challenge", "completed"): "challenge_completed",
    ("goal", "carried_forward"): "goal_carried_forward",
}
ENTRY_LIMIT = 400


def _bounds(year, zone):
    start = datetime.combine(date(year, 1, 1), time.min, tzinfo=zone)
    end = datetime.combine(date(year + 1, 1, 1), time.min, tzinfo=zone)
    return start, end


def _local(moment, zone):
    return moment.astimezone(zone)


def available_years(user):
    zone = ZoneInfo(user.timezone)
    years = set()
    for model, field in (
        (ActivityEvent, "occurred_at"),
        (PlanningEvent, "created_at"),
        (FocusSession, "started_at"),
        (Accomplishment, "created_at"),
    ):
        first = model.objects.filter(user=user).order_by(field).values_list(field, flat=True).first()
        if first:
            years.add(_local(first, zone).year)
    years.add(datetime.now(zone).year)
    return list(range(max(years), min(years) - 1, -1))


def journey(user, year):
    zone = ZoneInfo(user.timezone)
    start, end = _bounds(year, zone)
    entries = []

    events = ActivityEvent.objects.filter(
        user=user, occurred_at__gte=start, occurred_at__lt=end
    ).order_by("-occurred_at")
    counts = Counter()
    for event in events:
        entry_type = MILESTONE_KINDS.get((event.subject_type, event.kind))
        if not entry_type:
            continue
        counts[entry_type] += 1
        moment = _local(event.occurred_at, zone)
        entries.append(
            {
                "id": f"activity:{event.pk}",
                "type": entry_type,
                "title": event.title,
                "date": moment.date().isoformat(),
                "occurred_at": event.occurred_at.isoformat(),
                "subject_type": event.subject_type,
                "subject_id": str(event.subject_id),
                "detail": event.data,
            }
        )

    for item in Accomplishment.objects.filter(
        user=user,
        archived_at__isnull=True,
        local_date__gte=start.date(),
        local_date__lt=end.date(),
    ).select_related("area"):
        counts["achievement"] += 1
        entries.append(
            {
                "id": f"accomplishment:{item.pk}",
                "type": "achievement",
                "title": item.title,
                "date": item.local_date.isoformat(),
                "occurred_at": item.created_at.isoformat(),
                "detail": {
                    "description": item.description,
                    "area": {"label": item.area.name, "color": item.area.color}
                    if item.area_id
                    else None,
                },
            }
        )

    for item in JournalEntry.objects.filter(
        user=user,
        archived_at__isnull=True,
        local_date__gte=start.date(),
        local_date__lt=end.date(),
    ):
        counts["journal"] += 1
        entries.append(
            {
                "id": f"journal:{item.pk}",
                "type": f"journal_{item.kind}",
                "title": item.title,
                "date": item.local_date.isoformat(),
                "occurred_at": item.created_at.isoformat(),
                "subject_type": "journal",
                "subject_id": str(item.pk),
                "detail": {"body": item.body, "edited": bool(item.revisions)},
            }
        )

    for review in WeeklyReview.objects.filter(
        user=user,
        archived_at__isnull=True,
        week_start_date__gte=start.date(),
        week_start_date__lt=end.date(),
    ):
        counts["weekly_review"] += 1
        entries.append(
            {
                "id": f"review:{review.pk}",
                "type": "weekly_review",
                "title": f"Weekly review · week of {review.week_start_date:%d %b}",
                "date": review.week_start_date.isoformat(),
                "occurred_at": review.created_at.isoformat(),
                "detail": {
                    field: getattr(review, field, "")
                    for field in ("wins", "lessons", "next_week")
                    if getattr(review, field, "")
                },
            }
        )

    evidence = Evidence.objects.filter(
        user=user, archived_at__isnull=True, created_at__gte=start, created_at__lt=end
    ).select_related("task", "roadmap_node", "session", "accomplishment")
    for item in evidence:
        counts["evidence"] += 1
        parent = (
            item.task or item.roadmap_node or item.session or item.accomplishment
        )
        entries.append(
            {
                "id": f"evidence:{item.pk}",
                "type": "evidence",
                "title": getattr(parent, "title", "") or "Evidence",
                "date": _local(item.created_at, zone).date().isoformat(),
                "occurred_at": item.created_at.isoformat(),
                "detail": {"kind": item.kind, "url": item.url, "text": item.text},
            }
        )

    # Work and time, per month: tasks completed (workstream as recorded at
    # completion) and focus minutes actually tracked.
    months = defaultdict(lambda: {"tasks_completed": 0, "focus_minutes": 0, "areas": Counter()})
    completions = PlanningEvent.objects.filter(
        user=user, created_at__gte=start, created_at__lt=end
    ).filter(Q(event_type="completed") | Q(event_type="status_changed", snapshot__to="done"))
    for event in completions:
        month = _local(event.created_at, zone).strftime("%Y-%m")
        months[month]["tasks_completed"] += 1
        area = (event.snapshot or {}).get("area")
        if area:
            months[month]["areas"][area.get("label") or "No workstream"] += 1
    sessions = FocusSession.objects.filter(
        user=user, status="completed", started_at__gte=start, started_at__lt=end
    )
    for session in sessions:
        month = _local(session.started_at, zone).strftime("%Y-%m")
        months[month]["focus_minutes"] += (session.duration_seconds or 0) // 60

    chapters = [
        {
            "id": str(challenge.pk),
            "name": challenge.name,
            "start_date": challenge.start_date.isoformat(),
            "end_date": challenge.end_date.isoformat(),
            "status": challenge.status,
            "archived": challenge.archived_at is not None,
            "total_days": (challenge.end_date - challenge.start_date).days + 1,
        }
        for challenge in Challenge.objects.filter(
            user=user,
            start_date__lt=end.date(),
            end_date__gte=start.date(),
        ).order_by("start_date")
    ]

    entries.sort(key=lambda entry: (entry["date"], entry["occurred_at"]), reverse=True)
    total_tasks = sum(month["tasks_completed"] for month in months.values())
    total_focus = sum(month["focus_minutes"] for month in months.values())
    return {
        "year": year,
        "years": available_years(user),
        "summary": {
            "goals_completed": counts["goal_completed"],
            "milestones_completed": counts["milestone_completed"],
            "projects_completed": counts["project_completed"],
            "learning_completed": counts["learning_completed"],
            "roadmaps_completed": counts["roadmap_completed"],
            "visions_realised": counts["vision_realised"],
            "achievements": counts["achievement"],
            "evidence": counts["evidence"],
            "journal_entries": counts["journal"],
            "weekly_reviews": counts["weekly_review"],
            "tasks_completed": total_tasks,
            "focus_minutes": total_focus,
        },
        "months": [
            {
                "month": key,
                "tasks_completed": value["tasks_completed"],
                "focus_minutes": value["focus_minutes"],
                "top_areas": value["areas"].most_common(3),
            }
            for key, value in sorted(months.items(), reverse=True)
        ],
        "chapters": chapters,
        "entries": entries[:ENTRY_LIMIT],
        "truncated": len(entries) > ENTRY_LIMIT,
    }


def year_end_candidates(user, year):
    """Unfinished goals of ``year`` that the user may deliberately continue."""
    from .models import Goal

    zone = ZoneInfo(user.timezone)
    _, end = _bounds(year, zone)
    last_day = end.date() - timedelta(days=1)
    return Goal.objects.filter(
        user=user,
        archived_at__isnull=True,
        status__in=("active", "paused"),
    ).filter(Q(target_date__isnull=True) | Q(target_date__lte=last_day))
