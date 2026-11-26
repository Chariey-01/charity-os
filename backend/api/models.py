from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class IdempotencyKey(models.Model):
    """The answer to one create, kept briefly so a retry can be replayed.

    See api/idempotency.py. Rows hold a copy of the created record as it was
    returned, so they are personal data: they are purged 24 hours after use
    and deleted with the account.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    key = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=255)
    fingerprint = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"], name="idempotency_key_once_per_user"
            )
        ]

    def __str__(self):
        return f"{self.method} {self.path} ({self.created_at:%Y-%m-%d %H:%M})"
