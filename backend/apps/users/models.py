"""
A single identity for every Click actor. Roles are expressed by *profiles*
attached to the user (CustomerProfile now; partner memberships and staff
permissions later) rather than separate user tables, so one person can be a
customer and a partner without duplicate accounts.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_phone_user(self, phone: str, **extra):
        """A user who signs in with a verified phone number only (e.g. Click Partner via phone OTP)."""
        user = self.model(email=None, phone=phone, phone_verified=True, **extra)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    # Stored lowercased; CI constraint below. Null for phone-only identities
    # (Click Partner signs in with an OTP-verified phone number).
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    phone_verified = models.BooleanField(default=False, help_text="Phone ownership proven by an identity provider (OTP).")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can access internal tools (Business OS / admin).")

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_user_email_ci_unique"),
            # A verified phone number belongs to exactly one Click account.
            models.UniqueConstraint(fields=["phone"], condition=models.Q(phone_verified=True), name="users_verified_phone_unique"),
        ]

    def __str__(self) -> str:
        return self.email or self.phone or str(self.id)

