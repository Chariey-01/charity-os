from django.core.management.base import BaseCommand

from notifications.services import dispatch


class Command(BaseCommand):
    help = (
        "Send every reminder that is due. Safe to run repeatedly and "
        "concurrently; run it every few minutes from any scheduler."
    )

    def handle(self, *args, **options):
        sent = dispatch()
        self.stdout.write(f"Sent {sent} reminder(s).")
