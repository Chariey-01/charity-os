"""A read-only iCalendar (RFC 5545) feed of what the user planned.

Google Calendar, Android calendars and others can subscribe to the feed's
secret address. No Google account permission is involved: the calendar app
fetches the address itself. Anyone holding the address can read the titles
in it, so it is revocable and rotatable, and only its hash is stored.

The feed contains planned time only (schedule entries), plus all-day markers
for open tasks' due dates, open milestones and active goals' target dates.
It never contains notes, reflections, evidence or tracked time.
"""

import hashlib
import secrets
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import CalendarFeed

WINDOW_BACK = timedelta(days=30)
WINDOW_AHEAD = timedelta(days=180)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_feed(user):
    """Create or rotate the user's feed. Returns the new token (shown once)."""
    token = secrets.token_urlsafe(32)
    CalendarFeed.objects.update_or_create(user=user, defaults={"token_hash": _hash(token)})
    return token


def revoke_feed(user):
    CalendarFeed.objects.filter(user=user).delete()


def user_for_token(token):
    if not token or len(token) > 100:
        return None
    feed = CalendarFeed.objects.filter(token_hash=_hash(token)).select_related("user").first()
    return feed.user if feed and feed.user.is_active else None


def _escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line):
    """Fold lines longer than 75 octets (RFC 5545 §3.1)."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode()
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode())
            current = b""
        current += encoded
    parts.append(current.decode())
    return "\r\n ".join(parts)


def _utc(moment):
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _day(value):
    return value.strftime("%Y%m%d")


def build_feed(user, now=None):
    from growth.models import Goal, Milestone
    from planning.models import Task
    from scheduling.models import ScheduleEntry

    now = now or timezone.now()
    stamp = _utc(now)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CharityOS//Planner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:CharityOS",
        f"X-WR-TIMEZONE:{user.timezone}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]

    def event(uid, summary, *props):
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@charityos",
                f"DTSTAMP:{stamp}",
                f"SUMMARY:{_escape(summary)}",
                *props,
                "END:VEVENT",
            ]
        )

    entries = ScheduleEntry.objects.filter(
        user=user,
        start_at__gte=now - WINDOW_BACK,
        start_at__lte=now + WINDOW_AHEAD,
    ).exclude(status__in=("cancelled", "rescheduled"))
    for entry in entries:
        event(
            f"entry-{entry.pk}",
            entry.title,
            f"DTSTART:{_utc(entry.start_at)}",
            f"DTEND:{_utc(entry.end_at)}",
            "STATUS:CONFIRMED",
            f"DESCRIPTION:{_escape('Planned in CharityOS (' + entry.status.replace('_', ' ') + ')')}",
        )

    today = now.astimezone(ZoneInfo(user.timezone)).date()
    for task in Task.objects.filter(
        user=user,
        archived_at__isnull=True,
        due_date__isnull=False,
        due_date__gte=today - WINDOW_BACK,
        status__in=Task.OPEN_STATUSES,
    ):
        event(
            f"task-{task.pk}",
            f"Due: {task.title}",
            f"DTSTART;VALUE=DATE:{_day(task.due_date)}",
            f"DTEND;VALUE=DATE:{_day(task.due_date + timedelta(days=1))}",
            "TRANSP:TRANSPARENT",
        )
    for milestone in Milestone.objects.filter(
        user=user, archived_at__isnull=True, status="open", target_date__isnull=False
    ):
        event(
            f"milestone-{milestone.pk}",
            f"Milestone: {milestone.title}",
            f"DTSTART;VALUE=DATE:{_day(milestone.target_date)}",
            f"DTEND;VALUE=DATE:{_day(milestone.target_date + timedelta(days=1))}",
            "TRANSP:TRANSPARENT",
        )
    for goal in Goal.objects.filter(
        user=user, archived_at__isnull=True, status="active", target_date__isnull=False
    ):
        event(
            f"goal-{goal.pk}",
            f"Goal target: {goal.title}",
            f"DTSTART;VALUE=DATE:{_day(goal.target_date)}",
            f"DTEND;VALUE=DATE:{_day(goal.target_date + timedelta(days=1))}",
            "TRANSP:TRANSPARENT",
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
