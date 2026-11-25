"""Archive instead of delete (owner decisions 4.1 and 4.2).

Records that carry history are never deleted through the API. DELETE is not
an allowed method on them: it answers 405 with a stable error code that says
what to do instead (see api/exceptions.py). Archiving hides a record from
working lists; every relationship, every piece of evidence and all tracked
time stay where they are, and the record can be restored.

List endpoints accept ``?archived=exclude|include|only`` (default
``exclude``). Detail endpoints always return the record, archived or not.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from .exceptions import CodedAPIException

ARCHIVED_FILTER_VALUES = ("exclude", "include", "only")


class RestoreConflict(CodedAPIException):
    status_code = 409
    default_code = "restore_conflict"
    default_detail = (
        "This record cannot be restored while an active record uses the same name."
    )


class ParentArchived(CodedAPIException):
    status_code = 409
    default_code = "parent_archived"
    default_detail = "Restore the parent first; this record is archived under it."


def filter_archived(queryset, value, field="archived_at"):
    value = value or "exclude"
    if value not in ARCHIVED_FILTER_VALUES:
        raise serializers.ValidationError(
            {"archived": [f"Use one of: {', '.join(ARCHIVED_FILTER_VALUES)}."]}
        )
    if value == "exclude":
        return queryset.filter(**{f"{field}__isnull": True})
    if value == "only":
        return queryset.filter(**{f"{field}__isnull": False})
    return queryset


def _update_fields(obj, *names):
    fields = list(names)
    if any(field.name == "updated_at" for field in obj._meta.concrete_fields):
        fields.append("updated_at")
    return fields


@transaction.atomic
def archive_record(*, user, instance, also=None):
    """Set archived_at (and any ``also`` fields) once. Idempotent."""
    obj = type(instance).objects.select_for_update().get(pk=instance.pk, user=user)
    if obj.archived_at is None:
        obj.archived_at = timezone.now()
        for field, value in (also or {}).items():
            setattr(obj, field, value)
        obj.save(update_fields=_update_fields(obj, "archived_at", *(also or {})))
    return obj


@transaction.atomic
def restore_record(*, user, instance):
    """Clear archived_at. Idempotent; 409 if an active record now holds its name."""
    obj = type(instance).objects.select_for_update().get(pk=instance.pk, user=user)
    if obj.archived_at is not None:
        obj.archived_at = None
        try:
            with transaction.atomic():
                obj.save(update_fields=_update_fields(obj, "archived_at"))
        except IntegrityError as exc:
            raise RestoreConflict() from exc
    return obj


class NoDeleteMixin:
    """Leave DELETE out of the allowed methods and explain what to do instead.

    ``delete_instead`` is (error code, message); api/exceptions.py turns the
    resulting MethodNotAllowed into a 405 carrying them.
    """

    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    delete_instead = (
        "archive_instead",
        "Records with history are archived, not deleted. "
        "Use POST /api/v1/<resource>/<id>/archive.",
    )


class ArchivableMixin(NoDeleteMixin):
    """Archive/restore actions and the ``archived`` list filter."""

    # Extra fields set when archiving, e.g. a challenge stops being primary.
    archive_also = {}

    def archive_service(self, user, instance):
        return archive_record(user=user, instance=instance, also=self.archive_also)

    def restore_service(self, user, instance):
        return restore_record(user=user, instance=instance)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.action == "list":
            queryset = filter_archived(
                queryset, self.request.query_params.get("archived")
            )
        return queryset

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        obj = self.archive_service(request.user, self.get_object())
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        obj = self.restore_service(request.user, self.get_object())
        return Response(self.get_serializer(obj).data)
