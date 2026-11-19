"""
Central Business OS document store. Every module attaches files here (HR employee documents, candidate resumes,
certificates, contracts later) instead of keeping its own file storage.

A document belongs to a record (`resource_type`, `resource_id`) and the module that owns that record decides who may
see it (apps.documents.access). Files are versioned; nothing is overwritten. Expiry, verification and retention are
first-class so reminders and clean-up don't need per-module logic.
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Document(BaseModel):
    class Sensitivity(models.TextChoices):
        NORMAL = "normal", "Normal"
        CONFIDENTIAL = "confidential", "Confidential"
        RESTRICTED = "restricted", "Restricted (ID, tax, medical …)"

    class Verification(models.TextChoices):
        UNVERIFIED = "unverified", "Not verified"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    organization = models.ForeignKey("organization.Organization", on_delete=models.CASCADE, related_name="documents")
    module = models.CharField(max_length=40)
    resource_type = models.CharField(max_length=60, db_index=True)
    resource_id = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=40)
    title = models.CharField(max_length=160)
    sensitivity = models.CharField(max_length=12, choices=Sensitivity.choices, default=Sensitivity.CONFIDENTIAL)
    expires_on = models.DateField(null=True, blank=True)
    verification = models.CharField(max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)
    retain_until = models.DateField(null=True, blank=True, help_text="Retention policy: kept at least until this date.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    current_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["resource_type", "resource_id"], name="doc_resource_idx"),
                   models.Index(fields=["organization", "expires_on"], name="doc_expiry_idx")]

    def __str__(self) -> str:
        return self.title


class DocumentVersion(BaseModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    file = models.FileField(upload_to="os/documents/%Y/%m/")
    file_name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["document", "version"], name="docversion_unique")]
