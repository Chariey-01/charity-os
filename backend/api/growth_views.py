from datetime import date
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from growth import services
from growth.direction import direction
from growth.journey import journey, year_end_candidates
from growth.models import (
    ActivityEvent,
    Goal,
    JournalEntry,
    Milestone,
    Project,
    VisionItem,
)
from planning.models import Area, PlanningEvent
from roadmaps.models import Roadmap
from roadmaps.templates import TEMPLATES, catalog, create_from_template

from . import growth_serializers as gs
from . import serializers as s
from .archive import ArchivableMixin
from .views import OwnedViewSet


def local_today(user):
    return timezone.localtime(timezone.now(), ZoneInfo(user.timezone)).date()


def _date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise serializers.ValidationError({field: ["Use YYYY-MM-DD."]}) from exc


class TodayContextMixin:
    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            context["today"] = local_today(self.request.user)
        return context


class VisionViewSet(TodayContextMixin, ArchivableMixin, OwnedViewSet):
    queryset = VisionItem.objects.all()
    serializer_class = gs.VisionItemSerializer

    def get_queryset(self):
        queryset = (
            self.queryset.filter(user=self.request.user)
            .prefetch_related("goals")
            .order_by("position", "created_at")
        )
        kind = self.request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(kind=kind)
        return queryset

    def perform_update(self, serializer):
        serializer.instance = services.revise_vision(
            user=self.request.user,
            vision=serializer.instance,
            changes=serializer.validated_data,
        )

    @action(detail=True, methods=["post"])
    def realise(self, request, pk=None):
        vision = services.realise_vision(
            user=request.user,
            vision=self.get_object(),
            note=str(request.data.get("note", "")),
            evidence_url=str(request.data.get("evidence_url", "")),
            confirm=request.data.get("confirm") is True,
        )
        return Response(self.get_serializer(vision).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        vision = services.set_vision_status(
            user=request.user,
            vision=self.get_object(),
            status=str(request.data.get("status", "")),
        )
        return Response(self.get_serializer(vision).data)

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        vision = self.get_object()
        return Response(
            gs.VisionRevisionSerializer(
                vision.revisions.order_by("-version"), many=True
            ).data
        )


def _goal_queryset(user):
    return (
        Goal.objects.filter(user=user)
        .select_related("vision", "area")
        .prefetch_related("milestones", "tasks", "checkins")
    )


class GoalViewSet(TodayContextMixin, ArchivableMixin, OwnedViewSet):
    queryset = Goal.objects.all()
    serializer_class = gs.GoalSerializer

    def get_queryset(self):
        queryset = _goal_queryset(self.request.user).order_by(
            "status", "target_date", "created_at"
        )
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("vision"):
            queryset = queryset.filter(vision_id=params["vision"])
        return queryset

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        goal = services.set_goal_status(
            user=request.user,
            goal=self.get_object(),
            status=str(request.data.get("status", "")),
            note=str(request.data.get("note", "")),
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=goal.pk)).data)

    @action(detail=True, methods=["get", "post"])
    def checkins(self, request, pk=None):
        goal = self.get_object()
        if request.method == "POST":
            raw = request.data.get("value")
            value = None
            if raw not in (None, ""):
                field = serializers.DecimalField(max_digits=14, decimal_places=2)
                value = field.run_validation(raw)
            services.check_in(
                user=request.user,
                goal=goal,
                local_date=_date(request.data.get("local_date"), "local_date")
                or local_today(request.user),
                value=value,
                note=str(request.data.get("note", "")),
            )
        return Response(
            gs.GoalCheckInSerializer(
                goal.checkins.order_by("-local_date", "-created_at"), many=True
            ).data,
            status=201 if request.method == "POST" else 200,
        )

    @action(detail=True, methods=["post"], url_path="carry-forward")
    def carry_forward(self, request, pk=None):
        target = _date(request.data.get("target_date"), "target_date")
        if target is None:
            raise serializers.ValidationError({"target_date": ["Choose a new target date."]})
        goal = services.carry_forward_goal(
            user=request.user,
            goal=self.get_object(),
            target_date=target,
            note=str(request.data.get("note", "")),
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=goal.pk)).data)

    @action(detail=True, methods=["get"])
    def overview(self, request, pk=None):
        goal = self.get_object()
        context = self.get_serializer_context()
        return Response(
            {
                "goal": self.get_serializer(goal).data,
                "milestones": gs.MilestoneSerializer(
                    goal.milestones.filter(archived_at__isnull=True)
                    .prefetch_related("tasks")
                    .order_by("position", "target_date", "created_at"),
                    many=True,
                    context=context,
                ).data,
                "tasks": s.TaskSerializer(
                    goal.tasks.filter(archived_at__isnull=True).order_by(
                        "status", "due_date", "-priority"
                    ),
                    many=True,
                    context=context,
                ).data,
                "roadmaps": s.RoadmapSerializer(
                    goal.roadmaps.filter(archived_at__isnull=True),
                    many=True,
                    context=context,
                ).data,
                "projects": gs.ProjectSerializer(
                    goal.projects.filter(archived_at__isnull=True).prefetch_related(
                        "tasks", "milestones"
                    ),
                    many=True,
                    context=context,
                ).data,
                "checkins": gs.GoalCheckInSerializer(
                    goal.checkins.order_by("-local_date", "-created_at")[:50], many=True
                ).data,
                "history": gs.ActivityEventSerializer(
                    ActivityEvent.objects.filter(
                        user=request.user, subject_type="goal", subject_id=goal.pk
                    ).order_by("-occurred_at")[:50],
                    many=True,
                ).data,
            }
        )


class MilestoneViewSet(TodayContextMixin, ArchivableMixin, OwnedViewSet):
    queryset = Milestone.objects.all()
    serializer_class = gs.MilestoneSerializer

    def get_queryset(self):
        queryset = (
            self.queryset.filter(user=self.request.user)
            .select_related("goal", "project")
            .prefetch_related("tasks")
            .order_by("position", "target_date", "created_at")
        )
        params = self.request.query_params
        if params.get("goal"):
            queryset = queryset.filter(goal_id=params["goal"])
        if params.get("project"):
            queryset = queryset.filter(project_id=params["project"])
        return queryset

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        milestone = services.set_milestone_status(
            user=request.user,
            milestone=self.get_object(),
            status=str(request.data.get("status", "")),
            note=str(request.data.get("note", "")),
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=milestone.pk)).data)


class ProjectViewSet(TodayContextMixin, ArchivableMixin, OwnedViewSet):
    queryset = Project.objects.all()
    serializer_class = gs.ProjectSerializer

    def get_queryset(self):
        queryset = (
            self.queryset.filter(user=self.request.user)
            .select_related("goal", "area")
            .prefetch_related("tasks", "milestones")
            .order_by("-priority", "deadline", "name")
        )
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        project = services.set_project_status(
            user=request.user,
            project=self.get_object(),
            status=str(request.data.get("status", "")),
            note=str(request.data.get("note", "")),
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=project.pk)).data)

    @action(detail=True, methods=["get"])
    def overview(self, request, pk=None):
        project = self.get_object()
        context = self.get_serializer_context()
        include_archived = request.query_params.get("archived") == "include"
        tasks = project.tasks.select_related("area").order_by("-priority", "due_date", "created_at")
        if not include_archived:
            tasks = tasks.filter(archived_at__isnull=True)
        task_events = (
            PlanningEvent.objects.filter(user=request.user, task__project=project)
            .exclude(event_type="due_changed")
            .order_by("-created_at")[:40]
        )
        project_events = ActivityEvent.objects.filter(
            user=request.user, subject_type="project", subject_id=project.pk
        ).order_by("-occurred_at")[:40]
        activity = [
            {
                "id": str(event.pk),
                "kind": event.event_type,
                "title": (event.snapshot or {}).get("title", ""),
                "detail": {k: v for k, v in (event.snapshot or {}).items() if k in ("from", "to")},
                "occurred_at": event.created_at.isoformat(),
                "source": "task",
            }
            for event in task_events
        ] + [
            {
                "id": str(event.pk),
                "kind": event.kind,
                "title": event.title,
                "detail": {k: v for k, v in event.data.items() if k in ("from", "to", "note")},
                "occurred_at": event.occurred_at.isoformat(),
                "source": "project",
            }
            for event in project_events
        ]
        activity.sort(key=lambda row: row["occurred_at"], reverse=True)
        return Response(
            {
                "project": self.get_serializer(project).data,
                "tasks": s.TaskSerializer(tasks, many=True, context=context).data,
                "milestones": gs.MilestoneSerializer(
                    project.milestones.filter(archived_at__isnull=True)
                    .prefetch_related("tasks")
                    .order_by("position", "target_date", "created_at"),
                    many=True,
                    context=context,
                ).data,
                "activity": activity[:50],
            }
        )


class JournalViewSet(ArchivableMixin, OwnedViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = gs.JournalEntrySerializer

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by(
            "-local_date", "-created_at"
        )

    def perform_update(self, serializer):
        serializer.instance = services.edit_journal_entry(
            user=self.request.user,
            entry=serializer.instance,
            changes=serializer.validated_data,
        )


class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = gs.ActivityEventSerializer

    def get_queryset(self):
        queryset = ActivityEvent.objects.filter(user=self.request.user).order_by(
            "-occurred_at"
        )
        params = self.request.query_params
        if params.get("subject_type"):
            queryset = queryset.filter(subject_type=params["subject_type"])
        if params.get("subject_id"):
            queryset = queryset.filter(subject_id=params["subject_id"])
        return queryset[:200]


@api_view(["GET"])
def journey_view(request):
    raw = request.query_params.get("year")
    try:
        year = int(raw) if raw else local_today(request.user).year
    except ValueError as exc:
        raise serializers.ValidationError({"year": ["Use a year such as 2026."]}) from exc
    if not 1900 <= year <= 2200:
        raise serializers.ValidationError({"year": ["Use a year such as 2026."]})
    return Response(journey(request.user, year))


@api_view(["GET"])
def direction_view(request):
    return Response(direction(request.user, local_today(request.user)))


@api_view(["GET"])
def year_end_view(request):
    raw = request.query_params.get("year")
    try:
        year = int(raw) if raw else local_today(request.user).year
    except ValueError as exc:
        raise serializers.ValidationError({"year": ["Use a year such as 2026."]}) from exc
    goals = year_end_candidates(request.user, year).prefetch_related(
        "milestones", "tasks", "checkins"
    )
    context = {"request": request, "today": local_today(request.user)}
    return Response(
        {"year": year, "goals": gs.GoalSerializer(goals, many=True, context=context).data}
    )


@api_view(["GET"])
def roadmap_templates(request):
    return Response(catalog())


@api_view(["POST"])
def roadmap_from_template(request):
    key = str(request.data.get("template", ""))
    if key not in TEMPLATES:
        raise serializers.ValidationError({"template": ["Choose one of the templates."]})

    def owned(model, field):
        value = request.data.get(field)
        if not value:
            return None
        try:
            return model.objects.get(pk=value, user=request.user)
        except (model.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise serializers.ValidationError({field: ["Choose one of your own."]}) from exc

    roadmap = create_from_template(
        user=request.user,
        key=key,
        title=str(request.data.get("title") or "") or None,
        area=owned(Area, "area"),
        goal=owned(Goal, "goal"),
    )
    return Response(
        s.RoadmapSerializer(Roadmap.objects.get(pk=roadmap.pk), context={"request": request}).data,
        status=201,
    )


GROWTH_ROUTES = (
    ("vision", VisionViewSet),
    ("goals", GoalViewSet),
    ("milestones", MilestoneViewSet),
    ("projects", ProjectViewSet),
    ("journal", JournalViewSet),
)

