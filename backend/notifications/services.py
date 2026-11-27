"""Scheduling and sending reminders.

``next_fire`` turns a reminder's local date, time and repeat rule into the
next UTC instant, in the reminder's own timezone (so 07:30 stays 07:30 across
daylight-saving changes where they exist).

``dispatch`` is run by a scheduler every few minutes. For each thing that is
due it first claims a ReminderDelivery row with a key unique per user, then
sends. Two overlapping runs therefore never send the same reminder twice,
and a run that crashes after claiming does not resend later. Anything more
than ``LATE_LIMIT`` overdue is recorded as skipped rather than sent late.

Besides explicit reminders, dispatch also sends the reminders users switched
on in their preferences: an activity about to start (schedule entries), the
daily planning prompt and the weekly review prompt.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import PushSubscription, Reminder, ReminderDelivery

logger = logging.getLogger("charityos.notifications")
LATE_LIMIT = timedelta(minutes=30)
SNOOZE_SALT = "charityos.reminder.snooze"
SNOOZE_MAX_AGE = 60 * 60 * 24


def push_configured():
    return bool(settings.CHARITYOS_VAPID_PUBLIC_KEY and settings.CHARITYOS_VAPID_PRIVATE_KEY)


def next_fire(reminder, after):
    """The first fire time strictly after ``after`` (UTC), or None."""
    zone = ZoneInfo(reminder.timezone_name)
    local_after = after.astimezone(zone)
    if reminder.repeat == Reminder.Repeat.ONCE:
        moment = datetime.combine(reminder.local_date, reminder.local_time, tzinfo=zone)
        return moment.astimezone(UTC) if moment > after else None
    days = (
        set(range(1, 8))
        if reminder.repeat == Reminder.Repeat.DAILY
        else {int(day) for day in reminder.weekdays or []}
    )
    if not days:
        return None
    for offset in range(0, 8):
        day = local_after.date() + timedelta(days=offset)
        if day.isoweekday() not in days:
            continue
        moment = datetime.combine(day, reminder.local_time, tzinfo=zone)
        if moment > after:
            return moment.astimezone(UTC)
    return None


def schedule(reminder, now=None):
    """Recompute ``next_fire_at`` after any change to a reminder."""
    now = now or timezone.now()
    reminder.next_fire_at = (
        next_fire(reminder, now) if reminder.enabled and reminder.archived_at is None else None
    )
    return reminder


def snooze_token(delivery):
    return signing.dumps({"d": str(delivery.pk)}, salt=SNOOZE_SALT)


@transaction.atomic
def snooze(token, minutes=10):
    """Send the reminder again in ``minutes``. The token is the only credential:
    it comes from the notification itself, which the service worker cannot
    attach a CSRF token to."""
    try:
        payload = signing.loads(token, salt=SNOOZE_SALT, max_age=SNOOZE_MAX_AGE)
        delivery = ReminderDelivery.objects.select_related("user").get(pk=payload["d"])
    except (signing.BadSignature, ReminderDelivery.DoesNotExist, KeyError, ValueError):
        return None
    zone = ZoneInfo(delivery.user.timezone)
    moment = (timezone.now() + timedelta(minutes=minutes)).astimezone(zone)
    reminder, created = Reminder.objects.get_or_create(
        user=delivery.user,
        title=delivery.title[:120],
        repeat=Reminder.Repeat.ONCE,
        local_date=moment.date(),
        local_time=moment.time().replace(second=0, microsecond=0),
        defaults={
            "kind": Reminder.Kind.CUSTOM,
            "body": "Snoozed reminder",
            "link": delivery.link,
            "timezone_name": delivery.user.timezone,
        },
    )
    if created:
        schedule(reminder).save(update_fields=("next_fire_at",))
    return reminder


def _vapid_claims():
    return {"sub": settings.CHARITYOS_VAPID_SUBJECT}


def send_push(subscription, payload):
    """Send one Web Push message. Returns True, False (failed) or None (gone)."""
    from pywebpush import WebPushException, webpush

    if not push_configured():
        logger.warning("push skipped: VAPID keys are not configured")
        return False
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.CHARITYOS_VAPID_PRIVATE_KEY,
            vapid_claims=_vapid_claims(),
            ttl=60 * 60,
            timeout=10,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return None
        logger.warning("push failed", extra={"status": status})
        return False
    except Exception as exc:  # network errors must not stop the other reminders
        logger.warning("push error %s", type(exc).__name__)
        return False


def deliver(user, *, key, title, body, link, due_at, reminder=None, now=None, sender=None):
    """Claim ``key`` for ``user`` and send it to every active device. Idempotent."""
    now = now or timezone.now()
    sender = sender or send_push
    try:
        with transaction.atomic():
            delivery = ReminderDelivery.objects.create(
                user=user,
                key=key[:200],
                reminder=reminder,
                title=title[:120],
                link=link[:200],
                due_at=due_at,
                status=ReminderDelivery.Status.SKIPPED,
            )
    except IntegrityError:
        return None  # someone else already sent (or skipped) it
    if now - due_at > LATE_LIMIT:
        return delivery
    devices = list(PushSubscription.objects.filter(user=user, disabled_at__isnull=True))
    if not devices:
        delivery.status = ReminderDelivery.Status.NO_DEVICE
        delivery.save(update_fields=("status",))
        return delivery
    payload = {
        "title": title,
        "body": body,
        "url": f"/{link}" if link.startswith("#") else (link or "/#/today"),
        "tag": key[:60],
        "snooze": snooze_token(delivery),
    }
    sent = 0
    for device in devices:
        result = sender(device, payload)
        if result is True:
            sent += 1
            device.last_success_at = now
            device.failure_count = 0
            device.save(update_fields=("last_success_at", "failure_count"))
        elif result is None:
            device.disabled_at = now
            device.save(update_fields=("disabled_at",))
        else:
            device.failure_count += 1
            device.save(update_fields=("failure_count",))
    delivery.devices = sent
    delivery.status = ReminderDelivery.Status.SENT if sent else ReminderDelivery.Status.FAILED
    delivery.save(update_fields=("devices", "status"))
    return delivery


def _due_reminders(now):
    return Reminder.objects.filter(
        enabled=True, archived_at__isnull=True, next_fire_at__lte=now
    ).select_related("user")


def _preference_reminders(now, sender):
    """Start, planning and review reminders switched on in preferences."""
    from scheduling.models import ScheduleEntry
    from users.models import UserPreferences

    count = 0
    prefs = UserPreferences.objects.filter(reminders_enabled=True).select_related("user")
    for pref in prefs:
        user = pref.user
        if not PushSubscription.objects.filter(user=user, disabled_at__isnull=True).exists():
            continue
        zone = ZoneInfo(user.timezone)
        local_now = now.astimezone(zone)
        if pref.start_reminders_enabled:
            lead = timedelta(minutes=pref.reminder_lead_minutes)
            entries = ScheduleEntry.objects.filter(
                user=user,
                status=ScheduleEntry.Status.SCHEDULED,
                start_at__gt=now - LATE_LIMIT + lead,
                start_at__lte=now + lead,
            )
            for entry in entries:
                minutes = pref.reminder_lead_minutes
                starts = entry.start_at.astimezone(zone).strftime("%H:%M")
                if deliver(
                    user,
                    key=f"entry:{entry.pk}:{entry.start_at.isoformat()}",
                    title=entry.title,
                    body=f"Starts at {starts}" if minutes else "Starting now",
                    link=f"#/schedule?date={entry.local_date.isoformat()}",
                    due_at=entry.start_at - lead,
                    now=now,
                    sender=sender,
                ):
                    count += 1
        for enabled, at, key, title, body, link, weekday in (
            (
                pref.daily_planning_reminder_enabled,
                pref.daily_planning_time,
                "plan",
                "Plan your day",
                "Choose up to three outcomes that matter today.",
                "#/today",
                None,
            ),
            (
                pref.weekly_review_reminder_enabled,
                pref.weekly_review_time,
                "review",
                "Weekly review",
                "Look back at the week and choose what comes next.",
                "#/insights/review",
                pref.weekly_review_weekday,
            ),
        ):
            if not enabled or (weekday and local_now.isoweekday() != weekday):
                continue
            due = datetime.combine(local_now.date(), at, tzinfo=zone).astimezone(UTC)
            if due <= now < due + LATE_LIMIT and deliver(
                user,
                key=f"{key}:{local_now.date().isoformat()}",
                title=title,
                body=body,
                link=link,
                due_at=due,
                now=now,
                sender=sender,
            ):
                count += 1
    return count


def dispatch(now=None, sender=None):
    """Send everything that is due. Safe to run concurrently and repeatedly."""
    now = now or timezone.now()
    sent = 0
    for reminder in _due_reminders(now):
        with transaction.atomic():
            locked = (
                Reminder.objects.select_for_update(skip_locked=True)
                .filter(pk=reminder.pk, next_fire_at__lte=now, enabled=True)
                .first()
            )
            if locked is None:
                continue
            due = locked.next_fire_at
            delivery = deliver(
                reminder.user,
                key=f"reminder:{locked.pk}:{due.isoformat()}",
                title=locked.title,
                body=locked.body,
                link=locked.link,
                due_at=due,
                reminder=locked,
                now=now,
                sender=sender,
            )
            locked.last_fired_at = now
            locked.next_fire_at = next_fire(locked, max(due, now))
            if locked.repeat == Reminder.Repeat.ONCE:
                locked.enabled = False
            locked.save(update_fields=("last_fired_at", "next_fire_at", "enabled", "updated_at"))
            if delivery is not None:
                sent += 1
    sent += _preference_reminders(now, sender)
    return sent



def next_due(now=None, horizon=timedelta(hours=6)):
    """When dispatch next has something to send, capped at ``now + horizon``.

    The scheduler uses this to call dispatch only when needed, so the
    database (which may sleep when idle on a free plan) is not woken every
    few minutes for nothing.
    """
    from scheduling.models import ScheduleEntry
    from users.models import UserPreferences

    now = now or timezone.now()
    cap = now + horizon
    candidates = [cap]
    first = (
        Reminder.objects.filter(enabled=True, archived_at__isnull=True, next_fire_at__isnull=False)
        .order_by("next_fire_at")
        .values_list("next_fire_at", flat=True)
        .first()
    )
    if first:
        candidates.append(first)
    prefs = UserPreferences.objects.filter(reminders_enabled=True).select_related("user")
    for pref in prefs:
        user = pref.user
        if not PushSubscription.objects.filter(user=user, disabled_at__isnull=True).exists():
            continue
        zone = ZoneInfo(user.timezone)
        if pref.start_reminders_enabled:
            lead = timedelta(minutes=pref.reminder_lead_minutes)
            start = (
                ScheduleEntry.objects.filter(
                    user=user, status=ScheduleEntry.Status.SCHEDULED, start_at__gt=now + lead
                )
                .order_by("start_at")
                .values_list("start_at", flat=True)
                .first()
            )
            if start:
                candidates.append(start - lead)
        for enabled, at, weekday in (
            (pref.daily_planning_reminder_enabled, pref.daily_planning_time, None),
            (pref.weekly_review_reminder_enabled, pref.weekly_review_time, pref.weekly_review_weekday),
        ):
            if not enabled:
                continue
            local = now.astimezone(zone)
            for offset in range(8):
                day = local.date() + timedelta(days=offset)
                if weekday and day.isoweekday() != weekday:
                    continue
                moment = datetime.combine(day, at, tzinfo=zone).astimezone(UTC)
                if moment > now:
                    candidates.append(moment)
                    break
    return max(min(candidates), now)
