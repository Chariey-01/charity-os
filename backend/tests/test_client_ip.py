"""The client address used for lockouts and the security log (config/proxies.py).

Review of Phase 0C: behind a reverse proxy every request has the proxy's
REMOTE_ADDR, so all users would share one lockout per email and one
attacker could keep any account locked for everyone. Forwarded headers are
trusted only from addresses listed in CHARITYOS_TRUSTED_PROXIES (empty by
default), and only the right-most address the trusted chain did not add is
used: everything to its left was written by the client and can be forged.
"""

import ipaddress
import logging

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from config.proxies import client_ip, parse_trusted_proxies

PROXY_NET = parse_trusted_proxies("10.0.0.0/8, fd00::/8")
behind_proxy = override_settings(CHARITYOS_TRUSTED_PROXIES=PROXY_NET)


def request(remote, forwarded=None):
    extra = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **extra)


def test_by_default_forwarded_headers_are_ignored():
    assert client_ip(request("203.0.113.5", "1.2.3.4")) == "203.0.113.5"


@behind_proxy
@pytest.mark.parametrize(
    ("remote", "forwarded", "expected"),
    [
        # The proxy appended the address it saw.
        ("10.0.0.2", "203.0.113.5", "203.0.113.5"),
        # The client forged a first entry; the proxy appended the real one.
        ("10.0.0.2", "1.2.3.4, 203.0.113.5", "203.0.113.5"),
        ("10.0.0.2", "10.9.9.9, 203.0.113.5", "203.0.113.5"),
        # Two trusted proxies in a row.
        ("10.0.0.2", "203.0.113.5, 10.0.0.3", "203.0.113.5"),
        # IPv6, with spaces the way proxies write them.
        ("fd00::2", "2001:db8::7 , fd00::3", "2001:db8::7"),
        # A connection that bypassed the proxy: its header is not believed.
        ("203.0.113.9", "1.2.3.4", "203.0.113.9"),
        # The proxy sent no header, or nothing usable: use the proxy address.
        ("10.0.0.2", None, "10.0.0.2"),
        ("10.0.0.2", "", "10.0.0.2"),
        ("10.0.0.2", "203.0.113.5:4433", "10.0.0.2"),
        ("10.0.0.2", "not-an-ip, 203.0.113.5", "203.0.113.5"),
        ("10.0.0.2", "203.0.113.5, garbage", "10.0.0.2"),
        # Every hop is ours: the left-most is the client inside our network.
        ("10.0.0.2", "10.0.0.7, 10.0.0.3", "10.0.0.7"),
    ],
)
def test_only_the_trusted_chain_is_believed(remote, forwarded, expected):
    assert client_ip(request(remote, forwarded)) == expected


def test_the_setting_is_parsed_strictly():
    assert parse_trusted_proxies("") == ()
    assert parse_trusted_proxies(" 10.0.0.1 , ::1 ") == (
        ipaddress.ip_network("10.0.0.1/32"),
        ipaddress.ip_network("::1/128"),
    )
    for bad in ("10.0.0.0/33", "proxy.internal", "10.0.0.1/8"):
        with pytest.raises(ImproperlyConfigured):
            parse_trusted_proxies(bad)


def test_trusting_everything_is_refused():
    for everything in ("0.0.0.0/0", "::/0"):
        with pytest.raises(ImproperlyConfigured):
            parse_trusted_proxies(everything)


PASSWORD = "correct-horse-battery-staple"


def browser(forwarded):
    client = APIClient(
        enforce_csrf_checks=True,
        REMOTE_ADDR="10.0.0.2",
        HTTP_X_FORWARDED_FOR=forwarded,
    )
    client.get("/api/v1/auth/csrf")
    return client


def login(client, password):
    return client.post(
        "/api/v1/auth/login",
        {"email": "owner@example.com", "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )


@pytest.mark.django_db
@behind_proxy
@override_settings(AXES_ENABLED=True)
def test_behind_the_proxy_one_attacker_does_not_lock_out_everyone(django_user_model):
    django_user_model.objects.create_user("owner@example.com", PASSWORD)
    attacker = browser("203.0.113.66")
    for _ in range(6):
        login(attacker, "nope")

    owner = login(browser("198.51.100.20"), PASSWORD)
    attacker_again = login(attacker, PASSWORD)

    assert owner.status_code == 200
    assert attacker_again.status_code == 429


@pytest.mark.django_db
@behind_proxy
@override_settings(AXES_ENABLED=True)
def test_forging_the_header_does_not_escape_the_lock(django_user_model):
    django_user_model.objects.create_user("owner@example.com", PASSWORD)
    # Each request forges a different first hop; the proxy appends the real one.
    statuses = [
        login(browser(f"192.0.2.{n}, 203.0.113.66"), "nope").status_code
        for n in range(7)
    ]

    assert statuses == [400] * 5 + [429] * 2


@pytest.mark.django_db
@behind_proxy
def test_the_security_log_records_the_client_not_the_proxy(django_user_model, caplog):
    caplog.set_level(logging.INFO, logger="charityos.security")
    django_user_model.objects.create_user("owner@example.com", PASSWORD)

    login(browser("1.2.3.4, 203.0.113.66"), "nope")

    [failure] = [r for r in caplog.records if r.name == "charityos.security"]
    assert "ip=203.0.113.0/24" in failure.getMessage()
    assert "10.0.0" not in failure.getMessage()
