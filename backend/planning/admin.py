from django.contrib import admin

from .models import Area


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "slug", "sort_order", "archived_at")
    list_filter = ("archived_at",)
    search_fields = ("name", "slug", "user__email")
    ordering = ("sort_order", "name")
