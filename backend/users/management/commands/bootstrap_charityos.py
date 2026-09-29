from datetime import date, timedelta
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from challenges.models import Challenge
from planning.models import Area

DEFAULT_AREAS = (
    "Software Engineering",
    "Computer Science",
    "AI",
    "Career",
    "Freelancing",
    "Projects",
    "Reading",
    "Exercise",
    "Nutrition",
    "Recovery",
    "Personal",
    "Reflection",
)


class Command(BaseCommand):
    help = "Safely create a local user, challenge, and default areas."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--display-name", default="")
        parser.add_argument("--timezone", default="UTC")
        parser.add_argument("--challenge-name", default="My 96-Day Challenge")
        parser.add_argument(
            "--password-env", help="Read the password from this environment variable"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        import os

        User = get_user_model()
        if User.objects.filter(email__iexact=options["email"]).exists():
            raise CommandError("A user with this email already exists.")
        password = (
            os.environ.get(options["password_env"], "")
            if options["password_env"]
            else getpass("Local user password: ")
        )
        if not password:
            raise CommandError("A non-empty password is required.")
        user = User.objects.create_user(
            options["email"],
            password,
            display_name=options["display_name"],
            timezone=options["timezone"],
        )
        for order, name in enumerate(DEFAULT_AREAS):
            Area.objects.create(
                user=user, name=name, slug=slugify(name), sort_order=order
            )
        today = date.today()
        Challenge.objects.create(
            user=user,
            name=options["challenge_name"],
            start_date=today,
            end_date=today + timedelta(days=95),
            status=Challenge.Status.ACTIVE,
            is_primary=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {user.email} with a 96-day challenge and {len(DEFAULT_AREAS)} areas."
            )
        )
