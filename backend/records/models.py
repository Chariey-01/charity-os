# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.db import models

from execution.models import FocusSession
from planning.models import Area, Task
from roadmaps.models import RoadmapNode


class Accomplishment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accomplishments",
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL)
    session = models.ForeignKey(
        FocusSession, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Evidence(models.Model):
    class Kind(models.TextChoices):
        NOTE = "note", "Note"
        URL = "url", "URL"
        GITHUB = "github", "GitHub URL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="evidence"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    text = models.TextField(blank=True, default="")
    url = models.URLField(blank=True, default="")
    task = models.ForeignKey(
        Task, null=True, blank=True, on_delete=models.CASCADE, related_name="evidence"
    )
    session = models.ForeignKey(
        FocusSession,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    roadmap_node = models.ForeignKey(
        RoadmapNode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    accomplishment = models.ForeignKey(
        Accomplishment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        task__isnull=False,
                        session__isnull=True,
                        roadmap_node__isnull=True,
                        accomplishment__isnull=True,
                    )
                    | models.Q(
                        task__isnull=True,
                        session__isnull=False,
                        roadmap_node__isnull=True,
                        accomplishment__isnull=True,
                    )
                    | models.Q(
                        task__isnull=True,
                        session__isnull=True,
                        roadmap_node__isnull=False,
                        accomplishment__isnull=True,
                    )
                    | models.Q(
                        task__isnull=True,
                        session__isnull=True,
                        roadmap_node__isnull=True,
                        accomplishment__isnull=False,
                    )
                ),
                name="records_evidence_exactly_one_parent",
            )
        ]
