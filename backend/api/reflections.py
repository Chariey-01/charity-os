"""API behaviour shared by daily reflections and weekly reviews (Phase 0C, S8)."""

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from reflections.services import EDITABLE, history, revise

from .exceptions import CodedAPIException


class ReflectionExists(CodedAPIException):
    status_code = 409
    default_code = "already_exists"

    def __init__(self, existing, key):
        super().__init__(
            "You already wrote this one. Open it and edit it instead; "
            "earlier wording is kept."
        )
        self.extra = {
            "existing_id": str(existing.pk),
            "fields": {key: ["You already wrote this one."]},
        }


class ReflectionMixin:
    """Creates are idempotent per period; edits go through reflections.revise.

    ``natural_key`` names the field that identifies the period (local_date or
    week_start_date). A repeated create with the same words returns the
    existing record (200); different words are a 409 "already_exists" with the
    existing id, never an overwrite.
    """

    natural_key = None

    def create(self, request, *args, **kwargs):
        value = request.data.get(self.natural_key)
        existing = (
            self.get_queryset().filter(**{self.natural_key: value}).first()
            if value
            else None
        )
        if existing is None:
            return super().create(request, *args, **kwargs)
        fields = self.get_serializer().fields
        same = all(
            fields[name].to_internal_value(request.data[name])
            == getattr(existing, name)
            for name in EDITABLE[type(existing)]
            if name in request.data and request.data[name] is not None
        )
        if same and existing.archived_at is None:
            return Response(self.get_serializer(existing).data)
        raise ReflectionExists(existing, self.natural_key)

    def update(self, request, *args, **kwargs):
        record = self.get_object()
        sent = {
            key: value
            for key, value in request.data.items()
            if key != "expected_version"
        }
        refused = sorted(set(sent) - set(EDITABLE[type(record)]))
        if refused:
            raise serializers.ValidationError(
                {field: ["This cannot be changed."] for field in refused}
            )
        serializer = self.get_serializer(record, data=sent, partial=True)
        serializer.is_valid(raise_exception=True)
        record = revise(
            user=request.user,
            record=record,
            expected_version=request.data.get("expected_version"),
            changes=serializer.validated_data,
        )
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        return Response(history(self.get_object()))
