"""Reminders, Web Push delivery, snooze, the scheduler hook and the .ics feed."""

import base64
import json
from datetime import UTC, date, datetime, time, timedelta

import http_ece
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from growth.models import Goal
from notifications import services
from notifications.models import PushSubscription, Reminder, ReminderDelivery
from planning.models import Task
from users.models import UserPreferences

pytestmark = pytest.mark.django_db
API = "/api/v1"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-a"


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture
def user():
    return get_user_model().objects.create_user("me@example.com", "pw", timezone="Africa/Nairobi")


@pytest.fixture
def other():
    return get_user_model().objects.create_user("them@example.com", "pw", timezone="UTC")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def reminder(user, **values):
    data = {
        "user": user,
        "title": "Study RAG",
        "local_time": time(7, 30),
        "timezone_name": "Africa/Nairobi",
        "repeat": "daily",
    }
    data.update(values)
    return services.schedule(Reminder(**data))


def test_next_fire_respects_the_local_timezone_and_repeat():
    base = datetime(2026, 11, 27, 5, 0, tzinfo=UTC)  # 08:00 in Nairobi, a Friday
    daily = reminder(None, repeat="daily")
    assert services.next_fire(daily, base) == datetime(2026, 11, 28, 4, 30, tzinfo=UTC)
    weekly = reminder(None, repeat="weekly", weekdays=[1])
    assert services.next_fire(weekly, base) == datetime(2026, 11, 30, 4, 30, tzinfo=UTC)
    once_past = reminder(None, repeat="once", local_date=date(2026, 11, 27))
    assert services.next_fire(once_past, base) is None
    london = reminder(None, repeat="daily", timezone_name="Europe/London", local_time=time(7, 30))
    # Across the end of British Summer Time, 07:30 local stays 07:30 local.
    before = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    assert services.next_fire(london, before) == datetime(2026, 10, 25, 7, 30, tzinfo=UTC)


def test_dispatch_sends_once_even_when_run_twice(user):
    now = datetime(2026, 11, 27, 4, 31, tzinfo=UTC)
    item = reminder(user, repeat="once", local_date=date(2026, 11, 27))
    item.next_fire_at = datetime(2026, 11, 27, 4, 30, tzinfo=UTC)
    item.save()
    PushSubscription.objects.create(user=user, endpoint=ENDPOINT, p256dh="k", auth="a")
    sent = []

    def sender(device, payload):
        sent.append(payload)
        return True

    assert services.dispatch(now=now, sender=sender) == 1
    assert services.dispatch(now=now, sender=sender) == 0
    assert len(sent) == 1
    assert sent[0]["title"] == "Study RAG"
    assert sent[0]["snooze"]
    item.refresh_from_db()
    assert item.enabled is False and item.next_fire_at is None
    delivery = ReminderDelivery.objects.get()
    assert delivery.status == "sent" and delivery.devices == 1


def test_a_late_reminder_is_skipped_not_sent_hours_later(user):
    item = reminder(user, repeat="daily")
    item.next_fire_at = datetime(2026, 11, 27, 4, 30, tzinfo=UTC)
    item.save()
    PushSubscription.objects.create(user=user, endpoint=ENDPOINT, p256dh="k", auth="a")
    sent = []
    services.dispatch(now=datetime(2026, 11, 27, 9, 0, tzinfo=UTC), sender=lambda d, p: sent.append(p) or True)
    assert sent == []
    assert ReminderDelivery.objects.get().status == "skipped"
    item.refresh_from_db()
    assert item.next_fire_at == datetime(2026, 11, 28, 4, 30, tzinfo=UTC)


def test_gone_subscriptions_are_disabled_and_no_device_is_recorded(user):
    now = timezone.now()
    device = PushSubscription.objects.create(user=user, endpoint=ENDPOINT, p256dh="k", auth="a")
    services.deliver(user, key="k1", title="t", body="", link="", due_at=now, now=now, sender=lambda d, p: None)
    device.refresh_from_db()
    assert device.disabled_at is not None
    delivery = services.deliver(user, key="k2", title="t", body="", link="", due_at=now, now=now)
    assert delivery.status == "no_device"


def test_preference_reminders_for_activities_about_to_start(user):
    from planning.models import Area
    from scheduling.models import ScheduleEntry

    prefs, _ = UserPreferences.objects.get_or_create(user=user)
    prefs.reminders_enabled = True
    prefs.reminder_lead_minutes = 10
    prefs.save()
    PushSubscription.objects.create(user=user, endpoint=ENDPOINT, p256dh="k", auth="a")
    area = Area.objects.create(user=user, name="Learning", slug="learning")
    start = datetime(2026, 11, 27, 6, 0, tzinfo=UTC)
    ScheduleEntry.objects.create(
        user=user,
        title="Deep work: RAG",
        area=area,
        start_at=start,
        end_at=start + timedelta(hours=1),
        local_date=date(2026, 11, 27),
        timezone_name="Africa/Nairobi",
    )
    sent = []
    services.dispatch(now=start - timedelta(minutes=9), sender=lambda d, p: sent.append(p) or True)
    services.dispatch(now=start - timedelta(minutes=5), sender=lambda d, p: sent.append(p) or True)
    assert [p["title"] for p in sent] == ["Deep work: RAG"]
    assert sent[0]["body"] == "Starts at 09:00"


def test_subscriptions_are_owned_and_only_known_push_services_are_accepted(client, user, other):
    bad = client.post(
        f"{API}/push/subscriptions",
        {"endpoint": "https://attacker.example/x", "keys": {"p256dh": "k", "auth": "a"}},
        format="json",
    )
    assert bad.status_code == 400
    ok = client.post(
        f"{API}/push/subscriptions",
        {"endpoint": ENDPOINT, "keys": {"p256dh": "k", "auth": "a"}, "device_label": "Android"},
        format="json",
    )
    assert ok.status_code == 201
    other_client = APIClient()
    other_client.force_authenticate(other)
    assert other_client.get(f"{API}/push/subscriptions").data == []
    removed = other_client.post(f"{API}/push/unsubscribe", {"endpoint": ENDPOINT}, format="json")
    assert removed.data["removed"] == 0
    assert PushSubscription.objects.filter(user=user).count() == 1


def test_reminder_api_validates_and_schedules(client, other):
    missing = client.post(f"{API}/reminders", {"title": "x", "local_time": "07:30", "repeat": "weekly"}, format="json")
    assert missing.status_code == 400
    bad_link = client.post(
        f"{API}/reminders",
        {"title": "x", "local_time": "07:30", "repeat": "daily", "link": "https://evil.example"},
        format="json",
    )
    assert bad_link.status_code == 400
    created = client.post(
        f"{API}/reminders",
        {"title": "Weekly review", "local_time": "18:00", "repeat": "weekly", "weekdays": [7], "link": "#/insights/review"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["timezone_name"] == "Africa/Nairobi"
    assert created.data["next_fire_at"] is not None
    rid = created.data["id"]
    off = client.patch(f"{API}/reminders/{rid}", {"enabled": False}, format="json")
    assert off.data["next_fire_at"] is None
    assert client.delete(f"{API}/reminders/{rid}").status_code == 405
    other_client = APIClient()
    other_client.force_authenticate(other)
    assert other_client.get(f"{API}/reminders/{rid}").status_code == 404


def test_snooze_needs_a_valid_token_and_creates_a_one_off_reminder(user):
    now = timezone.now()
    PushSubscription.objects.create(user=user, endpoint=ENDPOINT, p256dh="k", auth="a")
    captured = []
    services.deliver(user, key="k", title="Stretch", body="", link="#/today", due_at=now, now=now, sender=lambda d, p: captured.append(p) or True)
    anonymous = APIClient()
    assert anonymous.post(f"{API}/push/snooze", {"token": "forged"}, format="json").status_code == 400
    response = anonymous.post(f"{API}/push/snooze", {"token": captured[0]["snooze"], "minutes": 15}, format="json")
    assert response.status_code == 200
    snoozed = Reminder.objects.get(user=user, title="Stretch")
    assert snoozed.repeat == "once" and snoozed.link == "#/today"
    assert abs((snoozed.next_fire_at - now) - timedelta(minutes=15)) < timedelta(minutes=2)


def test_dispatch_endpoint_requires_the_cron_secret(settings):
    anonymous = APIClient()
    settings.CHARITYOS_CRON_SECRET = ""
    assert anonymous.post(f"{API}/internal/reminders/dispatch").status_code == 403
    settings.CHARITYOS_CRON_SECRET = "s" * 40
    assert anonymous.post(f"{API}/internal/reminders/dispatch", HTTP_X_CHARITYOS_CRON_SECRET="wrong").status_code == 403
    ok = anonymous.post(f"{API}/internal/reminders/dispatch", HTTP_X_CHARITYOS_CRON_SECRET="s" * 40)
    assert ok.status_code == 200 and ok.data["sent"] == 0
    # Nothing scheduled: the scheduler may wait up to six hours.
    assert ok.data["next_due_at"] > timezone.now() + timedelta(hours=5)


def test_next_due_is_the_earliest_reminder(user):
    now = datetime(2026, 11, 27, 5, 0, tzinfo=UTC)
    item = reminder(user, repeat="daily", local_time=time(9, 0))
    services.schedule(item, now=now).save()
    assert services.next_due(now) == datetime(2026, 11, 27, 6, 0, tzinfo=UTC)


def test_web_push_payload_is_encrypted_for_the_device_and_signed(user, settings, monkeypatch):
    """A real pywebpush round trip: the captured request decrypts with the
    device's key, and carries a VAPID signature for our public key."""
    from io import StringIO

    out = StringIO()
    call_command("generate_vapid_keys", stdout=out)
    keys = dict(line.split("=", 1) for line in out.getvalue().split())
    settings.CHARITYOS_VAPID_PUBLIC_KEY = keys["CHARITYOS_VAPID_PUBLIC_KEY"]
    settings.CHARITYOS_VAPID_PRIVATE_KEY = keys["CHARITYOS_VAPID_PRIVATE_KEY"]
    device_key = ec.generate_private_key(ec.SECP256R1())
    device_public = device_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth_secret = b"0123456789abcdef"
    device = PushSubscription.objects.create(
        user=user, endpoint=ENDPOINT, p256dh=b64(device_public), auth=b64(auth_secret)
    )
    captured = {}

    class Reply:
        status_code = 201
        text = ""
        headers = {}

    def fake_post(self, url, data=None, headers=None, timeout=None, **kwargs):
        captured.update(url=url, data=data, headers=headers)
        return Reply()

    monkeypatch.setattr(requests.Session, "post", fake_post, raising=False)
    monkeypatch.setattr(requests, "post", lambda url, **kw: fake_post(None, url, **kw))
    assert services.send_push(device, {"title": "Hello"}) is True
    assert captured["url"] == ENDPOINT
    plain = http_ece.decrypt(
        captured["data"], private_key=device_key, auth_secret=auth_secret, version="aes128gcm"
    )
    assert json.loads(plain) == {"title": "Hello"}
    assert keys["CHARITYOS_VAPID_PUBLIC_KEY"] in captured["headers"]["Authorization"]


def test_calendar_feed_is_private_revocable_and_escaped(client, user, other):
    Task.objects.create(user=user, title="Pitch, deck; v2", due_date=date(2026, 12, 3))
    Goal.objects.create(user=user, title="Ship it", target_date=date(2027, 1, 31))
    Task.objects.create(user=other, title="Someone else's task", due_date=date(2026, 12, 3))
    path = client.post(f"{API}/calendar/feed").data["path"]
    anonymous = APIClient()
    body = anonymous.get(path).content.decode()
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert "SUMMARY:Due: Pitch\\, deck\\; v2" in body
    assert "Goal target: Ship it" in body
    assert "Someone else" not in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    rotated = client.post(f"{API}/calendar/feed").data["path"]
    assert anonymous.get(path).status_code == 404
    client.delete(f"{API}/calendar/feed")
    assert anonymous.get(rotated).status_code == 404


def test_erase_user_removes_notification_records(user, client):
    PushSubscription.objects.create(user=user, endpoint=ENDPOINT, p256dh="k", auth="a")
    now = timezone.now()
    item = reminder(user)
    item.save()
    services.deliver(user, key="x", title="t", body="", link="", due_at=now, reminder=item, now=now)
    client.post(f"{API}/calendar/feed")
    call_command("erase_user", user.email, "--confirm", user.email)
    assert not Reminder.objects.exists() and not ReminderDelivery.objects.exists()
    assert not PushSubscription.objects.exists()
