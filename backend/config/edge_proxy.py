"""Accept requests only from CharityOS's own Cloudflare Worker.

When Cloudflare serves the PWA and forwards ``/api/``, ``/admin/`` and
``/static/`` to a backend on another host (docs/operations/cloudflare-deployment.md),
that backend still has a public address of its own. With
``CHARITYOS_EDGE_PROXY_SECRET`` set:

* Every request must carry the same value in ``X-CharityOS-Edge-Secret``
  (compared in constant time). Anything else gets 403, so the backend cannot be
  used directly, around Cloudflare, to guess passwords or reach the admin.
  The platform health probe is answered earlier (``config/health_probe.py``)
  and reveals nothing.
* The Worker sends the visitor's address (Cloudflare's ``CF-Connecting-IP``)
  in ``X-CharityOS-Client-IP``. It is believed only on a request that carried
  the secret, and only if it is a plain IP address. It then becomes
  ``REMOTE_ADDR``, so login lockouts and the security log see the visitor, not
  Cloudflare (``config/proxies.py`` keeps ``CHARITYOS_TRUSTED_PROXIES`` empty).
* Both headers are removed from the request before any view, log or error
  report can see them.

Without the secret the middleware switches itself off (``MiddlewareNotUsed``),
so a single-host deployment behaves exactly as before.
"""

import hmac
import ipaddress
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, MiddlewareNotUsed
from django.http import JsonResponse

from config.security import security_event

SECRET_HEADER = "HTTP_X_CHARITYOS_EDGE_SECRET"
CLIENT_IP_HEADER = "HTTP_X_CHARITYOS_CLIENT_IP"
MIN_SECRET_LENGTH = 32


def validate_secret(secret):
    """Refuse a secret that could be guessed; an empty one means "off"."""
    if secret and (len(secret) < MIN_SECRET_LENGTH or len(set(secret)) < 16):
        raise ImproperlyConfigured(
            "CHARITYOS_EDGE_PROXY_SECRET must be a random value of at least "
            f"{MIN_SECRET_LENGTH} characters, e.g. "
            "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
        )
    return secret


def _address(value):
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


class EdgeProxyMiddleware:
    def __init__(self, get_response):
        secret = validate_secret(getattr(settings, "CHARITYOS_EDGE_PROXY_SECRET", ""))
        if not secret:
            raise MiddlewareNotUsed
        self.secret = secret.encode()
        self.get_response = get_response

    def __call__(self, request):
        sent = request.META.pop(SECRET_HEADER, "")
        claimed = request.META.pop(CLIENT_IP_HEADER, "")
        if not hmac.compare_digest(sent.encode(), self.secret):
            # Neither header value is logged: one may be a near-miss secret.
            security_event(
                "edge_secret_rejected",
                request=request,
                level=logging.WARNING,
                secret_sent="yes" if sent else "no",
            )
            message = "This address only answers CharityOS's own site."
            return JsonResponse(
                {"detail": message, "error": {"code": "edge_only", "message": message}},
                status=403,
            )
        address = _address(claimed)
        if address:
            request.META["REMOTE_ADDR"] = address
        return self.get_response(request)
