from django.apps import AppConfig


class ProcurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.procurement"
    verbose_name = "Business OS · Procurement"

    def ready(self):
        from apps.access import defaults as access_defaults

        from . import integrations, services  # noqa: F401  (approval hooks, Finance matcher, search, AI, alerts, documents)
        from .defaults import install

        if install not in access_defaults.INSTALLERS:
            access_defaults.INSTALLERS.append(install)
