import uuid

from django.conf import settings
from django.contrib.auth import (
    get_user_model,
    login,
    password_validation,
    update_session_auth_hash,
)
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from community import services
from community.models import BetaInvite, Cheer, Feedback, Partnership
from growth.models import Goal
from reflections.models import WeeklyReview


def _user(user):
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "timezone": user.timezone,
        "is_beta_admin": user.is_staff,
    }


def _text(data, field, limit=None):
    value = data.get(field, "")
    if not isinstance(value, str):
        raise serializers.ValidationError({field: ["Must be text."]})
    return value[:limit] if limit else value


def _require_staff(request):
    if not request.user.is_staff:
        raise PermissionDenied("Only the beta admin can do this.")


# --- Accounts ----------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def signup_status(request):
    return Response({"mode": settings.CHARITYOS_SIGNUP_MODE})


@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request):
    SessionAuthentication().enforce_csrf(request)
    if settings.CHARITYOS_SIGNUP_MODE != "invite":
        raise PermissionDenied("Sign-up is closed.")
    user = services.sign_up(
        code=_text(request.data, "invite_code", 100),
        email=_text(request.data, "email", 254),
        password=_text(request.data, "password", 200),
        display_name=_text(request.data, "display_name", 100),
        timezone_name=_text(request.data, "timezone", 64) or "UTC",
    )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response(_user(user), status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    SessionAuthentication().enforce_csrf(request)
    services.reset_password(
        uid=_text(request.data, "uid", 100),
        token=_text(request.data, "token", 100),
        password=_text(request.data, "password", 200),
    )
    return Response({"reset": True})


@api_view(["POST"])
def change_password(request):
    current = _text(request.data, "current_password", 200)
    new = _text(request.data, "new_password", 200)
    if not request.user.check_password(current):
        raise serializers.ValidationError({"current_password": ["That is not your current password."]})
    password_validation.validate_password(new, request.user)
    request.user.set_password(new)
    request.user.save(update_fields=("password",))
    update_session_auth_hash(request, request.user)
    return Response({"changed": True})


# --- Beta admin ----------------------------------------------------------------


def _invite(invite):
    return {
        "id": str(invite.pk),
        "email": invite.email,
        "note": invite.note,
        "uses": invite.uses,
        "max_uses": invite.max_uses,
        "expires_at": invite.expires_at,
        "status": services.invite_status(invite),
        "created_at": invite.created_at,
    }


@api_view(["GET", "POST"])
def beta_invites(request):
    _require_staff(request)
    if request.method == "POST":
        days = request.data.get("days", services.INVITE_DAYS)
        uses = request.data.get("max_uses", 1)
        if not isinstance(days, int) or not 1 <= days <= 60:
            raise serializers.ValidationError({"days": ["Between 1 and 60 days."]})
        if not isinstance(uses, int) or not 1 <= uses <= 50:
            raise serializers.ValidationError({"max_uses": ["Between 1 and 50."]})
        email = _text(request.data, "email", 254).strip()
        if email and "@" not in email:
            raise serializers.ValidationError({"email": ["Enter a valid email or leave it empty."]})
        invite, code = services.create_invite(
            created_by=request.user,
            email=email,
            note=_text(request.data, "note", 120),
            max_uses=uses,
            days=days,
        )
        return Response({**_invite(invite), "code": code}, status=201)
    invites = BetaInvite.objects.order_by("-created_at")[:100]
    return Response([_invite(invite) for invite in invites])


@api_view(["POST"])
def beta_invite_revoke(request, pk):
    _require_staff(request)
    invite = BetaInvite.objects.filter(pk=pk).first()
    if invite is None:
        raise NotFound()
    if invite.revoked_at is None:
        invite.revoked_at = timezone.now()
        invite.save(update_fields=("revoked_at",))
    return Response(_invite(invite))


@api_view(["GET"])
def beta_users(request):
    _require_staff(request)
    users = get_user_model().objects.order_by("date_joined")
    return Response(
        [
            {
                "id": str(user.pk),
                "email": user.email,
                "display_name": user.display_name,
                "date_joined": user.date_joined,
                "last_login": user.last_login,
                "is_active": user.is_active,
            }
            for user in users
        ]
    )


@api_view(["POST"])
def beta_reset_link(request, pk):
    _require_staff(request)
    user = get_user_model().objects.filter(pk=pk, is_active=True).first()
    if user is None:
        raise NotFound()
    uid, token = services.reset_link_parts(user)
    return Response({"path": f"/#/reset?uid={uid}&token={token}"})


@api_view(["GET"])
def beta_feedback(request):
    _require_staff(request)
    rows = Feedback.objects.select_related("user").order_by("-created_at")[:200]
    return Response([{**_feedback(row), "from": row.user.display_name or row.user.email} for row in rows])


@api_view(["POST"])
def beta_feedback_status(request, pk):
    _require_staff(request)
    row = Feedback.objects.filter(pk=pk).first()
    if row is None:
        raise NotFound()
    status = _text(request.data, "status", 10)
    if status not in Feedback.Status.values:
        raise serializers.ValidationError({"status": ["Use new, seen or resolved."]})
    row.status = status
    row.save(update_fields=("status",))
    return Response(_feedback(row))


# --- Feedback ------------------------------------------------------------------


def _feedback(row):
    return {
        "id": str(row.pk),
        "kind": row.kind,
        "message": row.message,
        "page": row.page,
        "device": row.device,
        "status": row.status,
        "created_at": row.created_at,
    }


@api_view(["GET", "POST"])
def feedback(request):
    if request.method == "POST":
        kind = _text(request.data, "kind", 10) or "bug"
        message = _text(request.data, "message", 4000).strip()
        if kind not in Feedback.Kind.values:
            raise serializers.ValidationError({"kind": ["Choose a kind."]})
        if len(message) < 5:
            raise serializers.ValidationError({"message": ["Tell us a little more."]})
        row = Feedback.objects.create(
            user=request.user,
            kind=kind,
            message=message,
            page=_text(request.data, "page", 200),
            device=_text(request.data, "device", 300),
        )
        return Response(_feedback(row), status=201)
    rows = Feedback.objects.filter(user=request.user).order_by("-created_at")[:50]
    return Response([_feedback(row) for row in rows])


# --- Accountability partners --------------------------------------------------------


def _sharing(partnership):
    partner = partnership.partner
    return {
        "id": str(partnership.pk),
        "invited_email": partnership.invited_email,
        "partner": (partner.display_name or partner.email) if partner else None,
        "status": partnership.status,
        "paused": partnership.paused,
        "share_summary": partnership.share_summary,
        "share_achievements": partnership.share_achievements,
        "goals": [str(pk) for pk in partnership.goals.values_list("pk", flat=True)],
        "weekly_reviews": [
            str(pk) for pk in partnership.weekly_reviews.values_list("pk", flat=True)
        ],
        "cheers": [
            {"kind": c.kind, "message": c.message, "about": c.about, "created_at": c.created_at}
            for c in partnership.cheers.order_by("-created_at")[:20]
        ],
        "created_at": partnership.created_at,
        "accepted_at": partnership.accepted_at,
    }


@api_view(["GET", "POST"])
def partners(request):
    user = request.user
    if request.method == "POST":
        email = _text(request.data, "email", 254).strip().lower()
        if "@" not in email:
            raise serializers.ValidationError({"email": ["Enter your partner's email address."]})
        if email == user.email.lower():
            raise serializers.ValidationError({"email": ["You cannot invite yourself."]})
        if Partnership.objects.filter(
            owner=user, invited_email__iexact=email, status__in=("pending", "active")
        ).exists():
            raise serializers.ValidationError({"email": ["You already invited this person."]})
        partnership = Partnership.objects.create(
            owner=user,
            invited_email=email,
            share_summary=request.data.get("share_summary", True) is True,
            share_achievements=request.data.get("share_achievements", False) is True,
        )
        return Response(_sharing(partnership), status=201)
    sharing = Partnership.objects.filter(owner=user).exclude(status="declined").order_by("-created_at")
    received = Partnership.objects.filter(partner=user, status="active")
    invitations = Partnership.objects.filter(
        invited_email__iexact=user.email, status="pending"
    ).exclude(owner=user)
    return Response(
        {
            "sharing": [_sharing(p) for p in sharing if p.status != "ended"],
            "ended": [_sharing(p) for p in sharing if p.status == "ended"][:10],
            "shared_with_me": [
                {"id": str(p.pk), "owner": p.owner.display_name or p.owner.email.split("@")[0], "paused": p.paused}
                for p in received
            ],
            "invitations": [
                {"id": str(p.pk), "owner": p.owner.display_name or p.owner.email.split("@")[0], "created_at": p.created_at}
                for p in invitations
            ],
        }
    )


def _owned(request, pk):
    partnership = Partnership.objects.filter(pk=pk, owner=request.user).first()
    if partnership is None:
        raise NotFound()
    return partnership


@api_view(["PATCH"])
def partner_update(request, pk):
    partnership = _owned(request, pk)
    if partnership.status not in ("pending", "active"):
        raise serializers.ValidationError({"status": ["This partnership has ended."]})
    data = request.data
    with transaction.atomic():
        for field in ("paused", "share_summary", "share_achievements"):
            if field in data:
                if not isinstance(data[field], bool):
                    raise serializers.ValidationError({field: ["Use true or false."]})
                setattr(partnership, field, data[field])
        partnership.save()
        if "goals" in data:
            ids = data["goals"] if isinstance(data["goals"], list) else None
            goals = Goal.objects.filter(user=request.user, pk__in=ids or [])
            if ids is None or goals.count() != len(set(ids)):
                raise serializers.ValidationError({"goals": ["Choose from your own goals."]})
            partnership.goals.set(goals)
        if "weekly_reviews" in data:
            ids = data["weekly_reviews"] if isinstance(data["weekly_reviews"], list) else None
            reviews = WeeklyReview.objects.filter(user=request.user, pk__in=ids or [])
            if ids is None or reviews.count() != len(set(ids)):
                raise serializers.ValidationError({"weekly_reviews": ["Choose from your own reviews."]})
            partnership.weekly_reviews.set(reviews)
    return Response(_sharing(partnership))


def _invitation(request, pk):
    partnership = (
        Partnership.objects.filter(pk=pk, status="pending", invited_email__iexact=request.user.email)
        .exclude(owner=request.user)
        .first()
    )
    if partnership is None:
        raise NotFound()
    return partnership


@api_view(["POST"])
def partner_accept(request, pk):
    partnership = _invitation(request, pk)
    partnership.partner = request.user
    partnership.status = Partnership.Status.ACTIVE
    partnership.accepted_at = timezone.now()
    partnership.save()
    return Response({"id": str(partnership.pk), "status": partnership.status})


@api_view(["POST"])
def partner_decline(request, pk):
    partnership = _invitation(request, pk)
    partnership.status = Partnership.Status.DECLINED
    partnership.ended_at = timezone.now()
    partnership.save()
    return Response({"id": str(partnership.pk), "status": partnership.status})


@api_view(["POST"])
def partner_end(request, pk):
    """The owner stops sharing, or the partner leaves. Either may end it."""
    partnership = Partnership.objects.filter(pk=pk).first()
    if partnership is None or request.user.pk not in (partnership.owner_id, partnership.partner_id):
        raise NotFound()
    if partnership.status in ("pending", "active"):
        partnership.status = Partnership.Status.ENDED
        partnership.ended_at = timezone.now()
        partnership.save()
    return Response({"id": str(partnership.pk), "status": partnership.status})


def _received(request, pk):
    partnership = Partnership.objects.filter(pk=pk, partner=request.user, status="active").select_related("owner").first()
    if partnership is None:
        raise NotFound()
    return partnership


@api_view(["GET"])
def partner_view(request, pk):
    return Response(services.partner_view(_received(request, pk)))


@api_view(["POST"])
def partner_cheer(request, pk):
    partnership = _received(request, pk)
    if partnership.paused:
        raise serializers.ValidationError({"detail": ["Sharing is paused."]})
    kind = _text(request.data, "kind", 10) or "cheer"
    if kind not in Cheer.Kind.values:
        raise serializers.ValidationError({"kind": ["Choose cheer, encourage or checkin."]})
    message = _text(request.data, "message", 280).strip()
    about = _text(request.data, "about", 80)
    if about and about != "summary":
        shared = False
        if about.startswith("goal:"):
            try:
                shared = partnership.goals.filter(pk=uuid.UUID(about[5:])).exists()
            except ValueError:
                shared = False
        if not shared:
            raise serializers.ValidationError(
                {"about": ["You can only respond to what is shared with you."]}
            )
    cheer = Cheer.objects.create(
        partnership=partnership, sender=request.user, kind=kind, message=message, about=about
    )
    return Response({"id": str(cheer.pk), "kind": cheer.kind}, status=201)

