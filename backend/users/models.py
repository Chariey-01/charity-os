import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone as django_timezone

from .managers import UserManager


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValidationError("Enter a valid IANA timezone.") from error


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    display_name = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(
        max_length=64, default="UTC", validators=[validate_timezone]
    )
    week_starts_on = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=django_timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_user_email_ci_unique"),
            models.CheckConstraint(
                condition=models.Q(week_starts_on__range=(1, 7)),
                name="users_user_week_starts_on_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = UserManager._normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class UserPreferences(models.Model):
    """Per-user scheduler, reminder and motivation settings."""

    class TodayView(models.TextChoices):
        AGENDA = "agenda", "Agenda"
        TIMELINE = "timeline", "Timeline"
        DAY = "day", "Day"

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="preferences"
    )
    reminders_enabled = models.BooleanField(default=False)
    reminder_lead_minutes = models.PositiveSmallIntegerField(
        default=10, validators=[MaxValueValidator(120)]
    )
    start_reminders_enabled = models.BooleanField(default=True)
    daily_planning_reminder_enabled = models.BooleanField(default=False)
    daily_planning_time = models.TimeField(default="07:30")
    weekly_review_reminder_enabled = models.BooleanField(default=False)
    weekly_review_weekday = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    weekly_review_time = models.TimeField(default="18:00")
    show_streaks = models.BooleanField(default=False)
    celebrations_enabled = models.BooleanField(default=True)
    default_today_view = models.CharField(
        max_length=10, choices=TodayView.choices, default=TodayView.AGENDA
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reminder_lead_minutes__lte=120),
                name="users_prefs_lead_minutes_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(weekly_review_weekday__range=(1, 7)),
                name="users_prefs_weekday_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    default_today_view__in=("agenda", "timeline", "day")
                ),
                name="users_prefs_today_view_valid",
            ),
        ]

    def __str__(self):
        return f"Preferences for {self.user_id}"
