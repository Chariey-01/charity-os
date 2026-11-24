"""Schedule, Today, insights and preference endpoints."""

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.fields import DateTimeField
from rest_framework.response import Response

from execution.models import FocusSession
from planning.categories import active_categories, ensure_default_categories
from planning.models import Area, DailyCapacity, DailyPlanItem, Task
from roadmaps.models import RoadmapNode
from scheduling import insights as insight_service
from scheduling import services
from scheduling.models import ScheduleEntry
from users.models import UserPreferences

Status = ScheduleEntry.Status


# --------------------------------------------------------------------------
# Serialisation


def _local_iso(instant, zone):
    return timezone.localtime(instant, zone).strftime("%Y-%m-%dT%H:%M")


def serialize_entry(entry, now=None):
    zone = ZoneInfo(entry.timezone_name)
    session = entry.focus_session if entry.focus_session_id else None
    rescheduled_to = getattr(entry, "rescheduled_to", None)
    actual_seconds = entry.actual_seconds(at=now)
    return {
        "id": str(entry.id),
        "title": entry.title,
        "description": entry.description,
        "notes": entry.notes,
        "outcome": entry.outcome,
        "area": str(entry.area_id) if entry.area_id else None,
        "area_label": entry.area.name if entry.area else entry.area_label_snapshot,
        "color": entry.area.color if entry.area else "#64748B",
        "health_kind": entry.area.health_kind if entry.area else "",
        "start_at": entry.start_at,
        "end_at": entry.end_at,
        "start_local": _local_iso(entry.start_at, zone),
        "end_local": _local_iso(entry.end_at, zone),
        "timezone_name": entry.timezone_name,
        "local_date": entry.local_date,
        "planned_minutes": round(entry.planned_seconds / 60),
        "status": entry.status,
        "tracking": entry.tracking,
        "task": str(entry.task_id) if entry.task_id else None,
        "task_title": entry.task.title if entry.task_id else "",
        "task_status": entry.task.status if entry.task_id else None,
        "roadmap_node": str(entry.roadmap_node_id) if entry.roadmap_node_id else None,
        "roadmap_node_title": entry.roadmap_node.title if entry.roadmap_node_id else "",
        "focus_session": str(session.id) if session else None,
        "focus_session_status": session.status if session else None,
        "focus_session_version": session.version if session else None,
        "actual_started_at": session.started_at if session else entry.actual_started_at,
        "actual_ended_at": session.ended_at if session else entry.actual_ended_at,
        "actual_seconds": actual_seconds,
        "actual_minutes": None
        if actual_seconds is None
        else round(actual_seconds / 60),
        "paused_at": entry.paused_at,
        "closed_at": entry.closed_at,
        "rescheduled_from": str(entry.rescheduled_from_id)
        if entry.rescheduled_from_id
        else None,
        "rescheduled_to": str(rescheduled_to.id) if rescheduled_to else None,
        "version": entry.version,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def entry_queryset(user):
    return (
        ScheduleEntry.objects.filter(user=user)
        .select_related(
            "area", "task", "roadmap_node", "focus_session", "rescheduled_to"
        )
        .prefetch_related("focus_session__pauses")
    )


class LocalDateTimeField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise serializers.ValidationError("Use YYYY-MM-DDTHH:MM.") from error
        if parsed.tzinfo is not None:
            raise serializers.ValidationError(
                "Send a local wall-clock time without an offset."
            )
        return parsed


class EntryInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    outcome = serializers.CharField(required=False, allow_blank=True)
    area = serializers.UUIDField(required=False, allow_null=True)
    task = serializers.UUIDField(required=False, allow_null=True)
    roadmap_node = serializers.UUIDField(required=False, allow_null=True)
    tracking = serializers.ChoiceField(
        choices=ScheduleEntry.Tracking.choices, required=False
    )
    start_local = LocalDateTimeField(required=False)
    end_local = LocalDateTimeField(required=False)
    timezone_name = serializers.CharField(max_length=64, required=False)
    allow_overlap = serializers.BooleanField(required=False, default=False)
    expected_version = serializers.IntegerField(required=False, min_value=1)


def _owned(model, user, pk, field):
    if pk is None:
        return None
    obj = model.objects.filter(pk=pk, user=user).first()
    if obj is None:
        raise serializers.ValidationError({field: "Choose one of your own records."})
    return obj


RELATED = {"area": Area, "task": Task, "roadmap_node": RoadmapNode}


def _resolve_related(user, data):
    return {
        field: _owned(model, user, data[field], field)
        for field, model in RELATED.items()
        if field in data
    }


def _bool(value):
    return value in (True, "true", "True", "1", 1)


def _instant(value, field):
    if value in (None, ""):
        return None
    try:
        return DateTimeField().to_internal_value(value)
    except serializers.ValidationError as error:
        raise serializers.ValidationError(
            {field: "Use an ISO 8601 timestamp."}
        ) from error


# --------------------------------------------------------------------------
# Schedule entries


def parse_day(value, field="date"):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise serializers.ValidationError({field: "Use YYYY-MM-DD."}) from error


def entries_between(user, start, end, include_all=False):
    """Entries overlapping local dates ``start``..``end`` in the user's zone."""
    zone = ZoneInfo(user.timezone)
    lower, upper = insight_service.local_bounds(start, end, zone)
    queryset = entry_queryset(user).filter(start_at__lt=upper, end_at__gt=lower)
    if not include_all:
        queryset = queryset.exclude(status=Status.RESCHEDULED)
    return queryset.order_by("start_at", "created_at")


class ScheduleEntryViewSet(viewsets.ViewSet):
    """Owner-scoped schedule entries. Cancel instead of delete."""

    def list(self, request):
        today = insight_service.user_today(request.user)
        start = parse_day(request.query_params.get("start", str(today)), "start")
        end = parse_day(request.query_params.get("end", str(start)), "end")
        if end < start:
            raise serializers.ValidationError({"end": "End must not precede start."})
        if (end - start).days > 92:
            raise serializers.ValidationError({"end": "Request at most 93 days."})
        include_all = request.query_params.get("include") == "all"
        now = timezone.now()
        return Response(
            [
                serialize_entry(entry, now)
                for entry in entries_between(request.user, start, end, include_all)
            ]
        )

    def retrieve(self, request, pk=None):
        return Response(serialize_entry(entry_queryset(request.user).get(pk=pk)))

    def create(self, request):
        serializer = EntryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        missing = [
            field
            for field in ("title", "start_local", "end_local")
            if not data.get(field)
        ]
        if missing:
            raise serializers.ValidationError(
                {field: "This field is required." for field in missing}
            )
        tz_name = data.get("timezone_name") or request.user.timezone
        related = _resolve_related(request.user, data)
        entry = services.create_entry(
            user=request.user,
            entry_id=data.get("id"),
            title=data["title"],
            description=data.get("description", ""),
            notes=data.get("notes", ""),
            tracking=data.get("tracking", ScheduleEntry.Tracking.MANUAL),
            start_at=services.resolve_local(
                data["start_local"], tz_name, "start_local"
            ),
            end_at=services.resolve_local(data["end_local"], tz_name, "end_local"),
            timezone_name=tz_name,
            allow_overlap=data.get("allow_overlap", False),
            **related,
        )
        replayed = getattr(entry, "_replayed", False)
        return Response(
            serialize_entry(entry_queryset(request.user).get(pk=entry.pk)),
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    def partial_update(self, request, pk=None):
        serializer = EntryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        current = entry_queryset(request.user).get(pk=pk)
        changes = {
            field: data[field]
            for field in ("title", "description", "notes", "outcome", "tracking")
            if field in data
        }
        changes.update(_resolve_related(request.user, data))
        if {"start_local", "end_local", "timezone_name"} & data.keys():
            old_zone = ZoneInfo(current.timezone_name)
            tz_name = data.get("timezone_name") or current.timezone_name
            start_local = data.get("start_local") or timezone.localtime(
                current.start_at, old_zone
            ).replace(tzinfo=None)
            if "end_local" in data:
                end_local = data["end_local"]
            elif "start_local" in data:
                # Moving the start keeps the planned duration.
                end_local = None
            else:
                end_local = timezone.localtime(current.end_at, old_zone).replace(
                    tzinfo=None
                )
            start_at = services.resolve_local(start_local, tz_name, "start_local")
            end_at = (
                services.resolve_local(end_local, tz_name, "end_local")
                if end_local is not None
                else start_at + (current.end_at - current.start_at)
            )
            changes.update(start_at=start_at, end_at=end_at, timezone_name=tz_name)
        services.update_entry(
            user=request.user,
            entry_id=pk,
            changes=changes,
            expected_version=data.get("expected_version"),
            allow_overlap=data.get("allow_overlap", False),
        )
        return Response(serialize_entry(entry_queryset(request.user).get(pk=pk)))

    def _respond(self, request, entry):
        return Response(serialize_entry(entry_queryset(request.user).get(pk=entry.pk)))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        session_id = request.data.get("session_id")
        try:
            session_id = uuid.UUID(str(session_id)) if session_id else None
        except ValueError as error:
            raise serializers.ValidationError({"session_id": "Use a UUID."}) from error
        entry = services.start_entry(
            user=request.user,
            entry_id=pk,
            expected_version=request.data.get("expected_version"),
            session_id=session_id,
        )
        return self._respond(request, entry)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        pause_id = request.data.get("pause_id")
        try:
            pause_id = uuid.UUID(str(pause_id)) if pause_id else None
        except ValueError as error:
            raise serializers.ValidationError({"pause_id": "Use a UUID."}) from error
        entry = services.pause_entry(
            user=request.user,
            entry_id=pk,
            expected_version=request.data.get("expected_version"),
            pause_id=pause_id,
        )
        return self._respond(request, entry)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        entry = services.resume_entry(
            user=request.user,
            entry_id=pk,
            expected_version=request.data.get("expected_version"),
        )
        return self._respond(request, entry)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        data = request.data
        minutes = data.get("actual_minutes")
        if minutes not in (None, ""):
            try:
                minutes = int(minutes)
            except (TypeError, ValueError) as error:
                raise serializers.ValidationError(
                    {"actual_minutes": "Use whole minutes."}
                ) from error
        else:
            minutes = None
        entry = services.complete_entry(
            user=request.user,
            entry_id=pk,
            partial=_bool(data.get("partial", False)),
            outcome=data.get("outcome", "") or "",
            learning=data.get("learning", "") or "",
            notes=data.get("notes"),
            actual_minutes=minutes,
            actual_started_at=_instant(
                data.get("actual_started_at"), "actual_started_at"
            ),
            actual_ended_at=_instant(data.get("actual_ended_at"), "actual_ended_at"),
            complete_task=_bool(data.get("complete_task", False)),
            expected_version=data.get("expected_version"),
        )
        return self._respond(request, entry)

    @action(detail=True, methods=["post"])
    def skip(self, request, pk=None):
        entry = services.skip_entry(
            user=request.user,
            entry_id=pk,
            note=request.data.get("note", "") or "",
            expected_version=request.data.get("expected_version"),
        )
        return self._respond(request, entry)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        entry = services.cancel_entry(
            user=request.user,
            entry_id=pk,
            note=request.data.get("note", "") or "",
            expected_version=request.data.get("expected_version"),
        )
        return self._respond(request, entry)

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        serializer = EntryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("start_local") or not data.get("end_local"):
            raise serializers.ValidationError(
                {"start_local": "Choose the new start and end."}
            )
        original = entry_queryset(request.user).get(pk=pk)
        tz_name = data.get("timezone_name") or original.timezone_name
        replacement = services.reschedule_entry(
            user=request.user,
            entry_id=pk,
            start_at=services.resolve_local(
                data["start_local"], tz_name, "start_local"
            ),
            end_at=services.resolve_local(data["end_local"], tz_name, "end_local"),
            timezone_name=tz_name,
            new_entry_id=data.get("id"),
            allow_overlap=data.get("allow_overlap", False),
            expected_version=data.get("expected_version"),
        )
        return Response(
            {
                "original": serialize_entry(entry_queryset(request.user).get(pk=pk)),
                "entry": serialize_entry(
                    entry_queryset(request.user).get(pk=replacement.pk)
                ),
            }
        )


# --------------------------------------------------------------------------
# Today


def _unscheduled_tasks(user, local_date):
    open_entry_tasks = ScheduleEntry.objects.filter(
        user=user, status__in=ScheduleEntry.OPEN_STATUSES, task__isnull=False
    ).values("task_id")
    today_items = DailyPlanItem.objects.filter(
        user=user,
        plan__local_date=local_date,
        state=DailyPlanItem.State.CURRENT,
    )
    kinds = {item.task_id: item.kind for item in today_items}
    tasks = (
        Task.objects.filter(
            user=user, status__in=Task.OPEN_STATUSES, archived_at__isnull=True
        )
        .exclude(pk__in=open_entry_tasks)
        .select_related("area")
        .annotate(
            on_plan=Case(
                When(pk__in=list(kinds), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("on_plan", "-priority", "-created_at")[:15]
    )
    return [
        {
            "id": str(task.id),
            "title": task.title,
            "area": str(task.area_id) if task.area_id else None,
            "area_label": task.area.name if task.area else "",
            "color": task.area.color if task.area else "#64748B",
            "estimated_minutes": task.estimated_minutes,
            "roadmap_item": str(task.roadmap_item_id) if task.roadmap_item_id else None,
            "plan_kind": kinds.get(task.id),
            "is_deep_work_default": task.is_deep_work_default,
        }
        for task in tasks
    ]


@api_view(["GET"])
def schedule_day(request):
    user = request.user
    today = insight_service.user_today(user)
    local_date = parse_day(request.query_params.get("date", str(today)))
    now = timezone.now()
    entries = list(entries_between(user, local_date, local_date))
    own_day = [
        entry
        for entry in entries
        if entry.local_date == local_date and entry.status != Status.CANCELLED
    ]
    progress = {
        "planned": len(own_day),
        "completed": sum(entry.status == Status.COMPLETED for entry in own_day),
        "partially_completed": sum(
            entry.status == Status.PARTIALLY_COMPLETED for entry in own_day
        ),
        "skipped": sum(entry.status == Status.SKIPPED for entry in own_day),
        "in_progress": sum(
            entry.status in ScheduleEntry.RUNNING_STATUSES for entry in own_day
        ),
        "remaining": sum(entry.status == Status.SCHEDULED for entry in own_day),
        "planned_minutes": round(sum(entry.planned_seconds for entry in own_day) / 60),
        "actual_minutes": round(
            sum(
                entry.actual_seconds(at=now) or 0
                for entry in own_day
                if entry.status != Status.SKIPPED
            )
            / 60
        ),
    }
    capacity = DailyCapacity.objects.filter(user=user, local_date=local_date).first()
    scheduled_minutes = round(
        sum(
            entry.planned_seconds
            for entry in own_day
            if entry.status != Status.SKIPPED
            and not (entry.area and entry.area.health_kind == "sleep")
        )
        / 60
    )
    available = capacity.available_minutes if capacity else None
    challenge = insight_service.primary_challenge(user)
    active = (
        FocusSession.objects.filter(user=user, status__in=("active", "paused"))
        .select_related("schedule_entry")
        .first()
    )
    preferences, _ = UserPreferences.objects.get_or_create(user=user)
    return Response(
        {
            "date": local_date,
            "today": today,
            "timezone": user.timezone,
            "challenge": insight_service.challenge_progress(
                user, challenge, local_date, ZoneInfo(user.timezone)
            )
            if challenge
            else None,
            "entries": [serialize_entry(entry, now) for entry in entries],
            "progress": progress,
            "capacity": {
                "available_minutes": available,
                "deep_work_minutes": capacity.deep_work_minutes if capacity else None,
                "scheduled_minutes": scheduled_minutes,
                "remaining_minutes": None
                if available is None
                else available - scheduled_minutes,
            },
            "unscheduled_tasks": _unscheduled_tasks(user, local_date),
            "active_session_entry": str(active.schedule_entry.id)
            if active and getattr(active, "schedule_entry", None)
            else None,
            "week": insight_service.week_summary(
                user, today, show_streaks=preferences.show_streaks
            ),
        }
    )


# --------------------------------------------------------------------------
# Insights, preferences, categories


@api_view(["GET"])
def insights(request):
    period = request.query_params.get("period", "30d")
    if period not in insight_service.PERIODS:
        raise serializers.ValidationError(
            {"period": f"Use one of {', '.join(insight_service.PERIODS)}."}
        )
    preferences, _ = UserPreferences.objects.get_or_create(user=request.user)
    data = insight_service.build_insights(request.user, period)
    data["week"] = insight_service.week_summary(
        request.user, show_streaks=preferences.show_streaks
    )
    return Response(data)


class PreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        exclude = ("user",)
        read_only_fields = ("updated_at",)


@api_view(["GET", "PATCH"])
def preferences(request):
    instance, _ = UserPreferences.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        serializer = PreferencesSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        return Response(serializer.data)
    return Response(PreferencesSerializer(instance).data)


@api_view(["POST"])
def ensure_categories(request):
    created = ensure_default_categories(request.user)
    rows = active_categories(request.user)
    return Response(
        {
            "created": len(created),
            "areas": [
                {
                    "id": str(area.id),
                    "name": area.name,
                    "slug": area.slug,
                    "color": area.color,
                    "health_kind": area.health_kind,
                    "sort_order": area.sort_order,
                    "archived_at": area.archived_at,
                }
                for area in rows
            ],
        }
    )
