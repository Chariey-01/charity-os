import uuid

from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum
from django.middleware.csrf import get_token
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from challenges.models import Challenge
from execution.models import FocusSession
from execution.services import end_session, pause_session, resume_session, start_session
from health.models import (
    DailyNutritionRating,
    DailyWaterTotal,
    ExerciseLog,
    MealLog,
    SleepLog,
)
from planning.models import Area, DailyCapacity, DailyPlan, DailyPlanItem, Task
from planning.services import add_plan_item, carry_over, transition_task
from records.models import Accomplishment, Evidence
from reflections.models import DailyReflection, WeeklyReview
from roadmaps.models import (
    Roadmap,
    RoadmapNode,
    RoadmapNodePrerequisite,
    RoadmapResource,
)

from . import serializers as s


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"csrf_token": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(
        request,
        email=request.data.get("email", ""),
        password=request.data.get("password", ""),
    )
    if not user:
        return Response(
            {
                "error": {
                    "code": "invalid_credentials",
                    "message": "Invalid email or password.",
                }
            },
            status=400,
        )
    login(request, user)
    return Response(
        {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "timezone": user.timezone,
        }
    )


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response(status=204)


@api_view(["GET", "PATCH"])
def me(request):
    if request.method == "PATCH":
        for field in ("display_name", "timezone"):
            if field in request.data:
                setattr(request.user, field, request.data[field])
        request.user.full_clean()
        request.user.save()
    return Response(
        {
            "id": str(request.user.id),
            "email": request.user.email,
            "display_name": request.user.display_name,
            "timezone": request.user.timezone,
        }
    )


class OwnedViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by("-pk")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


def owned_viewset(name, model, serializer):
    return type(
        name,
        (OwnedViewSet,),
        {"queryset": model.objects.all(), "serializer_class": serializer},
    )


ChallengeViewSet = owned_viewset("ChallengeViewSet", Challenge, s.ChallengeSerializer)
AreaViewSet = owned_viewset("AreaViewSet", Area, s.AreaSerializer)
CapacityViewSet = owned_viewset(
    "CapacityViewSet", DailyCapacity, s.DailyCapacitySerializer
)
DailyPlanViewSet = owned_viewset("DailyPlanViewSet", DailyPlan, s.DailyPlanSerializer)
RoadmapViewSet = owned_viewset("RoadmapViewSet", Roadmap, s.RoadmapSerializer)
RoadmapNodeViewSet = owned_viewset(
    "RoadmapNodeViewSet", RoadmapNode, s.RoadmapNodeSerializer
)
RoadmapPrerequisiteViewSet = owned_viewset(
    "RoadmapPrerequisiteViewSet",
    RoadmapNodePrerequisite,
    s.RoadmapPrerequisiteSerializer,
)
RoadmapResourceViewSet = owned_viewset(
    "RoadmapResourceViewSet", RoadmapResource, s.RoadmapResourceSerializer
)
EvidenceViewSet = owned_viewset("EvidenceViewSet", Evidence, s.EvidenceSerializer)
AccomplishmentViewSet = owned_viewset(
    "AccomplishmentViewSet", Accomplishment, s.AccomplishmentSerializer
)
SleepLogViewSet = owned_viewset("SleepLogViewSet", SleepLog, s.SleepLogSerializer)
ExerciseLogViewSet = owned_viewset(
    "ExerciseLogViewSet", ExerciseLog, s.ExerciseLogSerializer
)
MealLogViewSet = owned_viewset("MealLogViewSet", MealLog, s.MealLogSerializer)
WaterViewSet = owned_viewset("WaterViewSet", DailyWaterTotal, s.WaterSerializer)
NutritionViewSet = owned_viewset(
    "NutritionViewSet", DailyNutritionRating, s.NutritionSerializer
)
DailyReflectionViewSet = owned_viewset(
    "DailyReflectionViewSet", DailyReflection, s.DailyReflectionSerializer
)
WeeklyReviewViewSet = owned_viewset(
    "WeeklyReviewViewSet", WeeklyReview, s.WeeklyReviewSerializer
)


class TaskViewSet(OwnedViewSet):
    queryset = Task.objects.all()
    serializer_class = s.TaskSerializer

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return Response(
            self.get_serializer(
                transition_task(
                    user=request.user, task=self.get_object(), target="completed"
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def skip(self, request, pk=None):
        return Response(
            self.get_serializer(
                transition_task(
                    user=request.user, task=self.get_object(), target="skipped"
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return Response(
            self.get_serializer(
                transition_task(
                    user=request.user, task=self.get_object(), target="planned"
                )
            ).data
        )


class PlanItemViewSet(OwnedViewSet):
    queryset = DailyPlanItem.objects.all()
    serializer_class = s.DailyPlanItemSerializer

    def perform_create(self, serializer):
        data = serializer.validated_data
        self.instance = add_plan_item(
            user=self.request.user,
            plan=data["plan"],
            task=data["task"],
            kind=data.get("kind", "secondary"),
            position=data.get("position", 0),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(self.get_serializer(self.instance).data, status=201)

    @action(detail=True, methods=["post"], url_path="carry-over")
    def carry(self, request, pk=None):
        item = carry_over(
            user=request.user,
            item=self.get_object(),
            destination_date=request.data["destination_date"],
        )
        return Response(self.get_serializer(item).data)


class SessionViewSet(OwnedViewSet):
    queryset = FocusSession.objects.all()
    serializer_class = s.FocusSessionSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=False, methods=["get"])
    def active(self, request):
        obj = self.get_queryset().filter(status__in=("active", "paused")).first()
        return Response(self.get_serializer(obj).data if obj else None)

    @action(detail=False, methods=["post"])
    def start(self, request):
        area = Area.objects.get(pk=request.data["area"], user=request.user)
        task = Task.objects.filter(
            pk=request.data.get("task"), user=request.user
        ).first()
        node = RoadmapNode.objects.filter(
            pk=request.data.get("roadmap_item"), user=request.user
        ).first()
        obj = start_session(
            user=request.user,
            session_id=uuid.UUID(request.data["id"]),
            area=area,
            title=request.data["title"],
            is_deep_work=request.data["is_deep_work"],
            task=task,
            roadmap_item=node,
        )
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        obj = pause_session(
            user=request.user,
            session_id=pk,
            pause_id=uuid.UUID(request.data["id"]),
            expected_version=request.data.get("expected_version"),
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        obj = resume_session(
            user=request.user,
            session_id=pk,
            expected_version=request.data.get("expected_version"),
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        obj = end_session(
            user=request.user,
            session_id=pk,
            target="completed",
            expected_version=request.data.get("expected_version"),
            outcome=request.data.get("outcome", ""),
            learning=request.data.get("learning", ""),
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        obj = end_session(
            user=request.user,
            session_id=pk,
            target="cancelled",
            expected_version=request.data.get("expected_version"),
        )
        return Response(self.get_serializer(obj).data)


@api_view(["GET"])
def metrics(request):
    sessions = FocusSession.objects.filter(user=request.user, status="completed")
    total = sessions.aggregate(value=Sum("duration_seconds"))["value"] or 0
    deep = (
        sessions.filter(is_deep_work=True).aggregate(value=Sum("duration_seconds"))[
            "value"
        ]
        or 0
    )
    appearances = DailyPlanItem.objects.filter(user=request.user).exclude(
        state="removed"
    )
    completed = appearances.filter(task__status="completed").count()
    return Response(
        {
            "total_focused_minutes": total // 60,
            "deep_work_minutes": deep // 60,
            "planned_appearances": appearances.count(),
            "completed_planned_appearances": completed,
            "planned_completion_rate": completed / appearances.count()
            if appearances.count()
            else 0,
        }
    )
