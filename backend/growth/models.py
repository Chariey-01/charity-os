"""Direction and long-term growth: Vision -> Goals -> Milestones -> Projects.

The product chain is Vision -> Goals -> Milestones -> Roadmaps and Projects ->
Tasks -> Schedule -> Focus -> Evidence -> Journey. Each record here owns one
responsibility:

* ``VisionItem`` is who the user wants to become: a vision statement, an
  aspiration, a manifestation or an identity statement. It is an intention.
  It is never marked realised automatically; ``realise`` needs evidence or an
  explicit confirmation (growth/services.py).
* ``Goal`` turns intention into a measurable or qualitative target with dates.
* ``GoalCheckIn`` records a measured value or a progress note. Append-only, so
  a goal's history is never rewritten.
* ``Milestone`` is a checkpoint inside one goal or one project.
* ``Project`` is an independent workspace (QUAHAXTON, FundBridge, a client).
  Projects never share tasks: a task belongs to at most one project.
* ``ActivityEvent`` is the append-only history behind My Journey. Every
  completion stores a snapshot (title, workstream, parent names) taken at that
  moment, so later edits never rewrite what was achieved.
* ``JournalEntry`` is a deliberate entry in My Journey: a decision, a challenge
  overcome, a lesson. Edits keep the previous text in ``revisions``.
"""

# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from planning.models import Area


class VisionItem(models.Model):
    class Kind(models.TextChoices):
        VISION = "vision", "Vision statement"
        ASPIRATION = "aspiration", "Aspiration"
        MANIFESTATION = "manifestation", "Manifestation"
        IDENTITY = "identity", "Who I am becoming"

    class Horizon(models.TextChoices):
        SHORT = "short", "Within a year"
        MEDIUM = "medium", "One to three years"
        LONG = "long", "Three to ten years"
        LIFETIME = "lifetime", "Lifetime"

    class Status(models.TextChoices):
        ACTIVE = "active", "Working towards"
        REALISED = "realised", "Realised"
        RELEASED = "released", "Let go"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vision_items"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ASPIRATION)
    title = models.CharField(max_length=160)
    statement = models.TextField(blank=True, default="")
    # A free-text vision category ("Career", "Health", "Faith"), user-defined.
    theme = models.CharField(max_length=60, blank=True, default="")
    horizon = models.CharField(
        max_length=10, choices=Horizon.choices, default=Horizon.MEDIUM
    )
    success_looks_like = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    image_url = models.URLField(blank=True, default="")
    target_year = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    realised_at = models.DateTimeField(null=True, blank=True)
    realised_note = models.TextField(blank=True, default="")
    realised_evidence_url = models.URLField(blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=("vision", "aspiration", "manifestation", "identity")
                ),
                name="growth_vision_kind_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(horizon__in=("short", "medium", "long", "lifetime")),
                name="growth_vision_horizon_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="realised", realised_at__isnull=False)
                    | (
                        models.Q(status__in=("active", "released"))
                        & models.Q(realised_at__isnull=True)
                    )
                ),
                name="growth_vision_realised_consistent",
            ),
            models.CheckConstraint(
                condition=models.Q(target_year__isnull=True)
                | models.Q(target_year__range=(1900, 2200)),
                name="growth_vision_target_year_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "archived_at", "position"), name="growth_vision_user_idx")
        ]


class VisionRevision(models.Model):
    """The previous wording of a vision item, kept whenever it is revised."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    vision = models.ForeignKey(
        VisionItem, on_delete=models.RESTRICT, related_name="revisions"
    )
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    statement = models.TextField(blank=True, default="")
    success_looks_like = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("vision", "version"), name="growth_vision_revision_unique"
            )
        ]


class Goal(models.Model):
    class Kind(models.TextChoices):
        MEASURABLE = "measurable", "Measurable target"
        QUALITATIVE = "qualitative", "Qualitative growth"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        RELEASED = "released", "Let go"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    why = models.TextField(blank=True, default="")
    area = models.ForeignKey(
        Area, null=True, blank=True, on_delete=models.RESTRICT, related_name="goals"
    )
    vision = models.ForeignKey(
        VisionItem,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="goals",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.QUALITATIVE)
    metric_unit = models.CharField(max_length=40, blank=True, default="")
    baseline_value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    target_value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_note = models.TextField(blank=True, default="")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=("measurable", "qualitative")),
                name="growth_goal_kind_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(kind="qualitative")
                | models.Q(target_value__isnull=False),
                name="growth_goal_measurable_has_target",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="completed", completed_at__isnull=False)
                    | (
                        models.Q(status__in=("active", "paused", "released"))
                        & models.Q(completed_at__isnull=True)
                    )
                ),
                name="growth_goal_completed_consistent",
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__isnull=True)
                | models.Q(target_date__isnull=True)
                | models.Q(target_date__gte=models.F("start_date")),
                name="growth_goal_dates_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "archived_at", "status"), name="growth_goal_user_idx")
        ]


class GoalCheckIn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    goal = models.ForeignKey(Goal, on_delete=models.RESTRICT, related_name="checkins")
    local_date = models.DateField()
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects"
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    area = models.ForeignKey(
        Area, null=True, blank=True, on_delete=models.RESTRICT, related_name="projects"
    )
    goal = models.ForeignKey(
        Goal, null=True, blank=True, on_delete=models.RESTRICT, related_name="projects"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    priority = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    color = models.CharField(max_length=7, default="#1F5A44")
    completed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "user",
                Lower("name"),
                condition=models.Q(archived_at__isnull=True),
                name="growth_project_active_name_ci_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=("planning", "active", "on_hold", "completed", "cancelled")
                ),
                name="growth_project_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(priority__range=(0, 3)),
                name="growth_project_priority_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status="completed", completed_at__isnull=False)
                | (~models.Q(status="completed") & models.Q(completed_at__isnull=True)),
                name="growth_project_completed_consistent",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="growth_project_color_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__isnull=True)
                | models.Q(deadline__isnull=True)
                | models.Q(deadline__gte=models.F("start_date")),
                name="growth_project_dates_valid",
            ),
        ]


class Milestone(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Done"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="milestones"
    )
    goal = models.ForeignKey(
        Goal, null=True, blank=True, on_delete=models.RESTRICT, related_name="milestones"
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="milestones",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_note = models.TextField(blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(goal__isnull=False, project__isnull=True)
                    | models.Q(goal__isnull=True, project__isnull=False)
                ),
                name="growth_milestone_one_parent",
            ),
            models.CheckConstraint(
                condition=models.Q(status="done", completed_at__isnull=False)
                | models.Q(status="open", completed_at__isnull=True),
                name="growth_milestone_completed_consistent",
            ),
        ]


class ActivityEvent(models.Model):
    """Append-only history for My Journey. Never updated or deleted by the API."""

    class Subject(models.TextChoices):
        VISION = "vision", "Vision"
        GOAL = "goal", "Goal"
        MILESTONE = "milestone", "Milestone"
        PROJECT = "project", "Project"
        CHALLENGE = "challenge", "Challenge"
        ROADMAP = "roadmap", "Roadmap"
        ROADMAP_ITEM = "roadmap_item", "Roadmap item"

    class Kind(models.TextChoices):
        CREATED = "created", "Created"
        COMPLETED = "completed", "Completed"
        REOPENED = "reopened", "Reopened"
        STATUS_CHANGED = "status_changed", "Status changed"
        CHECKIN = "checkin", "Check-in"
        REALISED = "realised", "Realised"
        REVISED = "revised", "Revised"
        CARRIED_FORWARD = "carried_forward", "Carried forward"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity"
    )
    subject_type = models.CharField(max_length=16, choices=Subject.choices)
    subject_id = models.UUIDField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=200)
    data = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=("user", "-occurred_at"), name="growth_activity_user_idx"),
            models.Index(
                fields=("user", "subject_type", "subject_id"),
                name="growth_activity_subject_idx",
            ),
        ]


class JournalEntry(models.Model):
    class Kind(models.TextChoices):
        REFLECTION = "reflection", "Reflection"
        DECISION = "decision", "Important decision"
        CHALLENGE = "challenge", "Challenge overcome"
        LESSON = "lesson", "Lesson learned"
        MOMENT = "moment", "Moment worth remembering"
        REVIEW = "review", "Monthly or annual review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.REFLECTION)
    title = models.CharField(max_length=180)
    body = models.TextField(blank=True, default="")
    local_date = models.DateField()
    goal = models.ForeignKey(
        Goal, null=True, blank=True, on_delete=models.RESTRICT, related_name="journal"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.RESTRICT, related_name="journal"
    )
    # Previous wording, oldest first: [{"title", "body", "replaced_at"}].
    revisions = models.JSONField(default=list, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=(
                        "reflection",
                        "decision",
                        "challenge",
                        "lesson",
                        "moment",
                        "review",
                    )
                ),
                name="growth_journal_kind_valid",
            )
        ]
