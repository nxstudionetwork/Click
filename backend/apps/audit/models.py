"""
Append-only audit trail for the Business OS. Every module records through apps.audit.services.record();
rows can't be updated or deleted through the ORM (and are read-only in Django admin).
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class AuditEvent(BaseModel):
    class Category(models.TextChoices):
        AUTH = "auth", "Sign-in & sessions"
        SECURITY = "security", "Security"
        ACCESS = "access", "Roles & permissions"
        DATA = "data", "Data change"
        APPROVAL = "approval", "Approval"
        FINANCIAL = "financial", "Financial"
        CONFIG = "config", "Configuration"
        EXPORT = "export", "Export"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        DENIED = "denied", "Denied"

    organization = models.ForeignKey("organization.Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    actor_label = models.CharField(max_length=200, blank=True, help_text="Snapshot: stays readable if the account is removed.")
    actor_kind = models.CharField(max_length=12, default="user")  # user | service | system | anonymous
    action = models.CharField(max_length=80, db_index=True)  # e.g. auth.login, access.role.update, approval.approved
    category = models.CharField(max_length=12, choices=Category.choices)
    module = models.CharField(max_length=40, blank=True, db_index=True)
    resource_type = models.CharField(max_length=60, blank=True)
    resource_id = models.CharField(max_length=64, blank=True, db_index=True)
    resource_label = models.CharField(max_length=200, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    org_unit = models.ForeignKey("organization.OrgUnit", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    sensitive = models.BooleanField(default=False, help_text="Only holders of audit.sensitive.view see these.")
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.SUCCESS)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    session_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="audit_org_recent_idx"),
            models.Index(fields=["actor", "-created_at"], name="audit_actor_recent_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events are append-only.")
