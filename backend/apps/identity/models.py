"""
Links a Click user to the identity that proved their phone (Click's own phone OTP today; another
provider later). The provider's subject is an authentication
identifier only: it is never the customer-facing ID and never a primary key.
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class ExternalIdentity(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_identities")
    provider = models.CharField(max_length=32, help_text="Registry key, e.g. 'phone_otp'.")
    subject = models.CharField(max_length=128, help_text="Provider's stable user id (the E.164 phone for phone_otp).")
    phone_number = models.CharField(max_length=20, blank=True, help_text="E.164 phone verified by the provider.")
    last_verified_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="identity_provider_subject_unique"),
            models.UniqueConstraint(fields=["user", "provider"], name="identity_one_per_provider_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.subject}"


class OtpChallenge(BaseModel):
    """One phone OTP. Only a salted hash of the code is stored; a challenge is single-use and expires."""

    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone", "-created_at"], name="otp_phone_recent_idx"), models.Index(fields=["ip", "-created_at"], name="otp_ip_recent_idx")]
