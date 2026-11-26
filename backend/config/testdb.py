"""Name the pytest database so checkouts never share or clobber one.

pytest-django creates the test database at the start of a run and, when one
with the same name already exists, silently drops and recreates it. A single
shared name (the old ``test_charityos``) therefore let one checkout wipe
another's database mid-run and let schema from one branch leak into another
branch's tests through ``--reuse-db``.

Each checkout now gets ``test_charityos_<hash of the checkout path>``. An
explicit ``CHARITYOS_TEST_DB`` overrides it, for example to run two suites in
the same checkout at once. Unsafe names are refused before any database is
created or dropped.
"""

import hashlib
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

OVERRIDE_VARIABLE = "CHARITYOS_TEST_DB"
# The old shared name. Other sessions may still hold data in it; never reuse it.
PROTECTED_NAMES = frozenset({"test_charityos"})
# Reserved for the legacy shared database, every checkout's automatic name and
# databases other sessions created (e.g. test_charityos_p2). An override in this
# namespace could make pytest-django drop one of them, so overrides may not use it.
RESERVED_PREFIX = "test_charityos"
VALID_NAME = re.compile(r"^test_[a-z0-9_]{1,58}$")


def default_test_database_name(checkout_dir):
    resolved = str(Path(checkout_dir).resolve())
    return "test_charityos_" + hashlib.sha256(resolved.encode()).hexdigest()[:10]


def test_database_name(checkout_dir, environ, main_database_name):
    """Return the test database name for ``checkout_dir`` or raise.

    ``environ`` is the process environment; ``main_database_name`` is the
    database the settings point at, which a test run must never replace.
    """
    name = environ.get(OVERRIDE_VARIABLE) or default_test_database_name(checkout_dir)
    if not VALID_NAME.fullmatch(name):
        raise ImproperlyConfigured(
            f"Test database name {name!r} must start with 'test_' and use only "
            "lowercase letters, digits and underscores (at most 63 characters)."
        )
    if name in PROTECTED_NAMES:
        raise ImproperlyConfigured(
            f"Refusing to use the shared test database {name!r}. Unset "
            f"{OVERRIDE_VARIABLE} to get this checkout's own test database."
        )
    if environ.get(OVERRIDE_VARIABLE) and name.startswith(RESERVED_PREFIX):
        raise ImproperlyConfigured(
            f"{OVERRIDE_VARIABLE}={name!r} is in the reserved {RESERVED_PREFIX}* "
            "namespace (other checkouts and sessions use it). Choose another "
            "test_ name."
        )
    if name == main_database_name:
        raise ImproperlyConfigured(
            f"Test database {name!r} is the configured application database. "
            "A test run would drop it."
        )
    return name
