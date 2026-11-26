import re
from collections import Counter

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError, RestrictedError
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    PermissionDenied,
)
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


class CodedAPIException(APIException):
    """An API error that answers with a stable ``error.code``."""


def _error(status, code, message, **extra):
    return Response(
        {"detail": message, "error": {"code": code, "message": message, **extra}},
        status=status,
    )


def _blocking(objects):
    """What still points at the record, as counts per kind: no ids or content."""
    counts = Counter(str(obj._meta.verbose_name_plural) for obj in objects)
    return [{"model": name, "count": count} for name, count in sorted(counts.items())]


def _is_csrf_rejection(exc):
    return isinstance(exc, PermissionDenied) and str(exc.detail).startswith(
        "CSRF Failed"
    )


def _csrf_reason(exc):
    """Django's reason ("CSRF token missing.", "Origin checking failed - ..."),
    printable ASCII only and capped: it can quote the client's Origin header."""
    text = str(exc.detail).removeprefix("CSRF Failed: ")
    return re.sub(r"[^\x20-\x7e]", "?", text).replace('"', "'")[:200]


def _log_csrf_rejection(exc, context):
    if _is_csrf_rejection(exc):
        import logging

        from config.security import security_event

        request = context.get("request")
        security_event(
            "csrf_rejected",
            request=getattr(request, "_request", request),
            method=getattr(request, "method", None),
            reason=f'"{_csrf_reason(exc)}"',
            level=logging.WARNING,
        )


def exception_handler(exc, context):
    """Return structured JSON for domain errors raised by services.

    Without this, Django ``ValidationError`` raised inside a service surfaced
    as HTTP 500. ``detail`` is kept for clients that read DRF's default key.
    """
    _log_csrf_rejection(exc, context)
    if isinstance(exc, DjangoValidationError):
        message, fields = _flatten(exc)
        # Domain errors may carry their own code and status (e.g. 409 conflicts).
        conflict = isinstance(exc, ScheduleConflict)
        status = 409 if conflict else getattr(exc, "http_status", 400)
        code = getattr(exc, "code_name", None) or "invalid"
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
    if isinstance(exc, (ProtectedError, RestrictedError)):
        blocked = getattr(exc, "protected_objects", None) or exc.restricted_objects
        return _error(
            409,
            "has_history",
            "This record still has history attached and cannot be deleted. "
            "Archive it instead.",
            blocking=_blocking(blocked),
        )
    # After Protected/RestrictedError, which are IntegrityError subclasses.
    if isinstance(exc, IntegrityError):
        # Validation runs every constraint first (OwnedModelSerializer); this is
        # the backstop for two requests racing past it. Never a 500.
        from .constraints import describe

        cause = exc.__cause__
        state = getattr(cause, "sqlstate", "") or ""
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        field, message = describe(constraint)
        conflict = state in ("23505", "23P01", "23503")  # unique, exclusion, FK
        return _error(
            409 if conflict else 400,
            "conflict" if conflict else "invalid",
            message,
            fields={field: [message]},
        )
    if isinstance(exc, CodedAPIException):
        return _error(
            exc.status_code,
            exc.default_code,
            str(exc.detail),
            **getattr(exc, "extra", {}),
        )
    # Clients must tell "signed out" apart from "not allowed": an expired
    # session sends the user to sign in, a CSRF or permission failure does not.
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        response = drf_exception_handler(exc, context)
        response.data = {
            "detail": str(exc.detail),
            "error": {"code": "not_authenticated", "message": str(exc.detail)},
        }
        return response
    if _is_csrf_rejection(exc):
        return _error(
            403,
            "csrf_failed",
            "Your security token is missing or out of date. Reload and try again.",
            reason=_csrf_reason(exc),
        )
    request = context.get("request")
    instead = getattr(context.get("view"), "delete_instead", None)
    if (
        isinstance(exc, MethodNotAllowed)
        and instead
        and request is not None
        and request.method == "DELETE"
    ):
        code, message = instead
        return _error(405, code, message)
    if isinstance(exc, ObjectDoesNotExist):
        message = "Not found."
        return Response(
            {"detail": message, "error": {"code": "not_found", "message": message}},
            status=404,
        )
    return drf_exception_handler(exc, context)
