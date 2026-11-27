from urllib.parse import urlparse

from rest_framework import serializers

from growth.models import (
    ActivityEvent,
    Goal,
    GoalCheckIn,
    JournalEntry,
    Milestone,
    Project,
    VisionItem,
    VisionRevision,
)
from growth.services import goal_progress

from .serializers import OwnedModelSerializer

STATUS_VIA_ACTION = "Change the status with POST .../status."


def _https_only(value, field):
    if value:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise serializers.ValidationError({field: ["Links must use HTTPS."]})


class StatusReadOnlyMixin:
    """Status changes write history, so they go through POST .../status."""

    def to_internal_value(self, data):
        if self.instance is not None and isinstance(data, dict) and "status" in data:
            if data["status"] != getattr(self.instance, "status", None):
                raise serializers.ValidationError({"status": [STATUS_VIA_ACTION]})
        return super().to_internal_value(data)


class VisionItemSerializer(OwnedModelSerializer):
    goals_count = serializers.SerializerMethodField()

    class Meta:
        model = VisionItem
        fields = "__all__"
        read_only_fields = (
            "user",
            "status",
            "realised_at",
            "realised_note",
            "realised_evidence_url",
            "version",
        )

    def get_goals_count(self, obj):
        return sum(1 for goal in obj.goals.all() if goal.archived_at is None)

    def validate_image_url(self, value):
        _https_only(value, "image_url")
        return value


class VisionRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisionRevision
        exclude = ("user",)


class GoalSerializer(StatusReadOnlyMixin, OwnedModelSerializer):
    progress = serializers.SerializerMethodField()
    vision_title = serializers.SerializerMethodField()
    constraint_exclude = ("completed_at",)

    class Meta:
        model = Goal
        fields = "__all__"
        read_only_fields = ("user", "completed_at", "completion_note")

    def get_progress(self, obj):
        return goal_progress(obj, self.context.get("today"))

    def get_vision_title(self, obj):
        return obj.vision.title if obj.vision_id else None

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", Goal.Kind.QUALITATIVE))
        target = attrs.get("target_value", getattr(self.instance, "target_value", None))
        if kind == Goal.Kind.MEASURABLE and target is None:
            raise serializers.ValidationError(
                {"target_value": ["A measurable goal needs a target value."]}
            )
        return super().validate(attrs)


class GoalCheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalCheckIn
        exclude = ("user",)


class MilestoneSerializer(StatusReadOnlyMixin, OwnedModelSerializer):
    tasks_total = serializers.SerializerMethodField()
    tasks_done = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Milestone
        fields = "__all__"
        read_only_fields = ("user", "completed_at", "completion_note")

    def _tasks(self, obj):
        return [t for t in obj.tasks.all() if t.archived_at is None]

    def get_tasks_total(self, obj):
        return len(self._tasks(obj))

    def get_tasks_done(self, obj):
        return sum(1 for t in self._tasks(obj) if t.status == "done")

    def get_overdue(self, obj):
        today = self.context.get("today")
        return bool(
            today and obj.target_date and obj.status == "open" and obj.target_date < today
        )

    def validate(self, attrs):
        if self.instance is not None:
            for field in ("goal", "project"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {field: ["A milestone stays with its goal or project."]}
                    )
        return super().validate(attrs)


class ProjectSerializer(StatusReadOnlyMixin, OwnedModelSerializer):
    counts = serializers.SerializerMethodField()
    goal_title = serializers.SerializerMethodField()
    constraint_exclude = ("completed_at",)

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ("user", "completed_at")

    def get_goal_title(self, obj):
        return obj.goal.title if obj.goal_id else None

    def get_counts(self, obj):
        tasks = [t for t in obj.tasks.all() if t.archived_at is None]
        milestones = [m for m in obj.milestones.all() if m.archived_at is None]
        today = self.context.get("today")
        return {
            "tasks": len(tasks),
            "open": sum(1 for t in tasks if t.status not in ("done", "cancelled")),
            "done": sum(1 for t in tasks if t.status == "done"),
            "overdue": sum(
                1
                for t in tasks
                if today
                and t.due_date
                and t.due_date < today
                and t.status not in ("done", "cancelled")
            ),
            "milestones": len(milestones),
            "milestones_done": sum(1 for m in milestones if m.status == "done"),
        }


class JournalEntrySerializer(OwnedModelSerializer):
    class Meta:
        model = JournalEntry
        fields = "__all__"
        read_only_fields = ("user", "revisions")


class ActivityEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityEvent
        exclude = ("user",)
