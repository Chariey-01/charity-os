import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Area(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="areas",
    )
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90)
    color = models.CharField(max_length=7, default="#64748B")
    icon = models.CharField(max_length=50, blank=True, default="")
    sort_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "user",
                Lower("name"),
                condition=models.Q(archived_at__isnull=True),
                name="planning_area_active_name_ci_unique",
            ),
            models.UniqueConstraint(
                fields=("user", "slug"),
                name="planning_area_user_slug_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="planning_area_color_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(sort_order__gte=0),
                name="planning_area_sort_order_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "archived_at", "sort_order"),
                name="planning_area_user_order_idx",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if self.color and HEX_COLOR_PATTERN.fullmatch(self.color) is None:
            errors["color"] = "Color must be a hex RGB value such as #64748B."
        if self.sort_order is not None and self.sort_order < 0:
            errors["sort_order"] = "Sort order cannot be negative."
        if errors:
            raise ValidationError(errors)
