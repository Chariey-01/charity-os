from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def _normalize_email(email):
        if not email:
            raise ValueError("An email address is required")
        return BaseUserManager.normalize_email(email).strip().lower()

    def create_user(self, email, password=None, **extra_fields):
        user = self.model(email=self._normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser enabled")
        return self.create_user(email, password, **extra_fields)
