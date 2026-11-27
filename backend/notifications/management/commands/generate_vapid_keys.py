import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Command(BaseCommand):
    help = (
        "Print a new VAPID key pair for Web Push. Store the private key as a "
        "secret (CHARITYOS_VAPID_PRIVATE_KEY); the public key is not secret "
        "(CHARITYOS_VAPID_PUBLIC_KEY). Changing keys unsubscribes every device."
    )

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, "big")
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.stdout.write(f"CHARITYOS_VAPID_PUBLIC_KEY={b64(public)}")
        self.stdout.write(f"CHARITYOS_VAPID_PRIVATE_KEY={b64(private)}")
