# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.db import models

from planning.models import Area, Task
from roadmaps.models import RoadmapNode


class FocusSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="focus_sessions",
    )
    task = models.ForeignKey(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="focus_sessions",
    )
    roadmap_item = models.ForeignKey(
        RoadmapNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="focus_sessions",
    )
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, related_name="focus_sessions"
    )
    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    is_deep_work = models.BooleanField()
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.TextField(blank=True, default="")
    learning = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    timezone_snapshot = models.CharField(max_length=64)
    area_label_snapshot = models.CharField(max_length=80)
    task_type_snapshot = models.CharField(max_length=40, blank=True, default="")
    roadmap_ancestry_snapshot = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(status__in=("active", "paused")),
                name="execution_one_open_session_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=("active", "paused"),
                    ended_at__isnull=True,
                    duration_seconds__isnull=True,
                )
                | models.Q(
                    status__in=("completed", "cancelled"),
                    ended_at__isnull=False,
                    duration_seconds__isnull=False,
                ),
                name="execution_session_terminal_valid",
            ),
        ]

    def elapsed_seconds(self, at=None):
        from django.utils import timezone

        at = at or self.ended_at or timezone.now()
        paused = sum(
            int(((pause.ended_at or at) - pause.started_at).total_seconds())
            for pause in self.pauses.all()
        )
        return max(0, int((at - self.started_at).total_seconds()) - paused)


class SessionPause(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.ForeignKey(
        FocusSession, on_delete=models.CASCADE, related_name="pauses"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("session",),
                condition=models.Q(ended_at__isnull=True),
                name="execution_one_open_pause_per_session",
            )
        ]


class FocusSessionCorrection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.ForeignKey(
        FocusSession, on_delete=models.CASCADE, related_name="corrections"
    )
    reason = models.TextField()
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
