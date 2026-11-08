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
        """A user who signs in with a verified phone number only (e.g. Click Partner via Firebase)."""
        user = self.model(email=None, phone=phone, **extra)
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
    # (Click Partner signs in with a Firebase-verified phone number).
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can access internal tools (Business OS / admin).")

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(Lower("email"), name="users_user_email_ci_unique")]

    def __str__(self) -> str:
        return self.email or self.phone or str(self.id)


class AuthIdentity(BaseModel):
    """
    An external identity provider account linked to a Click user.

    Firebase Authentication proves control of a phone number; its immutable
    UID (`subject`) is the lookup key, never the phone number itself. Business
    data lives in Click's own tables, not in the identity provider.
    """

    class Provider(models.TextChoices):
        FIREBASE = "firebase", "Firebase Authentication"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    subject = models.CharField(max_length=128, help_text="Provider's immutable user ID (Firebase UID).")
    phone_number = models.CharField(max_length=20, blank=True, help_text="E.164 phone verified by the provider.")
    last_verified_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="users_identity_provider_subject_unique"),
        ]
        indexes = [models.Index(fields=["provider", "phone_number"], name="users_identity_phone_idx")]

    def __str__(self) -> str:
        return f"{self.provider}:{self.subject}"
