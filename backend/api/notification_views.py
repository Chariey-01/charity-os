import hmac
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers
from rest_framework.decorators import (
    action,
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from notifications import ics
from notifications.models import PushSubscription, Reminder, ReminderDelivery
from notifications.services import (
    deliver,
    dispatch,
    next_due,
    push_configured,
    schedule,
    snooze,
)

from .archive import ArchivableMixin
from .serializers import OwnedModelSerializer
from .views import OwnedViewSet

# Push services Chrome, Firefox, Edge and Safari use. A subscription may only
# point at one of these, so the server never posts to arbitrary addresses.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
)


def allowed_push_endpoint(url):
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https":
        return False
    extra = tuple(getattr(settings, "CHARITYOS_EXTRA_PUSH_HOSTS", ()))
    return any(host == h or host.endswith("." + h) for h in (*PUSH_HOSTS, *extra))


@api_view(["GET"])
def push_config(request):
    return Response(
        {
            "configured": push_configured(),
            "public_key": settings.CHARITYOS_VAPID_PUBLIC_KEY or None,
        }
    )


class SubscriptionInput(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)
    keys = serializers.DictField(child=serializers.CharField(max_length=200))
    device_label = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_endpoint(self, value):
        if not allowed_push_endpoint(value):
            raise serializers.ValidationError("This is not a recognised push service.")
        return value

    def validate_keys(self, value):
        if not value.get("p256dh") or not value.get("auth"):
            raise serializers.ValidationError("Send the subscription's p256dh and auth keys.")
        return value


def _subscription(device):
    return {
        "id": str(device.pk),
        "device_label": device.device_label,
        "created_at": device.created_at,
        "last_success_at": device.last_success_at,
        "active": device.disabled_at is None,
    }


@api_view(["GET", "POST"])
def push_subscriptions(request):
    if request.method == "POST":
        data = SubscriptionInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        with transaction.atomic():
            # One browser has one endpoint. If another account signed in on it
            # before, the endpoint now belongs to whoever subscribed last.
            device, _ = PushSubscription.objects.update_or_create(
                endpoint=values["endpoint"],
                defaults={
                    "user": request.user,
                    "p256dh": values["keys"]["p256dh"],
                    "auth": values["keys"]["auth"],
                    "device_label": values.get("device_label", "")[:120],
                    "disabled_at": None,
                    "failure_count": 0,
                },
            )
        return Response(_subscription(device), status=201)
    devices = PushSubscription.objects.filter(user=request.user).order_by("-created_at")
    return Response([_subscription(device) for device in devices])


@api_view(["POST"])
def push_unsubscribe(request):
    endpoint = str(request.data.get("endpoint", ""))
    device_id = str(request.data.get("id", ""))
    devices = PushSubscription.objects.filter(user=request.user)
    if endpoint:
        devices = devices.filter(endpoint=endpoint)
    elif device_id:
        devices = devices.filter(pk=device_id)
    else:
        raise serializers.ValidationError({"endpoint": ["Send the endpoint or id to remove."]})
    # A subscription is a device address, not history: removing it is safe.
    removed, _ = devices.delete()
    return Response({"removed": removed})


@api_view(["POST"])
def push_test(request):
    if not push_configured():
        return Response(
            {
                "error": {
                    "code": "push_not_configured",
                    "message": "Notifications are not set up on this server yet.",
                }
            },
            status=503,
        )
    now = timezone.now()
    delivery = deliver(
        request.user,
        key=f"test:{now.isoformat()}",
        title="CharityOS notifications work",
        body="You will get reminders like this one, even when the app is closed.",
        link="#/profile/notifications",
        due_at=now,
        now=now,
    )
    return Response(
        {"status": delivery.status if delivery else "duplicate", "devices": delivery.devices if delivery else 0}
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def push_snooze(request):
    """Called by the service worker from a notification's Snooze button."""
    minutes = request.data.get("minutes", 10)
    if not isinstance(minutes, int) or not 1 <= minutes <= 240:
        minutes = 10
    reminder = snooze(str(request.data.get("token", "")), minutes=minutes)
    if reminder is None:
        return Response({"error": {"code": "invalid_token", "message": "This reminder can no longer be snoozed."}}, status=400)
    return Response({"snoozed_until": reminder.next_fire_at})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def dispatch_view(request):
    """The scheduler's entry point (Cloudflare cron trigger). Secret-protected."""
    expected = settings.CHARITYOS_CRON_SECRET
    given = request.headers.get("X-CharityOS-Cron-Secret", "")
    if not expected or len(expected) < 32 or not hmac.compare_digest(given, expected):
        return Response({"error": {"code": "forbidden", "message": "Forbidden."}}, status=403)
    sent = dispatch()
    return Response({"sent": sent, "next_due_at": next_due()})


class ReminderSerializer(OwnedModelSerializer):
    class Meta:
        model = Reminder
        fields = "__all__"
        read_only_fields = ("user", "next_fire_at", "last_fired_at")
        extra_kwargs = {"timezone_name": {"required": False}}

    def validate_weekdays(self, value):
        if not isinstance(value, list) or any(not isinstance(day, int) or not 1 <= day <= 7 for day in value):
            raise serializers.ValidationError("Use ISO weekdays 1 (Monday) to 7 (Sunday).")
        return sorted(set(value))

    def validate_link(self, value):
        if value and not value.startswith("#/"):
            raise serializers.ValidationError("Use an in-app link such as #/goals.")
        return value

    def validate_timezone_name(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("Use an IANA timezone.") from exc
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if not attrs.get("timezone_name") and self.instance is None:
            attrs["timezone_name"] = user.timezone

        def merged(field):
            return attrs.get(field, getattr(self.instance, field, None))

        repeat = merged("repeat") or Reminder.Repeat.ONCE
        if repeat == Reminder.Repeat.ONCE and not merged("local_date"):
            raise serializers.ValidationError({"local_date": ["Choose the day."]})
        if repeat == Reminder.Repeat.WEEKLY and not merged("weekdays"):
            raise serializers.ValidationError({"weekdays": ["Choose at least one day."]})
        return super().validate(attrs)


class ReminderViewSet(ArchivableMixin, OwnedViewSet):
    queryset = Reminder.objects.all()
    serializer_class = ReminderSerializer

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by("enabled", "next_fire_at", "local_time")

    def perform_create(self, serializer):
        with transaction.atomic():
            reminder = serializer.save(user=self.request.user)
            schedule(reminder).save(update_fields=("next_fire_at",))

    def perform_update(self, serializer):
        with transaction.atomic():
            reminder = serializer.save()
            schedule(reminder).save(update_fields=("next_fire_at",))

    def archive_service(self, user, instance):
        reminder = super().archive_service(user, instance)
        schedule(reminder).save(update_fields=("next_fire_at",))
        return reminder

    def restore_service(self, user, instance):
        reminder = super().restore_service(user, instance)
        schedule(reminder).save(update_fields=("next_fire_at",))
        return reminder

    @action(detail=False, methods=["get"])
    def deliveries(self, request):
        rows = ReminderDelivery.objects.filter(user=request.user).order_by("-created_at")[:30]
        return Response(
            [
                {
                    "id": str(row.pk),
                    "title": row.title,
                    "due_at": row.due_at,
                    "status": row.status,
                    "devices": row.devices,
                }
                for row in rows
            ]
        )


@api_view(["GET", "POST", "DELETE"])
def calendar_feed(request):
    if request.method == "POST":
        token = ics.issue_feed(request.user)
        return Response({"active": True, "path": f"/api/v1/calendar/{token}.ics"}, status=201)
    if request.method == "DELETE":
        ics.revoke_feed(request.user)
        return Response({"active": False})
    return Response({"active": hasattr(request.user, "calendar_feed")})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def calendar_ics(request, token):
    user = ics.user_for_token(token)
    if user is None:
        return HttpResponse("Not found", status=404, content_type="text/plain")
    response = HttpResponse(ics.build_feed(user), content_type="text/calendar; charset=utf-8")
    response["Cache-Control"] = "private, max-age=900"
    response["Content-Disposition"] = 'inline; filename="charityos.ics"'
    return response

