from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from challenges.models import Challenge
from execution.models import FocusSession
from health.models import (
    DailyNutritionRating,
    DailyWaterTotal,
    ExerciseLog,
    MealLog,
    SleepLog,
)
from planning.models import Area, DailyCapacity, DailyPlan, DailyPlanItem, Task
from planning.services import record_due_change, transition_task
from records.models import Accomplishment, Evidence
from reflections.models import DailyReflection, WeeklyReview
from roadmaps.models import (
    Roadmap,
    RoadmapNode,
    RoadmapNodePrerequisite,
    RoadmapResource,
)


class OwnedModelSerializer(serializers.ModelSerializer):
    # Fields a serializer or service sets after validation; constraints that
    # read them are left to that later step (Task status, for example).
    constraint_exclude = ()

    def get_unique_together_validators(self):
        # DRF's generic unique-together check would run first with a generic
        # message and without the services' rules; _validate_constraints covers
        # every constraint with the messages in api/constraints.py.
        return []

    def get_fields(self):
        fields = super().get_fields()
        # Archiving goes through POST .../archive and .../restore (api/archive.py).
        if "archived_at" in fields:
            fields["archived_at"].read_only = True
        return fields

    def to_internal_value(self, data):
        if "archived_at" in self.fields and "archived_at" in data:
            raise serializers.ValidationError(
                {
                    "archived_at": [
                        "Archive or restore with POST .../archive or .../restore."
                    ]
                }
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        user = self.context["request"].user
        for value in attrs.values():
            if hasattr(value, "user_id") and value.user_id != user.id:
                raise serializers.ValidationError(
                    "Related objects must belong to the current user."
                )
        self._validate_constraints(attrs, user)
        return attrs

    def _candidate(self, attrs, user):
        """An unsaved model instance as it would be stored, for validation only."""
        model = self.Meta.model
        if self.instance is not None:
            candidate = model(
                **{
                    field.attname: getattr(self.instance, field.attname)
                    for field in model._meta.concrete_fields
                }
            )
            candidate._state.adding = False
            candidate._state.db = self.instance._state.db
        else:
            candidate = model()
            if any(field.name == "user" for field in model._meta.concrete_fields):
                candidate.user = user
        many_to_many = {field.name for field in model._meta.many_to_many}
        for field, value in attrs.items():
            if field not in many_to_many:
                setattr(candidate, field, value)
        return candidate

    def _validate_constraints(self, attrs, user):
        """Run every database constraint (unique, conditional, expression,
        check, exclusion) before saving, so duplicates and invalid combinations
        are field errors instead of an IntegrityError and HTTP 500 (B3)."""
        from .constraints import describe

        model = self.Meta.model
        candidate = self._candidate(attrs, user)
        errors = {}
        for constraint in model._meta.constraints:
            try:
                constraint.validate(
                    model, candidate, exclude=set(self.constraint_exclude)
                )
            except DjangoValidationError:
                field, message = describe(constraint.name)
                errors.setdefault(field, []).append(message)
        if errors:
            raise serializers.ValidationError(errors)

    def create(self, validated_data):
        return super().create({**validated_data, "user": self.context["request"].user})


def serializer_for(model, fields="__all__", read_only=()):
    meta = type(
        "Meta",
        (),
        {"model": model, "fields": fields, "read_only_fields": ("user", *read_only)},
    )
    return type(f"{model.__name__}Serializer", (OwnedModelSerializer,), {"Meta": meta})


class ChallengeSerializer(serializer_for(Challenge)):
    @transaction.atomic
    def update(self, instance, validated_data):
        previous = instance.status
        challenge = super().update(instance, validated_data)
        if challenge.status != previous:
            from growth.services import record

            record(
                user=self.context["request"].user,
                subject_type="challenge",
                subject=challenge,
                kind="completed"
                if challenge.status == Challenge.Status.COMPLETED
                else "status_changed",
                title=challenge.name,
                data={
                    "from": previous,
                    "to": challenge.status,
                    "start_date": challenge.start_date.isoformat(),
                    "end_date": challenge.end_date.isoformat(),
                },
            )
        return challenge
AreaSerializer = serializer_for(Area)
DailyCapacitySerializer = serializer_for(DailyCapacity)
DailyPlanSerializer = serializer_for(DailyPlan)


class DailyPlanItemSerializer(
    serializer_for(
        DailyPlanItem, read_only=("title_snapshot", "area_label_snapshot", "state")
    )
):
    """``state`` changes only through actions that write planning history
    (carry-over, remove), never through a plain write."""

    # add_plan_item appends when no position is sent and checks a sent one.
    # No default: DRF would otherwise copy the model default 0 into every create.
    position = serializers.IntegerField(required=False, min_value=0)
    constraint_exclude = ("position",)

    def to_internal_value(self, data):
        if "state" in data:
            raise serializers.ValidationError(
                {
                    "state": [
                        "Use POST .../remove or .../carry-over to change this item's "
                        "state."
                    ]
                }
            )
        return super().to_internal_value(data)


class TaskSerializer(OwnedModelSerializer):
    """Tasks with every status change routed through transition_task.

    Accepts workflow statuses and the legacy planned/completed/skipped
    input values. ``legacy_status`` is deprecated and kept for one
    release (docs/project-workspaces-design.md §13).
    """

    status = serializers.CharField(required=False)
    legacy_status = serializers.SerializerMethodField()
    # transition_task sets these after validation and enforces their rules.
    constraint_exclude = ("status", "completed_at", "cancelled_at")

    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ("user", "completed_at", "cancelled_at")

    LEGACY_OUTPUT = {"done": "completed", "cancelled": "skipped"}

    def get_legacy_status(self, obj):
        return self.LEGACY_OUTPUT.get(obj.status, "planned")

    def validate_checklist(self, value):
        if not isinstance(value, list) or len(value) > 50:
            raise serializers.ValidationError("Use a list of at most 50 items.")
        cleaned = []
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each item needs text and done.")
            text = item.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 200:
                raise serializers.ValidationError(
                    "Each item needs text of at most 200 characters."
                )
            cleaned.append(
                {
                    "id": str(item.get("id") or "")[:40],
                    "text": text.strip(),
                    "done": item.get("done") is True,
                }
            )
        return cleaned

    def validate(self, attrs):
        attrs = super().validate(attrs)

        def merged(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field) if self.instance else None

        milestone = merged("milestone")
        if milestone is not None:
            # A milestone's parent becomes the task's goal or project.
            for field in ("goal", "project"):
                parent = getattr(milestone, field)
                current = merged(field)
                if parent is not None and current is not None and current != parent:
                    raise serializers.ValidationError(
                        {"milestone": [f"This milestone belongs to another {field}."]}
                    )
                if parent is not None and current is None:
                    attrs[field] = parent
        return attrs

    def validate_status(self, value):
        value = Task.LEGACY_TO_STATUS.get(value, value)
        if value not in Task.Status.values:
            raise serializers.ValidationError(f"Unknown task status: {value}.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        status = validated_data.pop("status", Task.Status.TODO)
        open_status = status if status in Task.OPEN_STATUSES else Task.Status.TODO
        task = super().create({**validated_data, "status": open_status})
        if status != open_status:
            task = transition_task(
                user=self.context["request"].user, task=task, target=status
            )
        return task

    @transaction.atomic
    def update(self, instance, validated_data):
        status = validated_data.pop("status", None)
        previous_due = instance.due_date
        task = super().update(instance, validated_data)
        record_due_change(
            user=self.context["request"].user, task=task, previous=previous_due
        )
        if status is not None and status != task.status:
            task = transition_task(
                user=self.context["request"].user, task=task, target=status
            )
        return task


class RoadmapSerializer(serializer_for(Roadmap)):
    @transaction.atomic
    def update(self, instance, validated_data):
        previous = instance.status
        roadmap = super().update(instance, validated_data)
        if roadmap.status != previous and Roadmap.Status.COMPLETED in (
            previous,
            roadmap.status,
        ):
            from growth.services import record

            record(
                user=self.context["request"].user,
                subject_type="roadmap",
                subject=roadmap,
                kind="completed"
                if roadmap.status == Roadmap.Status.COMPLETED
                else "reopened",
                title=roadmap.title,
                data={"progress": roadmap.progress()},
            )
        return roadmap


class RoadmapNodeSerializer(OwnedModelSerializer):
    """Tree changes are validated under the roadmap's row lock: same roadmap,
    no self or descendant parent, no archived parent, and a node never moves
    to another roadmap."""

    class Meta:
        model = RoadmapNode
        fields = "__all__"
        read_only_fields = ("user", "completed_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        roadmap = attrs.get("roadmap")
        if (
            self.instance is not None
            and roadmap
            and roadmap.pk != self.instance.roadmap_id
        ):
            raise serializers.ValidationError(
                {"roadmap": ["A node cannot move to another roadmap."]}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from roadmaps.services import lock_roadmap, validate_parent

        roadmap = lock_roadmap(
            user=self.context["request"].user, roadmap_id=validated_data["roadmap"].pk
        )
        validate_parent(roadmap=roadmap, parent=validated_data.get("parent"))
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        from roadmaps.services import lock_roadmap, validate_parent

        roadmap = lock_roadmap(
            user=self.context["request"].user, roadmap_id=instance.roadmap_id
        )
        if "parent" in validated_data:
            validate_parent(
                roadmap=roadmap, parent=validated_data["parent"], node_pk=instance.pk
            )
        state = validated_data.get("state", instance.state)
        if state == RoadmapNode.State.COMPLETED and instance.state != state:
            from django.utils import timezone

            from growth.services import record

            instance.completed_at = timezone.now()
            record(
                user=self.context["request"].user,
                subject_type="roadmap_item",
                subject=instance,
                kind="completed",
                title=validated_data.get("title", instance.title),
                data={
                    "roadmap": roadmap.title,
                    "roadmap_id": str(roadmap.pk),
                    "parent": instance.parent.title if instance.parent_id else None,
                    "node_type": instance.node_type,
                },
            )
        elif state != RoadmapNode.State.COMPLETED:
            instance.completed_at = None
        instance.state = state
        for field, value in validated_data.items():
            if field != "state":
                setattr(instance, field, value)
        instance.save()
        return instance


RoadmapPrerequisiteSerializer = serializer_for(RoadmapNodePrerequisite)
RoadmapResourceSerializer = serializer_for(RoadmapResource)


class FocusSessionSerializer(OwnedModelSerializer):
    elapsed_seconds = serializers.SerializerMethodField()
    schedule_entry = serializers.SerializerMethodField()

    class Meta:
        model = FocusSession
        fields = "__all__"
        read_only_fields = (
            "user",
            "started_at",
            "ended_at",
            "duration_seconds",
            "status",
            "version",
            "timezone_snapshot",
            "area_label_snapshot",
            "task_type_snapshot",
            "roadmap_ancestry_snapshot",
            "elapsed_seconds",
            "schedule_entry",
        )

    def get_schedule_entry(self, obj):
        entry = getattr(obj, "schedule_entry", None)
        return str(entry.pk) if entry else None

    def get_elapsed_seconds(self, obj):
        return (
            obj.duration_seconds
            if obj.status in ("completed", "cancelled")
            else obj.elapsed_seconds()
        )


class EvidenceSerializer(OwnedModelSerializer):
    class Meta:
        model = Evidence
        fields = "__all__"
        read_only_fields = ("user",)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        # Check the record as it will be stored, not just the fields sent: an
        # update that changes only `url` must still obey its kind's rules.
        def merged(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field) if self.instance else ""

        kind, url, note = merged("kind"), merged("url") or "", merged("text") or ""
        if kind == "note" and not note.strip():
            raise serializers.ValidationError({"text": "A note requires text."})
        if kind in ("url", "github"):
            if not url:
                raise serializers.ValidationError({"url": "A link requires a URL."})
            parsed = urlparse(url)
            local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
            if parsed.scheme != "https" and not (local and settings.DEBUG):
                raise serializers.ValidationError(
                    {"url": "Evidence URLs must use HTTPS."}
                )
            if kind == "github" and parsed.hostname not in (
                "github.com",
                "www.github.com",
            ):
                raise serializers.ValidationError(
                    {"url": "A GitHub URL must use github.com."}
                )
        return attrs


AccomplishmentSerializer = serializer_for(Accomplishment)


class SleepLogSerializer(OwnedModelSerializer):
    wake_local_date = serializers.DateField(read_only=True)

    class Meta:
        model = SleepLog
        fields = "__all__"
        read_only_fields = ("user", "wake_local_date")

    def create(self, validated_data):
        validated_data["wake_local_date"] = (
            validated_data["woke_at"]
            .astimezone(ZoneInfo(validated_data["timezone_name"]))
            .date()
        )
        return super().create(validated_data)


ExerciseLogSerializer = serializer_for(ExerciseLog)
MealLogSerializer = serializer_for(MealLog)
WaterSerializer = serializer_for(DailyWaterTotal)
NutritionSerializer = serializer_for(DailyNutritionRating)
DailyReflectionSerializer = serializer_for(DailyReflection, read_only=("version",))
WeeklyReviewSerializer = serializer_for(WeeklyReview, read_only=("version",))
