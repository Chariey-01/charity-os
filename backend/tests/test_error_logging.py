"""Unhandled server errors are logged, usefully and without secrets.

Before: with DEBUG = False (production) Django's console handler is off and
ADMINS is empty, so a 500's traceback was written nowhere (deployment-plan
L1). Now django.request and django.security errors go to stderr through
config.error_logging.RedactingFormatter.
"""

import io
import logging

import pytest
from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import path

from config.error_logging import redact


def boom(request):
    raise RuntimeError(
        "lookup failed for owner@example.com with password=hunter2 "
        'and {"token": "abc123secret"}'
    )


def fine(request):
    return HttpResponse("ok")


urlpatterns = [path("boom", boom), path("fine", fine)]


@pytest.fixture
def error_stream():
    handler = next(
        h for h in logging.getLogger("django.request").handlers if h.name == "errors"
    )
    stream = io.StringIO()
    previous = handler.setStream(stream)
    yield stream
    handler.setStream(previous)


@override_settings(ROOT_URLCONF=__name__)
def test_an_unhandled_error_is_logged_with_its_traceback(error_stream):
    response = Client(raise_request_exception=False).get("/boom?session=xyz789")

    output = error_stream.getvalue()
    assert response.status_code == 500
    assert "ERROR django.request Internal Server Error: /boom" in output
    assert "Traceback (most recent call last)" in output
    assert "RuntimeError: lookup failed for o***@example.com" in output
    assert "test_error_logging.py" in output  # the frame that raised


@override_settings(ROOT_URLCONF=__name__)
def test_the_logged_error_carries_no_secrets(error_stream):
    Client(raise_request_exception=False).get("/boom?session=xyz789")

    output = error_stream.getvalue()
    for secret in ("owner@example.com", "hunter2", "abc123secret", "xyz789"):
        assert secret not in output
    assert "password=[redacted]" in output
    assert '"token": "[redacted]"' in output


@override_settings(ROOT_URLCONF=__name__)
def test_successful_and_client_error_requests_add_no_error_lines(error_stream):
    client = Client(raise_request_exception=False)
    client.get("/fine")
    client.get("/missing")

    assert error_stream.getvalue() == ""


def test_django_security_errors_use_the_same_handler():
    handlers = logging.getLogger("django.security").handlers
    assert [h.name for h in handlers] == ["errors"]
    assert logging.getLogger("django.security").propagate is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Key (email)=(owner@example.com) already exists.",
            "Key (email)=(o***@example.com) already exists.",
        ),
        ("password=hunter2&next=/", "password=[redacted]&next=/"),
        (
            "Cookie: sessionid=abc; csrftoken=def",
            "Cookie: sessionid=[redacted]; csrftoken=[redacted]",
        ),
        ("'new_password': 'x1'", "'new_password': '[redacted]'"),
        (
            "Authorization: Bearer abc.def\nnext line",
            "Authorization: [redacted]\nnext line",
        ),
        ("Nothing sensitive at /api/v1/tasks", "Nothing sensitive at /api/v1/tasks"),
    ],
)
def test_redaction(raw, expected):
    assert redact(raw) == expected
