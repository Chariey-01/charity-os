from django.contrib import admin

from config.admin_safety import NoHardDeleteAdmin

from .models import Challenge


@admin.register(Challenge)
class ChallengeAdmin(NoHardDeleteAdmin, admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "status",
        "start_date",
        "end_date",
        "is_primary",
        "archived_at",
    )
    list_filter = ("status", "is_primary", "archived_at")
    search_fields = ("name", "description", "user__email")
    ordering = ("-start_date", "name")
