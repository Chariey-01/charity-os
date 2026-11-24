import uuid
from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Sum
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from challenges.models import Challenge
from execution.models import FocusSession
from execution.services import (
    correct_session,
    end_session,
    pause_session,
    resume_session,
    start_session,
)
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
from roadmaps.services import next_actions, roadmap_tree
from scheduling.services import sync_entry_from_session

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


def challenge_summary(challenge, today=None):
    today = today or date.today()
    total = (challenge.end_date - challenge.start_date).days + 1
    if today < challenge.start_date:
        day = 0
        remaining = total
        phase = "upcoming"
    elif today > challenge.end_date:
        day = total
        remaining = 0
        phase = "completed"
    else:
        day = (today - challenge.start_date).days + 1
        remaining = (challenge.end_date - today).days
        phase = "active"
    return {
        "id": str(challenge.id),
        "name": challenge.name,
        "description": challenge.description,
        "start_date": challenge.start_date,
        "end_date": challenge.end_date,
        "status": challenge.status,
        "is_primary": challenge.is_primary,
        "total_days": total,
        "current_day": day,
        "days_remaining": remaining,
        "progress_percent": round((day / total) * 100, 1) if total else 0,
        "phase": phase,
    }


class ChallengeViewSet(
    owned_viewset("ChallengeViewSet", Challenge, s.ChallengeSerializer)
):
    @action(detail=True, methods=["post"], url_path="set-primary")
    def set_primary(self, request, pk=None):
        challenge = self.get_object()
        Challenge.objects.filter(user=request.user, is_primary=True).update(
            is_primary=False
        )
        challenge.is_primary = True
        challenge.save(update_fields=("is_primary", "updated_at"))
        return Response(self.get_serializer(challenge).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        challenge = self.get_object()
        challenge.archived_at = timezone.now()
        challenge.is_primary = False
        challenge.status = Challenge.Status.CANCELLED
        challenge.save(
            update_fields=("archived_at", "is_primary", "status", "updated_at")
        )
        return Response(self.get_serializer(challenge).data)

    @action(detail=False, methods=["get"])
    def primary(self, request):
        challenge = (
            self.get_queryset()
            .filter(is_primary=True, archived_at__isnull=True)
            .first()
        )
        return Response(challenge_summary(challenge) if challenge else None)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data = [
            {**item, **challenge_summary(self.get_queryset().get(pk=item["id"]))}
            for item in response.data
        ]
        return response


AreaViewSet = owned_viewset("AreaViewSet", Area, s.AreaSerializer)


class AreaViewSet(AreaViewSet):
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by(
            "sort_order", "name"
        )


CapacityViewSet = owned_viewset(
    "CapacityViewSet", DailyCapacity, s.DailyCapacitySerializer
)


class CapacityViewSet(CapacityViewSet):
    def create(self, request, *args, **kwargs):
        existing = DailyCapacity.objects.filter(
            user=request.user, local_date=request.data.get("local_date")
        ).first()
        if existing:
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return super().create(request, *args, **kwargs)


DailyPlanViewSet = owned_viewset("DailyPlanViewSet", DailyPlan, s.DailyPlanSerializer)
RoadmapViewSet = owned_viewset("RoadmapViewSet", Roadmap, s.RoadmapSerializer)


class RoadmapViewSet(RoadmapViewSet):
    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        return Response(self.get_object().progress())

    @action(detail=True, methods=["get"])
    def tree(self, request, pk=None):
        return Response(
            {
                "roadmap": self.get_serializer(self.get_object()).data,
                "nodes": roadmap_tree(self.get_object()),
            }
        )

    @action(detail=False, methods=["get"], url_path="next-actions")
    def next_actions(self, request):
        return Response(
            next_actions(
                request.user, limit=min(int(request.query_params.get("limit", 5)), 20)
            )
        )


class DailyPlanViewSet(DailyPlanViewSet):
    @action(detail=False, methods=["get"])
    def today(self, request):
        requested = request.query_params.get("date")
        try:
            local_date = (
                date.fromisoformat(requested)
                if requested
                else timezone.localtime(
                    timezone.now(), ZoneInfo(request.user.timezone)
                ).date()
            )
        except ValueError as exc:
            raise serializers.ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        plan, _ = DailyPlan.objects.get_or_create(
            user=request.user,
            local_date=local_date,
            defaults={"timezone_name": request.user.timezone},
        )
        challenge = Challenge.objects.filter(
            user=request.user, is_primary=True, archived_at__isnull=True
        ).first()
        if challenge and plan.challenge_id != challenge.id:
            plan.challenge = challenge
            plan.save(update_fields=("challenge", "updated_at"))
        capacity = DailyCapacity.objects.filter(
            user=request.user, local_date=local_date
        ).first()
        items = (
            plan.items.select_related("task", "task__area")
            .filter(state=DailyPlanItem.State.CURRENT)
            .order_by("kind", "position")
        )
        return Response(
            {
                "plan": self.get_serializer(plan).data,
                "challenge": challenge_summary(challenge) if challenge else None,
                "capacity": s.DailyCapacitySerializer(
                    capacity, context={"request": request}
                ).data
                if capacity
                else None,
                "items": s.DailyPlanItemSerializer(
                    items, many=True, context={"request": request}
                ).data,
                "tasks": s.TaskSerializer(
                    Task.objects.filter(
                        user=request.user, created_at__date=local_date
                    ).order_by("-priority", "created_at"),
                    many=True,
                    context={"request": request},
                ).data,
            }
        )


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
                    user=request.user, task=self.get_object(), target=Task.Status.DONE
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def skip(self, request, pk=None):
        return Response(
            self.get_serializer(
                transition_task(
                    user=request.user,
                    task=self.get_object(),
                    target=Task.Status.CANCELLED,
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        target = request.data.get("status")
        if not target:
            raise serializers.ValidationError({"status": "This field is required."})
        task = transition_task(
            user=request.user,
            task=self.get_object(),
            target=target,
            reason=str(request.data.get("reason", "") or ""),
        )
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return Response(
            self.get_serializer(
                transition_task(
                    user=request.user, task=self.get_object(), target=Task.Status.TODO
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
    queryset = FocusSession.objects.select_related("schedule_entry")
    serializer_class = s.FocusSessionSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=False, methods=["get"])
    def active(self, request):
        obj = self.get_queryset().filter(status__in=("active", "paused")).first()
        return Response(self.get_serializer(obj).data if obj else None)

    @action(detail=False, methods=["post"])
    def start(self, request):
        required = ("id", "title", "area", "is_deep_work")
        missing = [
            field
            for field in required
            if field not in request.data or request.data[field] in ("", None)
        ]
        if missing:
            raise serializers.ValidationError(
                {field: "This field is required." for field in missing}
            )
        try:
            area = Area.objects.get(pk=request.data["area"], user=request.user)
            session_id = uuid.UUID(str(request.data["id"]))
        except (Area.DoesNotExist, ValueError, TypeError) as exc:
            raise serializers.ValidationError({"area": "Choose a valid area."}) from exc
        task = Task.objects.filter(
            pk=request.data.get("task"), user=request.user
        ).first()
        node = RoadmapNode.objects.filter(
            pk=request.data.get("roadmap_item"), user=request.user
        ).first()
        obj = start_session(
            user=request.user,
            session_id=session_id,
            area=area,
            title=request.data["title"],
            is_deep_work=request.data["is_deep_work"],
            task=task,
            roadmap_item=node,
        )
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        try:
            pause_id = uuid.UUID(str(request.data.get("id", "")))
        except (ValueError, TypeError) as exc:
            raise serializers.ValidationError(
                {"id": "A pause id is required."}
            ) from exc
        with transaction.atomic():
            obj = pause_session(
                user=request.user,
                session_id=pk,
                pause_id=pause_id,
                expected_version=request.data.get("expected_version"),
            )
            sync_entry_from_session(user=request.user, session=obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        with transaction.atomic():
            obj = resume_session(
                user=request.user,
                session_id=pk,
                expected_version=request.data.get("expected_version"),
            )
            sync_entry_from_session(user=request.user, session=obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        with transaction.atomic():
            obj = end_session(
                user=request.user,
                session_id=pk,
                target="completed",
                expected_version=request.data.get("expected_version"),
                outcome=request.data.get("outcome", ""),
                learning=request.data.get("learning", ""),
            )
            sync_entry_from_session(user=request.user, session=obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            obj = end_session(
                user=request.user,
                session_id=pk,
                target="cancelled",
                expected_version=request.data.get("expected_version"),
            )
            sync_entry_from_session(user=request.user, session=obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def corrections(self, request, pk=None):
        from rest_framework.fields import DateTimeField

        field = DateTimeField()
        obj = correct_session(
            user=request.user,
            session_id=pk,
            reason=request.data.get("reason", ""),
            started_at=field.to_internal_value(request.data["started_at"])
            if request.data.get("started_at")
            else None,
            ended_at=field.to_internal_value(request.data["ended_at"])
            if request.data.get("ended_at")
            else None,
            expected_version=request.data.get("expected_version"),
        )
        return Response(self.get_serializer(obj).data)


@api_view(["GET"])
def metrics(request):
    tz = ZoneInfo(request.user.timezone)
    today = timezone.localtime(timezone.now(), tz).date()
    period = request.query_params.get("period", "30d")
    if period == "7d":
        start = today - timedelta(days=6)
    elif period == "90d":
        start = today - timedelta(days=89)
    elif period == "year":
        start = today.replace(month=1, day=1)
    elif period == "challenge":
        primary = Challenge.objects.filter(
            user=request.user, is_primary=True, archived_at__isnull=True
        ).first()
        start = (
            max(primary.start_date, today - timedelta(days=365))
            if primary
            else today - timedelta(days=29)
        )
    elif request.query_params.get("start"):
        try:
            start = date.fromisoformat(request.query_params["start"])
        except ValueError as exc:
            raise serializers.ValidationError({"start": "Use YYYY-MM-DD."}) from exc
    else:
        start = today - timedelta(days=29)
    end = today
    if request.query_params.get("end"):
        try:
            end = date.fromisoformat(request.query_params["end"])
        except ValueError as exc:
            raise serializers.ValidationError({"end": "Use YYYY-MM-DD."}) from exc
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
    completed = appearances.filter(task__status=Task.Status.DONE).count()

    def in_range(value):
        return start <= value <= end

    focus_by_day = defaultdict(int)
    deep_by_day = defaultdict(int)
    area_minutes = defaultdict(int)
    for session in sessions.select_related("area"):
        local_day = timezone.localtime(session.started_at, tz).date()
        if in_range(local_day):
            minutes = (session.duration_seconds or 0) // 60
            focus_by_day[str(local_day)] += minutes
            if session.is_deep_work:
                deep_by_day[str(local_day)] += minutes
            area_minutes[session.area_label_snapshot or session.area.name] += minutes
    planned_by_day = defaultdict(int)
    completed_by_day = defaultdict(int)
    for item in (
        DailyPlanItem.objects.filter(user=request.user)
        .exclude(state="removed")
        .select_related("plan", "task")
    ):
        if in_range(item.plan.local_date):
            key = str(item.plan.local_date)
            planned_by_day[key] += 1
            if item.task.status == Task.Status.DONE:
                completed_by_day[key] += 1
    sleep_by_day = defaultdict(float)
    for sleep in SleepLog.objects.filter(user=request.user):
        local_day = sleep.wake_local_date
        if in_range(local_day):
            sleep_by_day[str(local_day)] += (
                sleep.woke_at - sleep.started_at
            ).total_seconds() / 3600
    exercise_by_day = defaultdict(int)
    for exercise in ExerciseLog.objects.filter(user=request.user):
        local_day = timezone.localtime(exercise.started_at, tz).date()
        if in_range(local_day):
            exercise_by_day[str(local_day)] += int(
                (exercise.ended_at - exercise.started_at).total_seconds() // 60
            )
    roadmaps = []
    for roadmap in Roadmap.objects.filter(user=request.user).order_by("title"):
        progress = roadmap.progress()
        roadmaps.append({"id": str(roadmap.id), "title": roadmap.title, **progress})
    challenge = Challenge.objects.filter(
        user=request.user, is_primary=True, archived_at__isnull=True
    ).first()
    return Response(
        {
            "total_focused_minutes": total // 60,
            "deep_work_minutes": deep // 60,
            "planned_appearances": appearances.count(),
            "completed_planned_appearances": completed,
            "planned_completion_rate": completed / appearances.count()
            if appearances.count()
            else 0,
            "period": {"start": start, "end": end, "label": period},
            "challenge": challenge_summary(challenge, today) if challenge else None,
            "roadmaps": roadmaps,
            "focus_trend": [
                {
                    "date": str(start + timedelta(days=i)),
                    "minutes": focus_by_day.get(str(start + timedelta(days=i)), 0),
                }
                for i in range((end - start).days + 1)
            ],
            "deep_work_trend": [
                {
                    "date": str(start + timedelta(days=i)),
                    "minutes": deep_by_day.get(str(start + timedelta(days=i)), 0),
                }
                for i in range((end - start).days + 1)
            ],
            "planned_vs_completed": [
                {
                    "date": str(start + timedelta(days=i)),
                    "planned": planned_by_day.get(str(start + timedelta(days=i)), 0),
                    "completed": completed_by_day.get(
                        str(start + timedelta(days=i)), 0
                    ),
                }
                for i in range((end - start).days + 1)
            ],
            "area_distribution": [
                {"area": name, "minutes": minutes}
                for name, minutes in sorted(
                    area_minutes.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "exercise_trend": [
                {
                    "date": str(start + timedelta(days=i)),
                    "minutes": exercise_by_day.get(str(start + timedelta(days=i)), 0),
                }
                for i in range((end - start).days + 1)
            ],
            "sleep_trend": [
                {
                    "date": str(start + timedelta(days=i)),
                    "hours": round(
                        sleep_by_day.get(str(start + timedelta(days=i)), 0), 2
                    ),
                }
                for i in range((end - start).days + 1)
            ],
        }
    )
