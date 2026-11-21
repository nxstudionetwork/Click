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


class SignInEvent(BaseModel):
    """
    Account security log: every code request, sign-in, failed code, new account and sign-out, with where it came from.
    Customers see their recent sign-ins in Safety Center; support uses it to investigate account takeovers.
    Never stores codes or tokens.
    """

    EVENTS = [("code_requested", "Code requested"), ("signed_in", "Signed in"), ("signed_up", "Account created"),
              ("failed", "Wrong or expired code"), ("signed_out", "Signed out"), ("signed_out_others", "Signed out other devices")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="sign_in_events")
    event = models.CharField(max_length=20, choices=EVENTS)
    method = models.CharField(max_length=20, default="phone_otp", help_text="phone_otp, password (dev/test), dev_login (development only).")
    phone = models.CharField(max_length=16, blank=True, help_text="E.164 (+91…) the attempt was for.")
    app = models.CharField(max_length=16, blank=True, help_text="customer / partner, from the X-Click-Client header.")
    ip = models.GenericIPAddressField(null=True, blank=True)
    device = models.CharField(max_length=80, blank=True, help_text="Readable device summary, e.g. 'Chrome on Android'.")
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"], name="signin_user_recent_idx"),
                   models.Index(fields=["phone", "-created_at"], name="signin_phone_recent_idx")]

    def __str__(self) -> str:
        return f"{self.event} {self.phone or self.user_id}"
