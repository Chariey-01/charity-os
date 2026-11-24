from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
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
from records.models import Accomplishment, Evidence
from reflections.models import DailyReflection, WeeklyReview
from roadmaps.models import (
    Roadmap,
    RoadmapNode,
    RoadmapNodePrerequisite,
    RoadmapResource,
)


class OwnedModelSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        user = self.context["request"].user
        for value in attrs.values():
            if hasattr(value, "user_id") and value.user_id != user.id:
                raise serializers.ValidationError(
                    "Related objects must belong to the current user."
                )
        return attrs

    def create(self, validated_data):
        return super().create({**validated_data, "user": self.context["request"].user})


def serializer_for(model, fields="__all__", read_only=()):
    meta = type(
        "Meta",
        (),
        {"model": model, "fields": fields, "read_only_fields": ("user", *read_only)},
    )
    return type(f"{model.__name__}Serializer", (OwnedModelSerializer,), {"Meta": meta})


ChallengeSerializer = serializer_for(Challenge)
AreaSerializer = serializer_for(Area)
DailyCapacitySerializer = serializer_for(DailyCapacity)
DailyPlanSerializer = serializer_for(DailyPlan)
DailyPlanItemSerializer = serializer_for(
    DailyPlanItem, read_only=("title_snapshot", "area_label_snapshot")
)
TaskSerializer = serializer_for(Task, read_only=("completed_at", "skipped_at"))
RoadmapSerializer = serializer_for(Roadmap)


class RoadmapNodeSerializer(OwnedModelSerializer):
    class Meta:
        model = RoadmapNode
        fields = "__all__"
        read_only_fields = ("user", "completed_at")

    def update(self, instance, validated_data):
        state = validated_data.get("state", instance.state)
        if state == RoadmapNode.State.COMPLETED and instance.state != state:
            from django.utils import timezone

            instance.completed_at = timezone.now()
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
        )

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
        kind, url, note = attrs.get("kind"), attrs.get("url", ""), attrs.get("text", "")
        if kind == "note" and not note.strip():
            raise serializers.ValidationError({"text": "A note requires text."})
        if kind in ("url", "github"):
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
DailyReflectionSerializer = serializer_for(DailyReflection)
WeeklyReviewSerializer = serializer_for(WeeklyReview)
