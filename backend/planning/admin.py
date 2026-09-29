from django.contrib import admin

from .models import Area, DailyCapacity


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "slug", "sort_order", "archived_at")
    list_filter = ("archived_at",)
    search_fields = ("name", "slug", "user__email")
    ordering = ("sort_order", "name")


@admin.register(DailyCapacity)
class DailyCapacityAdmin(admin.ModelAdmin):
    list_display = (
        "local_date",
        "user",
        "timezone_name",
        "available_minutes",
        "deep_work_minutes",
    )
    search_fields = ("user__email", "fixed_commitments")
    ordering = ("-local_date",)
