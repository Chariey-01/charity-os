"""Private beta access, feedback and optional accountability partners.

* ``BetaInvite``: a code that lets one friend create an account. Only a hash
  is stored; the code is shown once to the beta admin who made it.
* ``Feedback``: bug reports and suggestions from inside the app.
* ``Partnership``: one person (the owner) shares chosen things with one
  partner, after the partner accepts. Sharing is one-directional; two
  people who want to share both ways each invite the other. The partner can
  read only what the owner switched on or selected, and can never edit the
  owner's records. Notes, reflections, journal entries and unshared goals
  and projects are never visible to a partner.
* ``Cheer``: encouragement a partner sends on a shared item.
"""

# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.db import models


class BetaInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="beta_invites"
    )
    code_hash = models.CharField(max_length=64, unique=True)
    # Optional: only this email may use the invite.
    email = models.EmailField(blank=True, default="")
    note = models.CharField(max_length=120, blank=True, default="")
    max_uses = models.PositiveSmallIntegerField(default=1)
    uses = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(uses__lte=models.F("max_uses")),
                name="community_invite_uses_within_max",
            ),
            models.CheckConstraint(
                condition=models.Q(max_uses__range=(1, 50)),
                name="community_invite_max_uses_valid",
            ),
        ]


class Feedback(models.Model):
    class Kind(models.TextChoices):
        BUG = "bug", "Something is broken"
        IDEA = "idea", "Idea or improvement"
        QUESTION = "question", "Question"
        PRAISE = "praise", "Something I like"

    class Status(models.TextChoices):
        NEW = "new", "New"
        SEEN = "seen", "Seen"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BUG)
    message = models.TextField(max_length=4000)
    page = models.CharField(max_length=200, blank=True, default="")
    # Only when the person ticked "include device details".
    device = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)


class Partnership(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Invited"
        ACTIVE = "active", "Active"
        DECLINED = "declined", "Declined"
        ENDED = "ended", "Ended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partnerships_shared"
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="partnerships_received",
    )
    invited_email = models.EmailField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    paused = models.BooleanField(default=False)
    share_summary = models.BooleanField(default=True)
    share_achievements = models.BooleanField(default=False)
    goals = models.ManyToManyField("growth.Goal", blank=True, related_name="+")
    weekly_reviews = models.ManyToManyField(
        "reflections.WeeklyReview", blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "owner",
                "invited_email",
                condition=models.Q(status__in=("pending", "active")),
                name="community_partnership_one_open_per_email",
            ),
            models.CheckConstraint(
                condition=~models.Q(owner=models.F("partner")),
                name="community_partnership_not_self",
            ),
        ]


class Cheer(models.Model):
    class Kind(models.TextChoices):
        CHEER = "cheer", "Cheer"
        ENCOURAGE = "encourage", "Encouragement"
        CHECKIN = "checkin", "Check-in question"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partnership = models.ForeignKey(
        Partnership, on_delete=models.CASCADE, related_name="cheers"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cheers_sent"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHEER)
    message = models.CharField(max_length=280, blank=True, default="")
    # What the cheer is about: "goal:<id>" or "summary".
    about = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
