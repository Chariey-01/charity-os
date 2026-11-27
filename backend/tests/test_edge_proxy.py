"""Behind Cloudflare, only the Worker's requests are answered and its visitor
address is believed (config/edge_proxy.py)."""

import logging

import pytest
from django.core.exceptions import ImproperlyConfigured, MiddlewareNotUsed
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from config.edge_proxy import EdgeProxyMiddleware, validate_secret

SECRET = "Yb7Kq2Lm9Nv4Rx8Tz1Wc6Pd3Hf5Js0Ga-Ue_Io7By2"
EMAIL = "owner@example.com"
PASSWORD = "Sup3r-secret-passw0rd"
edge_on = override_settings(CHARITYOS_EDGE_PROXY_SECRET=SECRET)


def seen_by_view(request):
    response = HttpResponse("ok")
    response.remote_addr = request.META.get("REMOTE_ADDR")
    response.leaked = [
        key for key in request.META if key.startswith("HTTP_X_CHARITYOS_")
    ]
    return response


def gate(**headers):
    with edge_on:
        middleware = EdgeProxyMiddleware(seen_by_view)
    request = RequestFactory().get("/api/v1/me", REMOTE_ADDR="10.1.2.3", **headers)
    return middleware(request)


def test_off_without_a_secret():
    with override_settings(CHARITYOS_EDGE_PROXY_SECRET=""):
        with pytest.raises(MiddlewareNotUsed):
            EdgeProxyMiddleware(seen_by_view)


@pytest.mark.parametrize("secret", ["short", "a" * 64, "ab" * 20])
def test_a_guessable_secret_is_refused(secret):
    with pytest.raises(ImproperlyConfigured) as error:
        validate_secret(secret)
    assert secret not in str(error.value)


def test_requests_without_the_secret_are_refused():
    for headers in (
        {},
        {"HTTP_X_CHARITYOS_EDGE_SECRET": "guess"},
        {"HTTP_X_CHARITYOS_EDGE_SECRET": SECRET[:-1]},
        {"HTTP_X_CHARITYOS_CLIENT_IP": "203.0.113.9"},
    ):
        response = gate(**headers)
        assert response.status_code == 403, headers
        assert b"edge_only" in response.content


def test_the_workers_visitor_address_replaces_the_proxy_address():
    response = gate(
        HTTP_X_CHARITYOS_EDGE_SECRET=SECRET, HTTP_X_CHARITYOS_CLIENT_IP="196.201.214.7"
    )
    assert response.status_code == 200
    assert response.remote_addr == "196.201.214.7"
    assert response.leaked == []  # neither header reaches views or logs


@pytest.mark.parametrize("claimed", ["", "not-an-ip", "196.201.214.7, 10.0.0.1"])
def test_an_unusable_visitor_address_keeps_the_connection_address(claimed):
    response = gate(
        HTTP_X_CHARITYOS_EDGE_SECRET=SECRET, HTTP_X_CHARITYOS_CLIENT_IP=claimed
    )
    assert response.status_code == 200
    assert response.remote_addr == "10.1.2.3"


# ---------------------------------------------------------- through Django


def worker_client(visitor="196.201.214.7"):
    """A browser-like client whose requests arrive through the Worker."""
    client = APIClient(
        enforce_csrf_checks=True,
        REMOTE_ADDR="104.16.0.1",  # Cloudflare's side of the connection
        HTTP_X_CHARITYOS_EDGE_SECRET=SECRET,
        HTTP_X_CHARITYOS_CLIENT_IP=visitor,
    )
    client.get("/api/v1/auth/csrf")
    return client


def sign_in(client, password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        {"email": EMAIL, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )


@pytest.mark.django_db
@edge_on
def test_the_health_probe_still_answers_the_platform():
    assert APIClient().get("/api/v1/health").status_code == 200


@pytest.mark.django_db
@edge_on
def test_direct_requests_cannot_sign_in(django_user_model, caplog):
    django_user_model.objects.create_user(EMAIL, PASSWORD)
    caplog.set_level(logging.INFO, logger="charityos.security")
    direct = APIClient(REMOTE_ADDR="203.0.113.9")

    response = direct.post(
        "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD}, format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "edge_only"
    [record] = [r for r in caplog.records if "edge_secret_rejected" in r.getMessage()]
    assert "secret_sent=no" in record.getMessage()
    assert "ip=203.0.113.0/24" in record.getMessage()


@pytest.mark.django_db
@edge_on
def test_sign_in_through_the_worker_works_and_logs_the_visitor(
    django_user_model, caplog
):
    django_user_model.objects.create_user(EMAIL, PASSWORD)
    caplog.set_level(logging.INFO, logger="charityos.security")
    client = worker_client()

    assert sign_in(client).status_code == 200
    assert client.get("/api/v1/me").json()["email"] == EMAIL

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=login_succeeded" in text
    assert "ip=196.201.214.0/24" in text  # the visitor, not Cloudflare
    assert "104.16.0" not in text
    assert SECRET not in text


@pytest.mark.django_db
@edge_on
@override_settings(AXES_ENABLED=True)
def test_lockouts_count_per_visitor_not_per_cloudflare_address(django_user_model):
    django_user_model.objects.create_user(EMAIL, PASSWORD)
    attacker = worker_client(visitor="203.0.113.9")
    for _ in range(6):
        sign_in(attacker, password="Wr0ng-guess-123")
    assert sign_in(attacker).status_code == 429

    # The owner reaches Django through the same Cloudflare address.
    assert sign_in(worker_client(visitor="196.201.214.7")).status_code == 200
