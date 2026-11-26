"""Login-security hooks for django-axes (Phase 0C, S11)."""

from django.http import JsonResponse

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
