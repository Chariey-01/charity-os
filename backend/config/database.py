"""Which PostgreSQL server production connects to.

Development, the tests and the ``ops/db`` scripts name the server with the five
``POSTGRES_*`` variables. A hosting platform hands over one ``DATABASE_URL``
instead (Render's ``fromDatabase`` ``connectionString``), so production also
accepts that, but **never both at once**: with two sources a ``manage.py`` step
could reach a different server from the one the operator meant. The ``ops/db``
scripts refuse to run while ``DATABASE_URL`` is set for the same reason.

Accepted options: ``sslmode``, ``channel_binding`` and ``sslrootcert=system``
(Neon's connection strings use the first two; ``verify-full`` needs the third
so libpq checks the server against the system's certificate authorities).

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
CHANNEL_BINDING = frozenset({"disable", "prefer", "require"})
# A file path here could be anything on the host; only the system's CA store.
SSL_ROOT_CERTS = frozenset({"system"})


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
    allowed = {
        "sslmode": SSL_MODES,
        "channel_binding": CHANNEL_BINDING,
        "sslrootcert": SSL_ROOT_CERTS,
    }
    unknown = sorted(set(query) - set(allowed))
    if unknown:
        raise ImproperlyConfigured(
            "DATABASE_URL has unsupported options: " + ", ".join(unknown) + "."
        )
    options = {}
    for option, values in allowed.items():
        if option in query:
            value = query[option][-1]
            if value not in values:
                raise ImproperlyConfigured(f"DATABASE_URL has an unknown {option}.")
            options[option] = value
    fields = {
        "NAME": name,
        "USER": unquote(parts.username),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname,
        "PORT": str(port or 5432),
        "OPTIONS": options,
    }
    # Neon's pooled endpoint (PgBouncer in transaction mode) has "-pooler" in
    # its host name; server-side cursors do not survive transaction pooling.
    if "-pooler." in parts.hostname:
        fields["DISABLE_SERVER_SIDE_CURSORS"] = True
    return fields


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
