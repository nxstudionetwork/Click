from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self):
        # Click's API runs on port 4000 in development (`python manage.py runserver`).
        from django.conf import settings
        from django.core.management.commands import runserver

        runserver.Command.default_port = settings.CLICK_DEV_PORT
