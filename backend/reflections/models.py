# ruff: noqa: DJ008
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class DailyReflection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_reflections",
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    went_well = models.TextField(blank=True, default="")
    learned = models.TextField(blank=True, default="")
    improve = models.TextField(blank=True, default="")
    mood = models.PositiveSmallIntegerField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "local_date"), name="reflections_daily_user_date_unique"
            )
        ]


class WeeklyReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weekly_reviews",
    )
    week_start_date = models.DateField()
    week_end_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    wins = models.TextField(blank=True, default="")
    lessons = models.TextField(blank=True, default="")
    next_week = models.TextField(blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "week_start_date"),
                name="reflections_weekly_user_start_unique",
            )
        ]

    def clean(self):
        if self.week_start_date and self.week_start_date.isoweekday() != 1:
            raise ValidationError({"week_start_date": "Week must start on Monday."})
        if (
            self.week_start_date
            and self.week_end_date != self.week_start_date + timedelta(days=6)
        ):
            raise ValidationError({"week_end_date": "Week must end on Sunday."})
