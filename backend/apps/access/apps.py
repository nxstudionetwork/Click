from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access"
    verbose_name = "Business OS · Identity, Roles & Permissions"

    def ready(self):
        from .registry import sync_permissions

        def _sync(sender, **kwargs):
            if sender.name == self.name:
                sync_permissions(using=kwargs.get("using", "default"))

        post_migrate.connect(_sync, dispatch_uid="access.sync_permissions")
