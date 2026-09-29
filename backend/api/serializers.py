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
RoadmapNodeSerializer = serializer_for(RoadmapNode)
RoadmapPrerequisiteSerializer = serializer_for(RoadmapNodePrerequisite)
RoadmapResourceSerializer = serializer_for(RoadmapResource)
FocusSessionSerializer = serializer_for(
    FocusSession,
    read_only=(
        "started_at",
        "ended_at",
        "duration_seconds",
        "status",
        "version",
        "timezone_snapshot",
        "area_label_snapshot",
        "task_type_snapshot",
        "roadmap_ancestry_snapshot",
    ),
)
EvidenceSerializer = serializer_for(Evidence)
AccomplishmentSerializer = serializer_for(Accomplishment)
SleepLogSerializer = serializer_for(SleepLog)
ExerciseLogSerializer = serializer_for(ExerciseLog)
MealLogSerializer = serializer_for(MealLog)
WaterSerializer = serializer_for(DailyWaterTotal)
NutritionSerializer = serializer_for(DailyNutritionRating)
DailyReflectionSerializer = serializer_for(DailyReflection)
WeeklyReviewSerializer = serializer_for(WeeklyReview)
