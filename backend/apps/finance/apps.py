from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"
    verbose_name = "Business OS · Finance"

    def ready(self):
        from apps.access import defaults as access_defaults

        from . import integrations, services  # noqa: F401  (approval hooks, search, AI, alerts, pulse)
        from .defaults import install

        if install not in access_defaults.INSTALLERS:
            access_defaults.INSTALLERS.append(install)
