from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.people"
    verbose_name = "Business OS · People & HR"

    def ready(self):
        # Approval hooks (leave, corrections, positions, offers, changes, exits) and the module's Home widgets,
        # alerts, calendar, search, AI tools and document-access rules.
        from . import integrations, services  # noqa: F401
