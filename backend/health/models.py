# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Func

from execution.models import FocusSession


class TstzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class SleepLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sleep_logs"
    )
    started_at = models.DateTimeField()
    woke_at = models.DateTimeField()
    timezone_name = models.CharField(max_length=64)
    wake_local_date = models.DateField()
    quality = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(woke_at__gt=models.F("started_at")),
                name="health_sleep_order_valid",
            ),
            ExclusionConstraint(
                name="health_sleep_no_overlap",
                expressions=(
                    ("user", RangeOperators.EQUAL),
                    (TstzRange("started_at", "woke_at"), RangeOperators.OVERLAPS),
                ),
            ),
        ]


class ExerciseLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exercise_logs"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    activity = models.CharField(max_length=100)
    notes = models.TextField(blank=True, default="")
    session = models.OneToOneField(
        FocusSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exercise_log",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_at__gt=models.F("started_at")),
                name="health_exercise_order_valid",
            ),
            ExclusionConstraint(
                name="health_exercise_no_overlap",
                expressions=(
                    ("user", RangeOperators.EQUAL),
                    (TstzRange("started_at", "ended_at"), RangeOperators.OVERLAPS),
                ),
            ),
        ]


class MealLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_logs"
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    meal_type = models.CharField(max_length=30)
    description = models.TextField()
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DailyWaterTotal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="water_totals"
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    total_ml = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "local_date"), name="health_water_user_date_unique"
            )
        ]


class DailyNutritionRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nutrition_ratings",
    )
    local_date = models.DateField()
    timezone_name = models.CharField(max_length=64)
    rating = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "local_date"), name="health_nutrition_user_date_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(rating__range=(1, 5)),
                name="health_nutrition_rating_valid",
            ),
        ]
