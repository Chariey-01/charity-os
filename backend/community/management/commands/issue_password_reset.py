from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from community.services import reset_link_parts


class Command(BaseCommand):
    help = (
        "Print a one-time password reset link for an account (valid for "
        "PASSWORD_RESET_TIMEOUT, 1 day). Send it to the person privately."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--site", default="https://charityos.charity-jk.workers.dev")

    def handle(self, *args, email, site, **options):
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            raise CommandError("No active account with that email.")
        uid, token = reset_link_parts(user)
        self.stdout.write(f"{site.rstrip('/')}/#/reset?uid={uid}&token={token}")
