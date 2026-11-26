"""Safe retries of creates with the ``Idempotency-Key`` request header.

A client that sends a create and never sees the answer (a dropped
connection, a timeout, a network change on a phone) cannot tell whether the
record was stored. Sending the same request again with the same
``Idempotency-Key`` returns the stored answer instead of creating a second
record.

Rules:

* The client picks the key once per user action (one form submission) and
  reuses it only to retry that action: 1-255 visible ASCII characters; a
  random UUID is recommended. A new action gets a new key.
* Keys belong to one user and are kept for 24 hours (``TTL``). After that
  the same key starts a new create.
* Same key, endpoint and body: the first successful answer (status and body)
  is replayed with ``Idempotent-Replayed: true``. It is the record as it was
  created, not as it is now.
* Same key, different body or endpoint: 422 ``idempotency_key_reused``;
  nothing is created.
* A create that fails (any non-2xx answer) stores nothing, so it can be
  retried with the same key after the problem is fixed.
* Two requests with the same key at once: the key's unique index makes the
  second wait for the first, then it gets the first one's answer.
* No header: nothing changes. Requests without a key are never deduplicated,
  so separate actions always create separate records.
"""

import hashlib
import json
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from .exceptions import CodedAPIException
from .models import IdempotencyKey

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
TTL = timedelta(hours=24)
VALID_KEY = re.compile(r"[\x21-\x7e]{1,255}")


class InvalidIdempotencyKey(CodedAPIException):
    status_code = 400
    default_code = "invalid_idempotency_key"
    default_detail = (
        "Idempotency-Key must be 1 to 255 visible ASCII characters, such as a UUID."
    )


class IdempotencyKeyReused(CodedAPIException):
    status_code = 422
    default_code = "idempotency_key_reused"
    default_detail = (
        "This Idempotency-Key was already used for a different request. "
        "Use a new key for a new action."
    )


class IdempotencyKeyUnavailable(CodedAPIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "That request is still being processed. Try again shortly."


def request_fingerprint(request):
    """A hash of what the request asks for: method, path and parsed body."""
    data = request.data
    if hasattr(data, "lists"):  # form or multipart data
        data = dict(data.lists())
    body = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(
        f"{request.method} {request.path}\n{body}".encode()
    ).hexdigest()


def purge_expired(now=None):
    """Delete every key older than ``TTL``; returns the number removed."""
    cutoff = (now or timezone.now()) - TTL
    return IdempotencyKey.objects.filter(created_at__lt=cutoff).delete()[0]


class IdempotentCreateMixin:
    """Honour ``Idempotency-Key`` on ``create`` (see the module docstring)."""

    def create(self, request, *args, **kwargs):
        key = request.headers.get(HEADER)
        if key is None:
            return super().create(request, *args, **kwargs)
        if not VALID_KEY.fullmatch(key):
            raise InvalidIdempotencyKey()
        fingerprint = request_fingerprint(request)
        purge_expired()
        with transaction.atomic():
            try:
                # A savepoint: a duplicate key leaves the transaction usable.
                # While another request holds the same key uncommitted, this
                # insert waits for it to commit or roll back.
                with transaction.atomic():
                    record = IdempotencyKey.objects.create(
                        user=request.user,
                        key=key,
                        method=request.method,
                        path=request.path,
                        fingerprint=fingerprint,
                    )
            except IntegrityError:
                return self._replay(request, key, fingerprint)
            response = super().create(request, *args, **kwargs)
            if status.is_success(response.status_code):
                record.status_code = response.status_code
                record.response_body = response.data
                record.save(update_fields=["status_code", "response_body"])
            else:
                transaction.set_rollback(True)  # keep nothing for a failure
        return response

    def _replay(self, request, key, fingerprint):
        record = IdempotencyKey.objects.filter(user=request.user, key=key).first()
        if record is None or record.status_code is None:
            raise IdempotencyKeyUnavailable()
        if record.fingerprint != fingerprint:
            raise IdempotencyKeyReused()
        return Response(
            record.response_body,
            status=record.status_code,
            headers={REPLAYED_HEADER: "true"},
        )
