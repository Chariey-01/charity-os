import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from execution.models import FocusSession
from planning.models import Area, Task
from roadmaps.models import RoadmapNode

MAX_ENTRY_SECONDS = 24 * 60 * 60


class ScheduleEntry(models.Model):
    """A planned block of time for any activity.

    Distinct from ``Task`` (work to accomplish) and ``FocusSession`` (actual
    focused time). A ``focus`` entry obtains its actual time from its linked
    session; a ``manual`` entry stores actual time itself. Never both.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        PARTIALLY_COMPLETED = "partially_completed", "Partially completed"
        SKIPPED = "skipped", "Skipped"
        CANCELLED = "cancelled", "Cancelled"
        RESCHEDULED = "rescheduled", "Rescheduled"

    class Tracking(models.TextChoices):
        MANUAL = "manual", "Manual"
        FOCUS = "focus", "Focus session"

    OPEN_STATUSES = (Status.SCHEDULED, Status.IN_PROGRESS, Status.PAUSED)
    RUNNING_STATUSES = (Status.IN_PROGRESS, Status.PAUSED)
    DONE_STATUSES = (Status.COMPLETED, Status.PARTIALLY_COMPLETED)
    CLOSED_STATUSES = (
        Status.COMPLETED,
        Status.PARTIALLY_COMPLETED,
        Status.SKIPPED,
        Status.CANCELLED,
        Status.RESCHEDULED,
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedule_entries",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    area = models.ForeignKey(
        Area,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedule_entries",
    )
    area_label_snapshot = models.CharField(max_length=80, blank=True, default="")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    timezone_name = models.CharField(max_length=64)
    local_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    tracking = models.CharField(
        max_length=10, choices=Tracking.choices, default=Tracking.MANUAL
    )
    task = models.ForeignKey(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedule_entries",
    )
    roadmap_node = models.ForeignKey(
        RoadmapNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedule_entries",
    )
    focus_session = models.OneToOneField(
        FocusSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedule_entry",
    )
    rescheduled_from = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rescheduled_to",
    )
    actual_started_at = models.DateTimeField(null=True, blank=True)
    actual_ended_at = models.DateTimeField(null=True, blank=True)
    actual_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_seconds = models.PositiveIntegerField(default=0)
    outcome = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("start_at", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="scheduling_entry_time_order",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    end_at__lte=models.F("start_at")
                    + timedelta(seconds=MAX_ENTRY_SECONDS)
                ),
                name="scheduling_entry_max_24h",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=(
                        "scheduled",
                        "in_progress",
                        "paused",
                        "completed",
                        "partially_completed",
                        "skipped",
                        "cancelled",
                        "rescheduled",
                    )
                ),
                name="scheduling_entry_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(tracking__in=("manual", "focus")),
                name="scheduling_entry_tracking_valid",
            ),
            # Running entries must have a clock: their own or a focus session.
            models.CheckConstraint(
                condition=~models.Q(status__in=("in_progress", "paused"))
                | models.Q(actual_started_at__isnull=False)
                | models.Q(focus_session__isnull=False),
                name="scheduling_entry_running_has_start",
            ),
            # A manual pause needs a pause instant; nothing else may carry one.
            models.CheckConstraint(
                condition=~models.Q(
                    status="paused", focus_session__isnull=True, paused_at__isnull=True
                )
                & (models.Q(status="paused") | models.Q(paused_at__isnull=True)),
                name="scheduling_entry_pause_fields_valid",
            ),
            # Never store actual time twice: a linked session owns it.
            models.CheckConstraint(
                condition=models.Q(focus_session__isnull=True)
                | models.Q(
                    actual_started_at__isnull=True,
                    actual_ended_at__isnull=True,
                    actual_duration_seconds__isnull=True,
                    paused_at__isnull=True,
                    paused_seconds=0,
                ),
                name="scheduling_entry_no_double_actuals",
            ),
            models.CheckConstraint(
                condition=models.Q(actual_ended_at__isnull=True)
                | models.Q(actual_started_at__isnull=True)
                | models.Q(actual_ended_at__gt=models.F("actual_started_at")),
                name="scheduling_entry_actual_order",
            ),
            models.CheckConstraint(
                condition=models.Q(actual_duration_seconds__isnull=True)
                | models.Q(actual_duration_seconds__lte=MAX_ENTRY_SECONDS),
                name="scheduling_entry_actual_max_24h",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=("scheduled", "in_progress", "paused"),
                    closed_at__isnull=True,
                )
                | models.Q(
                    status__in=(
                        "completed",
                        "partially_completed",
                        "skipped",
                        "cancelled",
                        "rescheduled",
                    ),
                    closed_at__isnull=False,
                ),
                name="scheduling_entry_closed_fields_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(rescheduled_from=models.F("id")),
                name="scheduling_entry_not_own_reschedule",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "start_at"), name="sched_entry_user_start_idx"
            ),
            models.Index(
                fields=("user", "local_date"), name="sched_entry_user_date_idx"
            ),
            models.Index(fields=("user", "status"), name="sched_entry_user_status_idx"),
        ]

    def __str__(self):
        return f"{self.title} ({self.local_date})"

    @property
    def planned_seconds(self):
        return int((self.end_at - self.start_at).total_seconds())

    def actual_seconds(self, at=None):
        """Actual seconds for this entry, or ``None`` when unknown.

        Linked focus time comes from the session; it is never copied here.
        """
        if self.focus_session_id:
            session = self.focus_session
            if session.status == FocusSession.Status.CANCELLED:
                return None
            if session.duration_seconds is not None:
                return session.duration_seconds
            return session.elapsed_seconds(at=at)
        if self.actual_duration_seconds is not None:
            return self.actual_duration_seconds
        if self.status in self.RUNNING_STATUSES and self.actual_started_at:
            at = self.paused_at or at or timezone.now()
            measured = int((at - self.actual_started_at).total_seconds())
            return max(0, measured - self.paused_seconds)
        return None
