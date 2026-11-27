from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from community.services import create_invite


class Command(BaseCommand):
    help = "Create a beta invite code (shown once). The app's Beta admin screen does the same."

    def add_arguments(self, parser):
        parser.add_argument("--by", required=True, help="Email of the beta admin creating it")
        parser.add_argument("--for-email", default="", help="Only this email may use it")
        parser.add_argument("--note", default="")
        parser.add_argument("--uses", type=int, default=1)
        parser.add_argument("--days", type=int, default=14)

    def handle(self, *args, **options):
        admin = get_user_model().objects.filter(email__iexact=options["by"], is_staff=True).first()
        if admin is None:
            raise CommandError("--by must be a beta admin (manage.py grant_beta_admin).")
        invite, code = create_invite(
            created_by=admin,
            email=options["for_email"],
            note=options["note"],
            max_uses=options["uses"],
            days=options["days"],
        )
        self.stdout.write(f"Invite code: {code} (expires {invite.expires_at:%Y-%m-%d})")
