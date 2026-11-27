import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from config.proxies import parse_trusted_proxies

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = [
    host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "axes",
    "api",
    "users",
    "challenges",
    "planning",
    "roadmaps",
    "execution",
    "records",
    "reflections",
    "health",
    "scheduling",
]
MIDDLEWARE = [
    # First: answers the platform health probe before host and HTTPS checks.
    "config.health_probe.HealthProbeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, as django-axes requires: it turns a lockout into the 429 response.
    "axes.middleware.AxesMiddleware",
]

# Login throttling (owner decision 4.4, Phase 0C S11): five failures per email
# and IP address are answered normally; the sixth failure is refused with 429
# and locks that combination for 15 minutes. A success resets the count. Covers
# the API login and the Django admin login alike.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 6  # axes counts the failure that triggers the lock
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_CALLABLE = "config.security.axes_username"
AXES_LOCKOUT_CALLABLE = "config.security.lockout_response"
# Our own security log records these events with masked emails (S12); axes'
# verbose log and per-success access log would store raw emails instead.
AXES_VERBOSE = False
AXES_DISABLE_ACCESS_LOG = True
# Masked in the form data axes stores with each failed attempt (it always
# masks the password). The admin form's CSRF token is a secret of that browser.
AXES_SENSITIVE_PARAMETERS = ["username", "ip_address", "csrfmiddlewaretoken"]
# The client address for lockouts and the security log (config/proxies.py).
# Forwarded headers are believed only from these proxies; empty = none.
CHARITYOS_TRUSTED_PROXIES = parse_trusted_proxies(
    os.environ.get("CHARITYOS_TRUSTED_PROXIES", "")
)
AXES_CLIENT_IP_CALLABLE = "config.proxies.axes_client_ip"
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "charityos"),
        "USER": os.environ.get("POSTGRES_USER", "charityos"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"
# USERNAME_FIELD is protected by a functional unique constraint so mixed-case
# writes outside the model layer cannot bypass email uniqueness.
# Email is unique case-insensitively by the users_user_email_ci_unique
# constraint, not by unique=True. Django reports that as auth.E003 with the
# default backend and as auth.W004 with custom backends (django-axes).
SILENCED_SYSTEM_CHECKS = ["auth.E003", "auth.W004"]

# Security events (Phase 0C, S12): one line each on stderr, which the process
# manager or platform collects. Emails are masked and IPs truncated by
# config.security; nothing secret is ever passed to this logger.
#
# Server errors (unhandled exceptions, DisallowedHost and other
# django.security errors): one redacted line plus traceback each on stderr
# (config/error_logging.py). Without this, DEBUG = False wrote them nowhere.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "security": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        "errors": {
            "()": "config.error_logging.RedactingFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "security": {"class": "logging.StreamHandler", "formatter": "security"},
        "errors": {
            "class": "logging.StreamHandler",
            "formatter": "errors",
            "level": "ERROR",
        },
    },
    "loggers": {
        "charityos.security": {"handlers": ["security"], "level": "INFO"},
        "django.request": {
            "handlers": ["errors"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["errors"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "api.exceptions.exception_handler",
    # A JSON body must be an object (api/parsers.py); forms parse as before.
    "DEFAULT_PARSER_CLASSES": [
        "api.parsers.ObjectJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin
]
