"""Default activity categories.

Categories are stored as ``planning.Area`` rows. This module is the single
source for the defaults used by the bootstrap command, the data migration and
``POST /areas/ensure-defaults``.
"""

from django.db import transaction
from django.db.models.functions import Lower
from django.utils.text import slugify

# The model default colour; areas still carrying it were never coloured.
UNSET_COLOR = "#64748B"

# (name, colour, health_kind)
DEFAULT_CATEGORIES = (
    ("Software Engineering", "#2F6B55", ""),
    ("Computer Science", "#3D5A80", ""),
    ("Career", "#8C5E2A", ""),
    ("Freelancing", "#A0522D", ""),
    ("Projects", "#6A4C93", ""),
    ("Exercise", "#C2410C", "exercise"),
    ("Nutrition", "#65A30D", ""),
    ("Recovery", "#0E7490", ""),
    ("Sleep", "#4338CA", "sleep"),
    ("Personal", "#B4536A", ""),
    ("Social", "#D97706", ""),
    ("Learning", "#1D4ED8", ""),
    ("Custom", "#57534E", ""),
)


def _unique_slug(existing_slugs, name):
    base = slugify(name) or "category"
    slug, counter = base, 2
    while slug in existing_slugs:
        slug = f"{base}-{counter}"
        counter += 1
    existing_slugs.add(slug)
    return slug


def ensure_default_categories(user, area_model=None):
    """Create missing default categories for ``user``; never overwrite choices.

    Existing areas with a default name keep their name, order and archive
    state. They only receive the default colour if their colour was never set
    and the default health kind if none was chosen. Returns the created rows.
    """
    Area = area_model
    if Area is None:
        from .models import Area
    with transaction.atomic():
        areas = list(Area.objects.select_for_update().filter(user=user))
        by_name = {
            area.name.lower(): area for area in areas if area.archived_at is None
        }
        slugs = {area.slug for area in areas}
        next_order = max((area.sort_order for area in areas), default=-1) + 1
        created = []
        for name, color, health_kind in DEFAULT_CATEGORIES:
            area = by_name.get(name.lower())
            if area is None:
                created.append(
                    Area.objects.create(
                        user=user,
                        name=name,
                        slug=_unique_slug(slugs, name),
                        color=color,
                        health_kind=health_kind,
                        sort_order=next_order,
                    )
                )
                next_order += 1
                continue
            changed = []
            if area.color.upper() == UNSET_COLOR:
                area.color = color
                changed.append("color")
            if health_kind and not area.health_kind:
                area.health_kind = health_kind
                changed.append("health_kind")
            if changed:
                area.save(update_fields=(*changed, "updated_at"))
        return created


def active_categories(user):
    from .models import Area

    return Area.objects.filter(user=user, archived_at__isnull=True).order_by(
        "sort_order", Lower("name")
    )
