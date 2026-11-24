"""Historical reporting built only from stored records.

Rules:
- Daily grouping uses the user's timezone (entries use their stored local date).
- Unknown actual time is reported as unknown, never copied from the plan.
- A minute is counted once: linked focus time via the entry, plus only the
  focus sessions that are not linked to an entry.
- Health history stays in its own section and never feeds productivity.
- There is no composite score.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from challenges.models import Challenge
from execution.models import FocusSession
from health.models import ExerciseLog, SleepLog
from reflections.models import DailyReflection, WeeklyReview

from .models import ScheduleEntry

PERIODS = ("7d", "30d", "90d", "challenge", "year", "all")
MILESTONES = (3, 7, 12)
Status = ScheduleEntry.Status


def user_today(user):
    return timezone.localtime(timezone.now(), ZoneInfo(user.timezone)).date()


def week_start(day, week_starts_on=1):
    return day - timedelta(days=(day.isoweekday() - week_starts_on) % 7)


def primary_challenge(user):
    return Challenge.objects.filter(
        user=user, is_primary=True, archived_at__isnull=True
    ).first()


def _earliest_record(user, today):
    candidates = []
    entry = ScheduleEntry.objects.filter(user=user).order_by("local_date").first()
    if entry:
        candidates.append(entry.local_date)
    session = FocusSession.objects.filter(user=user).order_by("started_at").first()
    if session:
        candidates.append(
            timezone.localtime(session.started_at, ZoneInfo(user.timezone)).date()
        )
    for model, field in ((ExerciseLog, "started_at"), (SleepLog, "started_at")):
        row = model.objects.filter(user=user).order_by(field).first()
        if row:
            candidates.append(
                timezone.localtime(getattr(row, field), ZoneInfo(user.timezone)).date()
            )
    return min(candidates) if candidates else today


def period_bounds(user, period, today):
    if period == "7d":
        return today - timedelta(days=6), today
    if period == "90d":
        return today - timedelta(days=89), today
    if period == "year":
        return today.replace(month=1, day=1), today
    if period == "all":
        return min(_earliest_record(user, today), today), today
    if period == "challenge":
        challenge = primary_challenge(user)
        if challenge:
            end = min(challenge.end_date, today)
            start = min(challenge.start_date, end)
            return start, end
    return today - timedelta(days=29), today


def local_bounds(start, end, zone):
    """UTC-aware instants covering local dates ``start``..``end`` inclusive."""
    return (
        datetime.combine(start, time.min, tzinfo=zone),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone),
    )


def _days(start, end):
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _local_day(instant, zone):
    return timezone.localtime(instant, zone).date()


def _minutes(seconds):
    return round((seconds or 0) / 60)


def _overlaps(start, end, intervals):
    return any(
        start < other_end and end > other_start for other_start, other_end in intervals
    )


def _entry_interval(entry):
    if entry.actual_started_at and entry.actual_ended_at:
        return entry.actual_started_at, entry.actual_ended_at
    return entry.start_at, entry.end_at


def build_insights(user, period="30d"):
    period = period if period in PERIODS else "30d"
    zone = ZoneInfo(user.timezone)
    today = user_today(user)
    start, end = period_bounds(user, period, today)
    days = _days(start, end)
    week_of = {day: week_start(day, user.week_starts_on) for day in days}

    entries = list(
        ScheduleEntry.objects.filter(user=user, local_date__range=(start, end))
        .select_related("area", "focus_session")
        .prefetch_related("focus_session__pauses")
    )

    # --- Schedule completion -------------------------------------------------
    blank = {
        "planned": 0,
        "completed": 0,
        "partially_completed": 0,
        "skipped": 0,
        "cancelled": 0,
        "rescheduled": 0,
        "open": 0,
    }
    by_day = {day: dict(blank) for day in days}
    for entry in entries:
        bucket = by_day[entry.local_date]
        if entry.status == Status.RESCHEDULED:
            bucket["rescheduled"] += 1
            continue
        if entry.status == Status.CANCELLED:
            bucket["cancelled"] += 1
            continue
        bucket["planned"] += 1
        if entry.status in ScheduleEntry.OPEN_STATUSES:
            bucket["open"] += 1
        else:
            bucket[entry.status] += 1

    # --- Time by category (each minute once) ---------------------------------
    categories = {}

    def category(key, label, color):
        if key not in categories:
            categories[key] = {
                "area": key if key and not key.startswith("label:") else None,
                "label": label or "Uncategorised",
                "color": color or "#64748B",
                "planned_minutes": 0,
                "actual_minutes": 0,
                "activities": 0,
            }
        return categories[key]

    done_entries = []
    for entry in entries:
        if entry.status in (Status.RESCHEDULED, Status.CANCELLED):
            continue
        key = (
            str(entry.area_id)
            if entry.area_id
            else f"label:{entry.area_label_snapshot}"
        )
        row = category(
            key,
            entry.area.name if entry.area else entry.area_label_snapshot,
            entry.area.color if entry.area else None,
        )
        row["planned_minutes"] += _minutes(entry.planned_seconds)
        if entry.status in ScheduleEntry.DONE_STATUSES:
            row["activities"] += 1
            done_entries.append(entry)
            actual = entry.actual_seconds()
            if actual is not None:
                row["actual_minutes"] += _minutes(actual)

    lower, upper = local_bounds(start, end, zone)
    sessions = list(
        FocusSession.objects.filter(
            user=user,
            status=FocusSession.Status.COMPLETED,
            started_at__gte=lower,
            started_at__lt=upper,
        ).select_related("area", "schedule_entry")
    )
    focus_by_day = defaultdict(int)
    for session in sessions:
        day = _local_day(session.started_at, zone)
        focus_by_day[day] += session.duration_seconds or 0
        linked = getattr(session, "schedule_entry", None)
        if linked is None:
            row = category(
                str(session.area_id),
                session.area_label_snapshot or session.area.name,
                session.area.color,
            )
            row["actual_minutes"] += _minutes(session.duration_seconds)

    # --- Weekly rollups -------------------------------------------------------
    active_days = set()
    for entry in done_entries:
        active_days.add(entry.local_date)
    for day, seconds in focus_by_day.items():
        if seconds:
            active_days.add(day)

    weeks = {}
    for day in days:
        key = week_of[day]
        week = weeks.setdefault(
            key,
            {
                "week_start": key,
                "planned": 0,
                "completed": 0,
                "focus_minutes": 0,
                "active_days": 0,
                "days_in_range": 0,
            },
        )
        week["planned"] += by_day[day]["planned"]
        week["completed"] += (
            by_day[day]["completed"] + by_day[day]["partially_completed"]
        )
        week["focus_seconds"] = week.get("focus_seconds", 0) + focus_by_day.get(day, 0)
        week["days_in_range"] += 1
        week["active_days"] += 1 if day in active_days else 0
    for week in weeks.values():
        week["focus_minutes"] = _minutes(week.pop("focus_seconds", 0))

    # --- Health (separate) ----------------------------------------------------
    health = _health(user, zone, start, end, days)

    totals = {
        "planned": sum(row["planned"] for row in by_day.values()),
        "completed": sum(row["completed"] for row in by_day.values()),
        "partially_completed": sum(
            row["partially_completed"] for row in by_day.values()
        ),
        "skipped": sum(row["skipped"] for row in by_day.values()),
        "rescheduled": sum(row["rescheduled"] for row in by_day.values()),
        "cancelled": sum(row["cancelled"] for row in by_day.values()),
        "focus_minutes": _minutes(sum(focus_by_day.values())),
        "tracked_minutes": sum(row["actual_minutes"] for row in categories.values()),
        "active_days": len(active_days),
    }

    challenge = primary_challenge(user)
    return {
        "period": {"label": period, "start": start, "end": end, "days": len(days)},
        "totals": totals,
        "schedule_daily": [{"date": day, **by_day[day]} for day in days],
        "schedule_weekly": sorted(weeks.values(), key=lambda week: week["week_start"]),
        "category_time": sorted(
            categories.values(),
            key=lambda row: (
                -row["actual_minutes"],
                -row["planned_minutes"],
                row["label"],
            ),
        ),
        "focus_daily": [
            {"date": day, "minutes": _minutes(focus_by_day.get(day, 0))} for day in days
        ],
        "health": health,
        "challenge": challenge_progress(user, challenge, today, zone),
    }


def _health(user, zone, start, end, days):
    # Widen by a day so entries near the edges can be de-duplicated.
    window_start = start - timedelta(days=1)
    lower, upper = local_bounds(window_start, end + timedelta(days=1), zone)
    exercise_logs = list(
        ExerciseLog.objects.filter(user=user, started_at__lt=upper, ended_at__gt=lower)
    )
    sleep_logs = list(
        SleepLog.objects.filter(user=user, started_at__lt=upper, woke_at__gt=lower)
    )
    health_entries = list(
        ScheduleEntry.objects.filter(
            user=user,
            status__in=ScheduleEntry.DONE_STATUSES,
            area__health_kind__in=("exercise", "sleep"),
            local_date__gte=window_start,
            local_date__lte=end,
        )
        .select_related("area", "focus_session")
        .prefetch_related("focus_session__pauses")
    )
    exercise = defaultdict(int)
    for log in exercise_logs:
        day = _local_day(log.started_at, zone)
        if start <= day <= end:
            exercise[day] += int((log.ended_at - log.started_at).total_seconds())
    sleep = defaultdict(float)
    for log in sleep_logs:
        if start <= log.wake_local_date <= end:
            sleep[log.wake_local_date] += (log.woke_at - log.started_at).total_seconds()

    exercise_intervals = [(log.started_at, log.ended_at) for log in exercise_logs]
    sleep_intervals = [(log.started_at, log.woke_at) for log in sleep_logs]
    from_schedule = {"exercise": 0, "sleep": 0}
    for entry in health_entries:
        actual = entry.actual_seconds()
        if actual is None:
            continue
        interval = _entry_interval(entry)
        if entry.area.health_kind == "exercise":
            if _overlaps(*interval, exercise_intervals):
                continue
            day = entry.local_date
            if start <= day <= end:
                exercise[day] += actual
                from_schedule["exercise"] += 1
        else:
            if _overlaps(*interval, sleep_intervals):
                continue
            day = _local_day(interval[1], zone)
            if start <= day <= end:
                sleep[day] += actual
                from_schedule["sleep"] += 1
    return {
        "exercise_daily": [
            {"date": day, "minutes": _minutes(exercise.get(day, 0))} for day in days
        ],
        "sleep_daily": [
            {"date": day, "hours": round(sleep.get(day, 0) / 3600, 2)} for day in days
        ],
        "activities_from_schedule": from_schedule,
    }


def challenge_progress(user, challenge, today, zone):
    if challenge is None:
        return None
    total = (challenge.end_date - challenge.start_date).days + 1
    if today < challenge.start_date:
        day, phase = 0, "upcoming"
    elif today > challenge.end_date:
        day, phase = total, "completed"
    else:
        day, phase = (today - challenge.start_date).days + 1, "active"
    window_end = min(today, challenge.end_date)
    completed = ScheduleEntry.objects.filter(
        user=user,
        status__in=ScheduleEntry.DONE_STATUSES,
        local_date__range=(challenge.start_date, window_end),
    ).count()
    active = set(
        ScheduleEntry.objects.filter(
            user=user,
            status__in=ScheduleEntry.DONE_STATUSES,
            local_date__range=(challenge.start_date, window_end),
        ).values_list("local_date", flat=True)
    )
    focus_seconds = 0
    lower, upper = local_bounds(challenge.start_date, window_end, zone)
    for session in FocusSession.objects.filter(
        user=user,
        status=FocusSession.Status.COMPLETED,
        started_at__gte=lower,
        started_at__lt=upper,
    ):
        focus_seconds += session.duration_seconds or 0
        active.add(_local_day(session.started_at, zone))
    return {
        "id": str(challenge.id),
        "name": challenge.name,
        "start_date": challenge.start_date,
        "end_date": challenge.end_date,
        "phase": phase,
        "current_day": day,
        "total_days": total,
        "days_remaining": max(0, (challenge.end_date - today).days)
        if phase != "completed"
        else 0,
        "progress_percent": round(day / total * 100, 1) if total else 0,
        "completed_activities": completed,
        "focus_minutes": _minutes(focus_seconds),
        "active_days": len(active),
    }


# --------------------------------------------------------------------------
# Gamification: derived, gentle, never stored.

BADGES = (
    ("first_step", "First step", "Completed your first scheduled activity."),
    ("well_rounded", "Well-rounded week", "Completed activities in 3+ categories."),
    ("moved", "Moved your body", "Three exercise activities this week."),
    ("rested", "Well rested", "Five nights of 7+ hours of sleep this week."),
    ("planner", "Planner", "Planned activities on 5 days this week."),
    ("steady", "Steady rhythm", "Active on 4 days this week. Rest days count too."),
    ("focused", "Deep focus", "A focus session of 50+ minutes this week."),
    ("reflective", "Reflective", "Closed a weekly review or 3 daily reflections."),
)


def _active_dates(user, start, end, zone):
    dates = set(
        ScheduleEntry.objects.filter(
            user=user,
            status__in=ScheduleEntry.DONE_STATUSES,
            local_date__range=(start, end),
        ).values_list("local_date", flat=True)
    )
    lower, upper = local_bounds(start, end, zone)
    for started_at in FocusSession.objects.filter(
        user=user,
        status=FocusSession.Status.COMPLETED,
        started_at__gte=lower,
        started_at__lt=upper,
    ).values_list("started_at", flat=True):
        dates.add(_local_day(started_at, zone))
    return dates


def week_summary(user, today=None, show_streaks=False):
    zone = ZoneInfo(user.timezone)
    today = today or user_today(user)
    start = week_start(today, user.week_starts_on)
    end = start + timedelta(days=6)
    week_entries = list(
        ScheduleEntry.objects.filter(user=user, local_date__range=(start, end))
        .exclude(status__in=(Status.RESCHEDULED, Status.CANCELLED))
        .select_related("area")
    )
    done = [
        entry for entry in week_entries if entry.status in ScheduleEntry.DONE_STATUSES
    ]
    completed = len(done)
    active = _active_dates(user, start, end, zone)
    lower, upper = local_bounds(start, end, zone)

    exercise_count = (
        sum(1 for entry in done if entry.area and entry.area.health_kind == "exercise")
        + ExerciseLog.objects.filter(
            user=user, started_at__gte=lower, started_at__lt=upper
        ).count()
    )
    rested_nights = sum(
        1
        for log in SleepLog.objects.filter(
            user=user, wake_local_date__range=(start, end)
        )
        if (log.woke_at - log.started_at).total_seconds() >= 7 * 3600
    )
    long_focus = FocusSession.objects.filter(
        user=user,
        status=FocusSession.Status.COMPLETED,
        duration_seconds__gte=50 * 60,
        started_at__gte=lower,
        started_at__lt=upper,
    ).exists()
    reflective = (
        WeeklyReview.objects.filter(user=user, week_start_date=start).exists()
        or DailyReflection.objects.filter(
            user=user, local_date__range=(start, end)
        ).count()
        >= 3
    )
    earned = {
        "first_step": ScheduleEntry.objects.filter(
            user=user, status__in=ScheduleEntry.DONE_STATUSES
        ).exists(),
        "well_rounded": len({entry.area_id for entry in done if entry.area_id}) >= 3,
        "moved": exercise_count >= 3,
        "rested": rested_nights >= 5,
        "planner": len({entry.local_date for entry in week_entries}) >= 5,
        "steady": len(active) >= 4,
        "focused": long_focus,
        "reflective": reflective,
    }
    next_milestone = next((target for target in MILESTONES if completed < target), None)
    summary = {
        "week_start": start,
        "week_end": end,
        "completed": completed,
        "planned": len(week_entries),
        "active_days": len(active),
        "milestones": [
            {"target": target, "reached": completed >= target} for target in MILESTONES
        ],
        "next_milestone": next_milestone,
        "badges": [
            {"key": key, "title": title, "description": text, "earned": earned[key]}
            for key, title, text in BADGES
        ],
        "streak_weeks": None,
    }
    if show_streaks:
        summary["streak_weeks"] = consistency_streak(user, today, zone)
    return summary


def consistency_streak(user, today, zone, min_days=3, max_weeks=52):
    """Consecutive weeks with ``min_days`` active days.

    The current week only adds to the streak once it qualifies; an
    unfinished week never breaks it, and a missed day never resets it.
    """
    current = week_start(today, user.week_starts_on)
    earliest = current - timedelta(weeks=max_weeks)
    active = _active_dates(user, earliest, today, zone)
    counts = defaultdict(int)
    for day in active:
        counts[week_start(day, user.week_starts_on)] += 1
    streak = 1 if counts[current] >= min_days else 0
    cursor = current - timedelta(weeks=1)
    while cursor >= earliest and counts[cursor] >= min_days:
        streak += 1
        cursor -= timedelta(weeks=1)
    return streak
