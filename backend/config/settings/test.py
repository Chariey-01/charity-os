import os

from config.testdb import test_database_name

from .base import *  # noqa: F403
from .base import BASE_DIR, DATABASES

SECRET_KEY = "test-only-secret-key"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Django's test client.login() authenticates without a request, which
# django-axes refuses. The login-security tests switch it on explicitly.
AXES_ENABLED = False

# One test database per checkout (see config/testdb.py). BASE_DIR is backend/,
# so its parent is the checkout root.
DATABASES["default"]["TEST"] = {
    "NAME": test_database_name(
        BASE_DIR.parent, os.environ, DATABASES["default"]["NAME"]
    )
}
