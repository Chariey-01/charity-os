import uuid
from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError as DjangoValidationError
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
    update_session_details,
)
from health.models import (
    DailyNutritionRating,
    DailyWaterTotal,
    ExerciseLog,
    MealLog,
    SleepLog,
)
from planning.models import Area, DailyCapacity, DailyPlan, DailyPlanItem, Task
from planning.services import (
    add_node_to_today,
    add_plan_item,
    archive_task,
    carry_over,
    remove_plan_item,
    restore_task,
    transition_task,
)
from records.models import Accomplishment, Evidence
from reflections.models import DailyReflection, WeeklyReview
from roadmaps.models import (
    Roadmap,
    RoadmapNode,
    RoadmapNodePrerequisite,
    RoadmapResource,
)
from roadmaps.services import (
    ParentArchivedError,
    archive_node,
    next_actions,
    restore_node,
    roadmap_tree,
)
from scheduling.services import sync_entry_from_session

from . import serializers as s
from .archive import ArchivableMixin, NoDeleteMixin, ParentArchived

EDIT_INSTEAD = (
    "edit_instead",
    "Daily plans and capacities are kept as history; edit them instead.",
)


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
        # A savepoint, so a constraint race (answered 409) leaves the
        # connection usable.
        with transaction.atomic():
            serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()


def owned_viewset(name, model, serializer, *mixins):
    return type(
        name,
        (*mixins, OwnedViewSet),
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


class ChallengeViewSet(ArchivableMixin, OwnedViewSet):
    queryset = Challenge.objects.all()
    serializer_class = s.ChallengeSerializer
    # An archived challenge cannot be primary (database constraint). Its status
    # is left alone: archiving must not rewrite how the challenge ended.
    archive_also = {"is_primary": False}

    @action(detail=True, methods=["post"], url_path="set-primary")
    def set_primary(self, request, pk=None):
        challenge = self.get_object()
        if challenge.archived_at is not None:
            raise serializers.ValidationError(
                {"is_primary": ["Restore this challenge before making it primary."]}
            )
        Challenge.objects.filter(user=request.user, is_primary=True).update(
            is_primary=False
        )
        challenge.is_primary = True
        challenge.save(update_fields=("is_primary", "updated_at"))
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


class AreaViewSet(ArchivableMixin, OwnedViewSet):
    queryset = Area.objects.all()
    serializer_class = s.AreaSerializer

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by(
            "sort_order", "name"
        )


CapacityViewSet = owned_viewset(
    "CapacityViewSet", DailyCapacity, s.DailyCapacitySerializer, NoDeleteMixin
)


class CapacityViewSet(CapacityViewSet):
    delete_instead = EDIT_INSTEAD

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


DailyPlanViewSet = owned_viewset(
    "DailyPlanViewSet", DailyPlan, s.DailyPlanSerializer, NoDeleteMixin
)
RoadmapViewSet = owned_viewset(
    "RoadmapViewSet", Roadmap, s.RoadmapSerializer, ArchivableMixin
)


class RoadmapViewSet(RoadmapViewSet):
    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        return Response(self.get_object().progress())

    @action(detail=True, methods=["get"])
    def tree(self, request, pk=None):
        archived = request.query_params.get("archived", "exclude")
        if archived not in ("exclude", "include"):
            raise serializers.ValidationError({"archived": ["Use exclude or include."]})
        roadmap = self.get_object()
        return Response(
            {
                "roadmap": self.get_serializer(roadmap).data,
                "nodes": roadmap_tree(roadmap, include_archived=archived == "include"),
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
    delete_instead = EDIT_INSTEAD

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
            .filter(state=DailyPlanItem.State.CURRENT, task__archived_at__isnull=True)
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
                        user=request.user,
                        created_at__date=local_date,
                        archived_at__isnull=True,
                    ).order_by("-priority", "created_at"),
                    many=True,
                    context={"request": request},
                ).data,
            }
        )


class RoadmapNodeViewSet(ArchivableMixin, OwnedViewSet):
    queryset = RoadmapNode.objects.all()
    serializer_class = s.RoadmapNodeSerializer

    def archive_service(self, user, instance):
        return archive_node(user=user, node=instance)

    def restore_service(self, user, instance):
        try:
            return restore_node(user=user, node=instance)
        except ParentArchivedError as exc:
            raise ParentArchived() from exc

    @action(detail=True, methods=["post"], url_path="add-to-today")
    def add_to_today(self, request, pk=None):
        """Plan this item for today (optionally starting focus) atomically."""
        node = self.get_object()
        local_date = timezone.localtime(
            timezone.now(), ZoneInfo(request.user.timezone)
        ).date()
        focus = None
        if request.data.get("start_focus"):
            try:
                session_id = uuid.UUID(str(request.data.get("session_id", "")))
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"session_id": ["Send a client-generated session id."]}
                ) from exc
            area_id = request.data.get("area") or node.roadmap.area_id
            if not area_id:
                raise serializers.ValidationError(
                    {"area": ["Choose a category for the focus session."]}
                )
            try:
                area = Area.objects.get(pk=area_id, user=request.user)
            except (Area.DoesNotExist, ValueError, DjangoValidationError) as exc:
                raise serializers.ValidationError(
                    {"area": ["Choose one of your active categories."]}
                ) from exc
            focus = {"id": session_id, "area": area}
        result = add_node_to_today(
            user=request.user, node=node, local_date=local_date, focus=focus
        )
        context = {"request": request}
        return Response(
            {
                "task": s.TaskSerializer(result["task"], context=context).data,
                "plan_item": s.DailyPlanItemSerializer(
                    result["item"], context=context
                ).data,
                "session": s.FocusSessionSerializer(
                    result["session"], context=context
                ).data
                if result["session"]
                else None,
                "created_task": result["created_task"],
            }
        )


# Prerequisite links are pure structure with no history of their own, so they
# remain directly deletable (owner decision 4.2).
RoadmapPrerequisiteViewSet = owned_viewset(
    "RoadmapPrerequisiteViewSet",
    RoadmapNodePrerequisite,
    s.RoadmapPrerequisiteSerializer,
)
RoadmapResourceViewSet = owned_viewset(
    "RoadmapResourceViewSet",
    RoadmapResource,
    s.RoadmapResourceSerializer,
    ArchivableMixin,
)
EvidenceViewSet = owned_viewset(
    "EvidenceViewSet", Evidence, s.EvidenceSerializer, ArchivableMixin
)
AccomplishmentViewSet = owned_viewset(
    "AccomplishmentViewSet",
    Accomplishment,
    s.AccomplishmentSerializer,
    ArchivableMixin,
)
SleepLogViewSet = owned_viewset(
    "SleepLogViewSet", SleepLog, s.SleepLogSerializer, ArchivableMixin
)
ExerciseLogViewSet = owned_viewset(
    "ExerciseLogViewSet", ExerciseLog, s.ExerciseLogSerializer, ArchivableMixin
)
MealLogViewSet = owned_viewset(
    "MealLogViewSet", MealLog, s.MealLogSerializer, ArchivableMixin
)


class DailyTotalMixin:
    """A daily total is the value for its day: saving it again updates it.

    The app saves today's water and nutrition rating on every change, so a
    second save is an update, not a duplicate (Phase 0B, B3).
    """

    def create(self, request, *args, **kwargs):
        local_date = request.data.get("local_date")
        with transaction.atomic():
            existing = (
                self.get_queryset()
                .select_for_update()
                .filter(local_date=local_date)
                .first()
                if local_date
                else None
            )
            if existing is None:
                return super().create(request, *args, **kwargs)
            if existing.archived_at is not None:
                raise serializers.ValidationError(
                    {"local_date": ["This day's entry is archived. Restore it first."]}
                )
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(serializer.data)


WaterViewSet = owned_viewset(
    "WaterViewSet", DailyWaterTotal, s.WaterSerializer, DailyTotalMixin, ArchivableMixin
)
NutritionViewSet = owned_viewset(
    "NutritionViewSet",
    DailyNutritionRating,
    s.NutritionSerializer,
    DailyTotalMixin,
    ArchivableMixin,
)
DailyReflectionViewSet = owned_viewset(
    "DailyReflectionViewSet",
    DailyReflection,
    s.DailyReflectionSerializer,
    ArchivableMixin,
)
WeeklyReviewViewSet = owned_viewset(
    "WeeklyReviewViewSet", WeeklyReview, s.WeeklyReviewSerializer, ArchivableMixin
)


class TaskViewSet(ArchivableMixin, OwnedViewSet):
    queryset = Task.objects.all()
    serializer_class = s.TaskSerializer

    def archive_service(self, user, instance):
        return archive_task(user=user, task=instance)

    def restore_service(self, user, instance):
        return restore_task(user=user, task=instance)

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


class PlanItemViewSet(NoDeleteMixin, OwnedViewSet):
    queryset = DailyPlanItem.objects.all()
    serializer_class = s.DailyPlanItemSerializer
    delete_instead = (
        "remove_instead",
        "Plan items are kept as history. "
        "Use POST /api/v1/daily-plan-items/<id>/remove.",
    )

    @action(detail=True, methods=["post"])
    def remove(self, request, pk=None):
        item = remove_plan_item(
            user=request.user,
            item=self.get_object(),
            reason=str(request.data.get("reason", "") or ""),
        )
        return Response(self.get_serializer(item).data)

    def perform_create(self, serializer):
        data = serializer.validated_data
        self.instance = add_plan_item(
            user=self.request.user,
            plan=data["plan"],
            task=data["task"],
            kind=data.get("kind", "secondary"),
            position=data.get("position"),
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

    def partial_update(self, request, pk=None):
        changes = {
            key: value
            for key, value in request.data.items()
            if key != "expected_version"
        }
        session = update_session_details(
            user=request.user,
            session_id=self.get_object().pk,
            expected_version=request.data.get("expected_version"),
            changes=changes,
        )
        return Response(self.get_serializer(session).data)

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
        """Correct times and/or attribution of an ended session (audited)."""
        from rest_framework.fields import DateTimeField

        data = request.data
        times = {}
        for name in ("started_at", "ended_at"):
            if data.get(name):
                try:
                    times[name] = DateTimeField().to_internal_value(data[name])
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({name: exc.detail}) from exc
        attribution = {}
        for name, model in (
            ("area", Area),
            ("task", Task),
            ("roadmap_item", RoadmapNode),
        ):
            if name not in data:
                continue
            if data[name] in (None, ""):
                attribution[name] = None
                continue
            try:
                attribution[name] = model.objects.get(pk=data[name], user=request.user)
            except (model.DoesNotExist, ValueError, DjangoValidationError) as exc:
                raise serializers.ValidationError(
                    {name: ["Choose one of your own records."]}
                ) from exc
        if "is_deep_work" in data:
            if not isinstance(data["is_deep_work"], bool):
                raise serializers.ValidationError(
                    {"is_deep_work": ["Send true or false."]}
                )
            attribution["is_deep_work"] = data["is_deep_work"]
        obj = correct_session(
            user=request.user,
            session_id=self.get_object().pk,
            reason=str(data.get("reason", "") or ""),
            expected_version=data.get("expected_version"),
            **times,
            **attribution,
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
    for roadmap in Roadmap.objects.filter(
        user=request.user, archived_at__isnull=True
    ).order_by("title"):
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
