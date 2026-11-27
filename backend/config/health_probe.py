"""The health check a hosting platform polls: ``GET /api/v1/health``.

The platform's probe comes from inside its own network, over plain HTTP and
with whatever ``Host`` header it chooses (often an internal address). Behind
production settings that request would be redirected to HTTPS
(``SECURE_SSL_REDIRECT``) or refused as a disallowed host, and the platform
would mark a healthy service as down.

So ``HealthProbeMiddleware`` sits first in ``MIDDLEWARE`` and answers exactly
``GET``/``HEAD /api/v1/health`` itself, before any host or HTTPS check. The
answer carries no data: whether a ``SELECT 1`` on the database succeeded.
Every other request, including other methods on that path, takes the normal
route.
"""

import logging

from django.db import connection
from django.db.utils import DatabaseError
from django.http import JsonResponse

HEALTH_PATH = "/api/v1/health"
logger = logging.getLogger("django.request")


def database_available():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as error:
        # The class name only: driver messages can name hosts and users.
        logger.error("health check: database unavailable (%s)", type(error).__name__)
        return False
    return True


def health_body():
    """``(body, status)`` for the health endpoint."""
    if database_available():
        return {"status": "ok", "database": "ok"}, 200
    return {"status": "unhealthy", "database": "unavailable"}, 503


class HealthProbeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == HEALTH_PATH and request.method in ("GET", "HEAD"):
            body, status = health_body()
            response = JsonResponse(body, status=status)
            response["Cache-Control"] = "no-store"
            return response
        return self.get_response(request)
