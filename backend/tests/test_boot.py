from django.conf import settings


def test_application_uses_custom_user_and_utc():
    assert settings.AUTH_USER_MODEL == "users.User"
    assert settings.TIME_ZONE == "UTC"
    assert settings.USE_TZ is True


def test_tests_use_postgresql():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
