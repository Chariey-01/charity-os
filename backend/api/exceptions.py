from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from scheduling.services import ScheduleConflict, ScheduleOverlap


def _flatten(exc):
    if hasattr(exc, "error_dict"):
        fields = {
            key: [str(message) for message in messages]
            for key, messages in exc.message_dict.items()
        }
        first = next(iter(fields.values()), ["Invalid request."])
        return first[0], fields
    messages = [str(message) for message in exc.messages] or ["Invalid request."]
    return messages[0], {}


def exception_handler(exc, context):
    """Return structured JSON for domain errors raised by services.

    Without this, Django ``ValidationError`` raised inside a service surfaced
    as HTTP 500. ``detail`` is kept for clients that read DRF's default key.
    """
    if isinstance(exc, DjangoValidationError):
        message, fields = _flatten(exc)
        status = 409 if isinstance(exc, ScheduleConflict) else 400
        code = exc.code_name if isinstance(exc, ScheduleConflict) else "invalid"
        error = {"code": code, "message": message, "fields": fields}
        if isinstance(exc, ScheduleOverlap):
            error["conflicts"] = [
                {
                    "id": str(entry.id),
                    "title": entry.title,
                    "start_at": entry.start_at.isoformat(),
                    "end_at": entry.end_at.isoformat(),
                }
                for entry in exc.conflicts
            ]
        return Response({"detail": message, "error": error}, status=status)
    if isinstance(exc, ObjectDoesNotExist):
        message = "Not found."
        return Response(
            {"detail": message, "error": {"code": "not_found", "message": message}},
            status=404,
        )
    return drf_exception_handler(exc, context)
