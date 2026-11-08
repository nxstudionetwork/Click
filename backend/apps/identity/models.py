"""
Links a Click user to an external identity provider account (Firebase today; any
provider later). The provider's subject (e.g. Firebase UID) is an authentication
identifier only: it is never the customer-facing ID and never a primary key.
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class ExternalIdentity(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_identities")
    provider = models.CharField(max_length=32, help_text="Registry key, e.g. 'firebase'.")
    subject = models.CharField(max_length=128, help_text="Provider's stable user id, e.g. Firebase UID.")
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
