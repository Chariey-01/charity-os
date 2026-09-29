import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


class Challenge(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenges",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    is_primary = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "user",
                Lower("name"),
                condition=models.Q(archived_at__isnull=True),
                name="challenges_challenge_active_name_ci_unique",
            ),
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(is_primary=True, archived_at__isnull=True),
                name="challenges_challenge_one_primary_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="challenges_challenge_dates_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=("draft", "active", "completed", "cancelled")
                ),
                name="challenges_challenge_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(archived_at__isnull=True)
                | models.Q(is_primary=False),
                name="challenges_challenge_archived_not_primary",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "status"), name="challenge_user_status_idx"),
            models.Index(
                fields=("user", "start_date", "end_date"),
                name="challenge_user_dates_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before start date."
        if self.archived_at is not None and self.is_primary:
            errors["is_primary"] = "An archived challenge cannot be primary."
        if errors:
            raise ValidationError(errors)
