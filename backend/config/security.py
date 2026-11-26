"""Login security (Phase 0C, S11) and the security event log (S12).

Security events go to the "charityos.security" logger as one line each,
``event=<name> key=value ...``. Emails are masked (o***@example.com) and IP
addresses cut to their network (/24 for IPv4, /48 for IPv6): enough to
investigate an incident, not enough to identify a person from the log alone.
Passwords, session keys, CSRF tokens and request bodies are never logged.
"""

import ipaddress
import logging

from django.http import JsonResponse

from config.proxies import client_ip

security_log = logging.getLogger("charityos.security")

LOCKOUT_MESSAGE = "Too many failed sign-in attempts. Wait 15 minutes, then try again."


def axes_username(request, credentials):
    """The account being attempted, from the API login (email) or the admin
    login (username, which is the email here), normalised like stored emails."""
    credentials = credentials or {}
    value = credentials.get("email") or credentials.get("username") or ""
    return str(value).strip().lower()


def lockout_response(request, original_response, credentials):
    """The same 429 for every locked attempt: it never says whether the
    account exists, and it repeats no email."""
    return JsonResponse(
        {
            "detail": LOCKOUT_MESSAGE,
            "error": {"code": "too_many_attempts", "message": LOCKOUT_MESSAGE},
        },
        status=429,
    )


def mask_email(value):
    value = str(value or "").strip()
    if "@" not in value:
        return "***" if value else "-"
    local, _, domain = value.rpartition("@")
    return f"{local[:1]}***@{domain.lower()}"


def mask_ip(value):
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return "-"
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def security_event(
    event,
    *,
    request=None,
    user=None,
    user_id=None,
    email=None,
    level=logging.INFO,
    **fields,
):
    """Log one security event. Only masked or non-sensitive values are written.

    ``user_id`` is for events about an account that no longer exists.
    """
    parts = {"event": event}
    if user is not None:
        user_id = user.pk
        email = email or getattr(user, "email", None)
    if user_id is not None:
        parts["user"] = str(user_id)
    if email is not None:
        parts["email"] = mask_email(email)
    if request is not None:
        parts["ip"] = mask_ip(client_ip(request))
        parts["path"] = request.path
    parts.update({key: value for key, value in fields.items() if value is not None})
    security_log.log(
        level,
        " ".join(f"{key}={value}" for key, value in parts.items()),
        extra={"security_event": event},
    )


def _attempted_email(credentials):
    credentials = credentials or {}
    return credentials.get("email") or credentials.get("username") or ""


def on_login(sender, request, user, **kwargs):
    security_event("login_succeeded", request=request, user=user)


def on_login_failed(sender, credentials, request=None, **kwargs):
    # Django has already blanked the password in `credentials`; only the email
    # is read, and it is masked.
    security_event(
        "login_failed",
        request=request,
        email=_attempted_email(credentials),
        level=logging.WARNING,
    )


def on_logout(sender, request, user, **kwargs):
    security_event("logout", request=request, user=user)


def on_locked_out(sender, request=None, username=None, ip_address=None, **kwargs):
    security_event(
        "login_locked_out", request=request, email=username, level=logging.WARNING
    )


def connect_signals():
    from axes.signals import user_locked_out
    from django.contrib.auth.signals import (
        user_logged_in,
        user_logged_out,
        user_login_failed,
    )

    user_logged_in.connect(on_login, dispatch_uid="charityos.security.login")
    user_login_failed.connect(on_login_failed, dispatch_uid="charityos.security.failed")
    user_logged_out.connect(on_logout, dispatch_uid="charityos.security.logout")
    user_locked_out.connect(on_locked_out, dispatch_uid="charityos.security.locked")
