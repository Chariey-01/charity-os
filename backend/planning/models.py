# ruff: noqa: DJ008
import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from challenges.models import Challenge

HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Area(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="areas",
    )
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90)
    color = models.CharField(max_length=7, default="#64748B")
    icon = models.CharField(max_length=50, blank=True, default="")
    sort_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "user",
                Lower("name"),
                condition=models.Q(archived_at__isnull=True),
                name="planning_area_active_name_ci_unique",
            ),
            models.UniqueConstraint(
                fields=("user", "slug"),
                name="planning_area_user_slug_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="planning_area_color_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(sort_order__gte=0),
                name="planning_area_sort_order_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "archived_at", "sort_order"),
                name="planning_area_user_order_idx",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if self.color and HEX_COLOR_PATTERN.fullmatch(self.color) is None:
            errors["color"] = "Color must be a hex RGB value such as #64748B."
        if self.sort_order is not None and self.sort_order < 0:
            errors["sort_order"] = "Sort order cannot be negative."
        if errors:
            raise ValidationError(errors)


class DailyCapacity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_capacities",
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    available_minutes = models.IntegerField(default=0)
    deep_work_minutes = models.IntegerField(default=0)
    fixed_commitments = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "local_date"),
                name="planning_capacity_user_date_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(available_minutes__range=(0, 1440)),
                name="planning_capacity_available_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(deep_work_minutes__range=(0, 1440)),
                name="planning_capacity_deep_work_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    deep_work_minutes__lte=models.F("available_minutes")
                ),
                name="planning_capacity_deep_lte_available",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "-local_date"),
                name="plan_capacity_user_date_idx",
            )
        ]

    def __str__(self):
        return f"{self.local_date} capacity"

    def clean(self):
        super().clean()
        errors = {}
        for field_name in ("available_minutes", "deep_work_minutes"):
            value = getattr(self, field_name)
            if value is not None and not 0 <= value <= 1440:
                errors[field_name] = "Minutes must be between 0 and 1440."
        if (
            self.deep_work_minutes is not None
            and self.available_minutes is not None
            and self.deep_work_minutes > self.available_minutes
        ):
            errors["deep_work_minutes"] = (
                "Deep-work minutes cannot exceed available minutes."
            )
        if self.timezone_name:
            try:
                ZoneInfo(self.timezone_name)
            except ZoneInfoNotFoundError:
                errors["timezone_name"] = "Timezone must be a valid IANA zone name."
        if errors:
            raise ValidationError(errors)


class Task(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    area = models.ForeignKey(
        Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    roadmap_item = models.ForeignKey(
        "roadmaps.RoadmapNode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    priority = models.PositiveSmallIntegerField(default=0)
    estimated_minutes = models.PositiveIntegerField(null=True, blank=True)
    task_type = models.CharField(max_length=40, blank=True, default="")
    is_deep_work_default = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PLANNED
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    skipped_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=("planned", "completed", "skipped")),
                name="planning_task_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="planned",
                        completed_at__isnull=True,
                        skipped_at__isnull=True,
                    )
                    | models.Q(
                        status="completed",
                        completed_at__isnull=False,
                        skipped_at__isnull=True,
                    )
                    | models.Q(
                        status="skipped",
                        completed_at__isnull=True,
                        skipped_at__isnull=False,
                    )
                ),
                name="planning_task_terminal_fields_valid",
            ),
        ]


class DailyPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_plans"
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    challenge = models.ForeignKey(
        Challenge,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_plans",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "local_date"), name="planning_plan_user_date_unique"
            )
        ]


class DailyPlanItem(models.Model):
    class Kind(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"

    class State(models.TextChoices):
        CURRENT = "current", "Current"
        CARRIED_FORWARD = "carried_forward", "Carried forward"
        REMOVED = "removed", "Removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_plan_items",
    )
    plan = models.ForeignKey(DailyPlan, on_delete=models.CASCADE, related_name="items")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="plan_items")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SECONDARY)
    position = models.PositiveIntegerField(default=0)
    state = models.CharField(
        max_length=20, choices=State.choices, default=State.CURRENT
    )
    title_snapshot = models.CharField(max_length=200)
    area_label_snapshot = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("task",),
                condition=models.Q(state="current"),
                name="planning_item_one_current_per_task",
            ),
            models.UniqueConstraint(
                fields=("plan", "position"),
                condition=models.Q(state="current"),
                name="planning_item_current_position_unique",
            ),
        ]


class PlanningEvent(models.Model):
    class EventType(models.TextChoices):
        PLANNED = "planned", "Planned"
        CARRIED_OVER = "carried_over", "Carried over"
        REMOVED = "removed", "Removed"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"
        REOPENED = "reopened", "Reopened"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="planning_events",
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    task = models.ForeignKey(
        Task, null=True, on_delete=models.SET_NULL, related_name="planning_events"
    )
    source_item = models.ForeignKey(
        DailyPlanItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_events",
    )
    destination_item = models.ForeignKey(
        DailyPlanItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="destination_events",
    )
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
