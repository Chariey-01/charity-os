from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Let an account create beta invites, see feedback and make password "
        "reset links (sets is_staff; grants no Django admin permissions)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--revoke", action="store_true")

    def handle(self, *args, email, revoke, **options):
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError("No account with that email.")
        user.is_staff = not revoke
        user.save(update_fields=("is_staff",))
        self.stdout.write(("Removed" if revoke else "Granted") + " beta admin for the account.")
