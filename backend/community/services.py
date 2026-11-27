"""Beta sign-up, password reset links and what an accountability partner sees.

The partner view is built from an explicit allow-list (``partner_view``):
the owner's display name, the switches and selections the owner made, and
nothing else. Records are read, never written, on the owner's behalf.
"""

import hashlib
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import BetaInvite, Partnership

INVITE_DAYS = 14
ACHIEVEMENT_DAYS = 30


def _hash(code):
    return hashlib.sha256(code.strip().encode()).hexdigest()


def create_invite(*, created_by, email="", note="", max_uses=1, days=INVITE_DAYS):
    """Returns (invite, code). The code is shown once and never stored."""
    code = "-".join(secrets.token_hex(3) for _ in range(4))  # e.g. 3f9a1c-...
    invite = BetaInvite.objects.create(
        created_by=created_by,
        code_hash=_hash(code),
        email=email.strip().lower(),
        note=note[:120],
        max_uses=max(1, min(int(max_uses), 50)),
        expires_at=timezone.now() + timedelta(days=days),
    )
    return invite, code


def invite_status(invite, now=None):
    now = now or timezone.now()
    if invite.revoked_at:
        return "revoked"
    if invite.uses >= invite.max_uses:
        return "used"
    if invite.expires_at <= now:
        return "expired"
    return "open"


@transaction.atomic
def sign_up(*, code, email, password, display_name="", timezone_name="UTC"):
    """Create an account with a valid invite. Raises ValidationError."""
    from planning.categories import ensure_default_categories
    from users.models import UserPreferences, validate_timezone

    User = get_user_model()
    email = (email or "").strip().lower()
    invite = (
        BetaInvite.objects.select_for_update()
        .filter(code_hash=_hash(code or ""))
        .first()
    )
    if invite is None or invite_status(invite) != "open":
        raise ValidationError({"invite_code": "This invite code is not valid or has been used."})
    if invite.email and invite.email != email:
        raise ValidationError({"invite_code": "This invite is for a different email address."})
    if not email or "@" not in email:
        raise ValidationError({"email": "Enter your email address."})
    try:
        validate_timezone(timezone_name)
    except ValidationError:
        timezone_name = "UTC"
    candidate = User(email=email, display_name=display_name[:100])
    password_validation.validate_password(password, candidate)
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"email": "An account with this email already exists. Sign in instead."})
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email, password, display_name=display_name[:100], timezone=timezone_name
            )
    except IntegrityError as exc:
        raise ValidationError({"email": "An account with this email already exists."}) from exc
    ensure_default_categories(user)
    UserPreferences.objects.get_or_create(user=user)
    invite.uses += 1
    invite.save(update_fields=("uses",))
    return user


def reset_link_parts(user):
    return (
        urlsafe_base64_encode(force_bytes(user.pk)),
        default_token_generator.make_token(user),
    )


def reset_password(*, uid, token, password):
    User = get_user_model()
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, ValidationError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({"token": "This reset link is not valid or has expired. Ask for a new one."})
    password_validation.validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=("password",))
    return user


# --- Accountability partners -------------------------------------------------


def open_partnerships_for(user):
    """Invitations waiting for ``user`` (matched by email) and active ones."""
    return Partnership.objects.filter(
        invited_email__iexact=user.email, status__in=("pending", "active")
    ).exclude(owner=user)


def partner_view(partnership, now=None):
    """Everything the partner may see, built from the owner's choices only."""
    from execution.models import FocusSession
    from growth.models import ActivityEvent
    from growth.services import goal_progress
    from planning.models import PlanningEvent

    now = now or timezone.now()
    owner = partnership.owner
    base = {
        "id": str(partnership.pk),
        "owner": owner.display_name or owner.email.split("@")[0],
        "status": partnership.status,
        "paused": partnership.paused,
    }
    if partnership.status != Partnership.Status.ACTIVE or partnership.paused:
        return base
    zone = ZoneInfo(owner.timezone)
    today = now.astimezone(zone).date()
    goals = []
    for goal in partnership.goals.filter(archived_at__isnull=True).prefetch_related(
        "milestones", "tasks", "checkins"
    ):
        progress = goal_progress(goal, today)
        goals.append(
            {
                "id": str(goal.pk),
                "title": goal.title,
                "status": goal.status,
                "target_date": goal.target_date,
                "progress": progress["ratio"],
                "basis": progress["basis"],
                "overdue": progress["overdue"],
                "milestones": [
                    {"title": m.title, "status": m.status, "target_date": m.target_date}
                    for m in goal.milestones.all()
                    if m.archived_at is None
                ],
            }
        )
    view = {**base, "goals": goals}
    if partnership.share_summary:
        week_start = today - timedelta(days=today.weekday())
        start = datetime.combine(week_start, time.min, tzinfo=zone)
        done = PlanningEvent.objects.filter(user=owner, created_at__gte=start).filter(
            event_type__in=("completed", "status_changed"), snapshot__to="done"
        ).count()
        seconds = sum(
            FocusSession.objects.filter(
                user=owner, status="completed", started_at__gte=start
            ).values_list("duration_seconds", flat=True)
        )
        view["summary"] = {
            "week_start": week_start,
            "tasks_completed": done,
            "focus_minutes": (seconds or 0) // 60,
            "milestones_completed": ActivityEvent.objects.filter(
                user=owner, subject_type="milestone", kind="completed", occurred_at__gte=start
            ).count(),
        }
    if partnership.share_achievements:
        events = ActivityEvent.objects.filter(
            user=owner,
            kind__in=("completed", "realised"),
            subject_type__in=("goal", "milestone", "project", "roadmap_item", "roadmap", "challenge"),
            occurred_at__gte=now - timedelta(days=ACHIEVEMENT_DAYS),
        ).order_by("-occurred_at")[:30]
        view["achievements"] = [
            {"kind": e.subject_type, "title": e.title, "date": e.occurred_at.astimezone(zone).date()}
            for e in events
        ]
    view["weekly_reviews"] = [
        {"week_start_date": r.week_start_date, "wins": r.wins, "next_week": r.next_week}
        for r in partnership.weekly_reviews.filter(archived_at__isnull=True).order_by(
            "-week_start_date"
        )[:8]
    ]
    view["cheers"] = [
        {"kind": c.kind, "message": c.message, "about": c.about, "created_at": c.created_at}
        for c in partnership.cheers.order_by("-created_at")[:20]
    ]
    return view
