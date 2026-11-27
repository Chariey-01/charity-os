"""Reminders that reach the phone while CharityOS is closed.

A browser cannot run a timer while Android has suspended it, so reminders
are scheduled on the server: a scheduled job (the Cloudflare Worker's cron
trigger, or ``manage.py dispatch_reminders``) sends Web Push messages to the
devices the user subscribed. Delivery is best effort, like any notification:
it is not an alarm clock (docs/reminders-and-notifications.md).

* ``PushSubscription``: one browser or installed app that accepted
  notifications. The endpoint is the push service's address for it.
* ``Reminder``: what to say and when: once, every day, or on chosen weekdays,
  at a local time in the user's timezone.
* ``ReminderDelivery``: one row per thing sent. Its key is unique per user,
  so two overlapping dispatch runs can never send the same reminder twice.
* ``CalendarFeed``: a private, revocable address for an .ics subscription.
  Only a hash of the token is stored.
"""

# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    device_label = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    # Set when the push service says the subscription is gone (404/410).
    disabled_at = models.DateTimeField(null=True, blank=True)


class Reminder(models.Model):
    class Kind(models.TextChoices):
        TASK = "task", "Task"
        GOAL = "goal", "Goal"
        MILESTONE = "milestone", "Milestone"
        ROADMAP = "roadmap", "Roadmap study"
        FOCUS = "focus", "Focus session"
        REVIEW = "review", "Weekly review"
        CUSTOM = "custom", "Custom"

    class Repeat(models.TextChoices):
        ONCE = "once", "Once"
        DAILY = "daily", "Every day"
        WEEKLY = "weekly", "On chosen days"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminders"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CUSTOM)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=240, blank=True, default="")
    # In-app destination, a hash route such as "#/goals/<id>".
    link = models.CharField(max_length=200, blank=True, default="")
    target_id = models.UUIDField(null=True, blank=True)
    repeat = models.CharField(max_length=6, choices=Repeat.choices, default=Repeat.ONCE)
    # For "once": the local date. For repeats: unused.
    local_date = models.DateField(null=True, blank=True)
    local_time = models.TimeField()
    # ISO weekdays 1 (Monday) to 7 for "weekly".
    weekdays = models.JSONField(default=list, blank=True)
    timezone_name = models.CharField(max_length=64)
    enabled = models.BooleanField(default=True)
    next_fire_at = models.DateTimeField(null=True, blank=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(repeat__in=("once", "daily", "weekly")),
                name="notifications_reminder_repeat_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(repeat="once") | models.Q(local_date__isnull=False),
                name="notifications_reminder_once_has_date",
            ),
        ]
        indexes = [
            models.Index(fields=("enabled", "next_fire_at"), name="notif_reminder_due_idx")
        ]


class ReminderDelivery(models.Model):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        NO_DEVICE = "no_device", "No subscribed device"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (too late)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminder_deliveries"
    )
    # "reminder:<id>:<fire time>", "entry:<id>:<start>", "plan:<date>", ...
    key = models.CharField(max_length=200)
    reminder = models.ForeignKey(
        Reminder, null=True, blank=True, on_delete=models.RESTRICT, related_name="deliveries"
    )
    title = models.CharField(max_length=120)
    link = models.CharField(max_length=200, blank=True, default="")
    due_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices)
    devices = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "key"), name="notifications_delivery_once")
        ]


class CalendarFeed(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="calendar_feed",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now=True)
