from django.db import migrations


def add_default_categories(apps, schema_editor):
    """Give existing users the scheduler's default categories.

    Only missing categories are created; existing names, order and archive
    state are untouched. Colours are filled only where never set.
    """
    from planning.categories import ensure_default_categories

    User = apps.get_model("users", "User")
    Area = apps.get_model("planning", "Area")
    for user in User.objects.all().iterator():
        ensure_default_categories(user, area_model=Area)


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0005_area_health_kind"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_default_categories, migrations.RunPython.noop),
    ]
