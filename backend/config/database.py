"""Which PostgreSQL server production connects to.

Development, the tests and the ``ops/db`` scripts name the server with the five
``POSTGRES_*`` variables. A hosting platform hands over one ``DATABASE_URL``
instead (Render's ``fromDatabase`` ``connectionString``), so production also
accepts that, but **never both at once**: with two sources a ``manage.py`` step
could reach a different server from the one the operator meant. The ``ops/db``
scripts refuse to run while ``DATABASE_URL`` is set for the same reason.

Error messages never repeat the URL: it contains the database password.
"""

from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

POSTGRES_VARIABLES = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)
SSL_MODES = frozenset(
    {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)


def parse_database_url(url):
    """Return Django ``DATABASES`` fields for a ``postgres(ql)://`` URL."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(
            "DATABASE_URL must start with postgres:// or postgresql://."
        )
    try:
        port = parts.port
    except ValueError as error:
        raise ImproperlyConfigured("DATABASE_URL has an invalid port.") from error
    name = unquote(parts.path.removeprefix("/"))
    if not parts.hostname or not parts.username or not name or "/" in name:
        raise ImproperlyConfigured(
            "DATABASE_URL must name a user, a host and one database."
        )
    query = parse_qs(parts.query, keep_blank_values=True)
    unknown = sorted(set(query) - {"sslmode"})
    if unknown:
        raise ImproperlyConfigured(
            "DATABASE_URL has unsupported options: " + ", ".join(unknown) + "."
        )
    options = {}
    if "sslmode" in query:
        mode = query["sslmode"][-1]
        if mode not in SSL_MODES:
            raise ImproperlyConfigured("DATABASE_URL has an unknown sslmode.")
        options["sslmode"] = mode
    return {
        "NAME": name,
        "USER": unquote(parts.username),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname,
        "PORT": str(port or 5432),
        "OPTIONS": options,
    }


def database_from_url(environ):
    """``DATABASE_URL``'s fields, or ``None`` when it is not set.

    Refuses when any ``POSTGRES_*`` variable is set as well.
    """
    url = environ.get("DATABASE_URL", "").strip()
    if not url:
        return None
    clashing = [name for name in POSTGRES_VARIABLES if environ.get(name)]
    if clashing:
        raise ImproperlyConfigured(
            "DATABASE_URL and " + ", ".join(clashing) + " are both set. Set only "
            "one of them, so every command reaches the same database server."
        )
    return parse_database_url(url)
