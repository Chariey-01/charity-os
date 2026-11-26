"""Logging helpers: production error lines that are useful but not leaky.

With ``DEBUG = False`` Django's own console handler is switched off and
``mail_admins`` has no ``ADMINS`` to write to, so without a handler of our
own an unhandled exception's traceback was written nowhere. ``LOGGING`` in
settings routes ``django.request`` and ``django.security`` errors to stderr
through ``RedactingFormatter``.

What a line contains: time, level, logger, Django's message (for a request
error that is the path, never the query string) and the traceback. Python
tracebacks show code lines, not local variable values. Exception messages
can still carry data (a database error repeats the conflicting value), so the
formatted text is redacted before it is written:

* email addresses become ``c***@example.com`` (as in the security log);
* values of password, token, secret, session, CSRF and API-key keys, and an
  Authorization header's whole value, become ``[redacted]``.
"""

import logging
import re

EMAIL = re.compile(
    r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)
# key=value, key: value, "key": "value" and key=(value) for sensitive keys.
SECRET = re.compile(
    r"""(?ix)
    (\b[\w-]*(?:password|passwd|secret|token|sessionid|session_key|csrf[\w-]*|api[_-]?key)[\w-]*\b
      ["']?\s*[:=]\s*\(?["']?)
    ([^"'\s,;)&]+)
    """
)


# An Authorization header's whole value ("Bearer <token>") to the end of the line.
AUTHORIZATION = re.compile(r"(?i)(\bauthorization\s*[:=]\s*)[^\n]+")


def redact(text):
    text = EMAIL.sub(lambda match: f"{match.group(1)}***@{match.group(2)}", text)
    text = AUTHORIZATION.sub(lambda match: f"{match.group(1)}[redacted]", text)
    return SECRET.sub(lambda match: f"{match.group(1)}[redacted]", text)


class RedactingFormatter(logging.Formatter):
    """A ``logging.Formatter`` whose whole output, traceback included, is redacted."""

    def format(self, record):
        return redact(super().format(record))
