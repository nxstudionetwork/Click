"""Run every alert detector now (schedule every few minutes; Home also triggers them, at most every 2 minutes)."""

from django.core.management.base import BaseCommand

from apps.organization.models import Organization
from apps.workspace.alerts import run


class Command(BaseCommand):
    help = "Raise, refresh and auto-resolve Business OS alerts."

    def handle(self, *args, **opts):
        for org in Organization.objects.filter(is_active=True):
            self.stdout.write(f"{org.name}: {run(org, force=True)} new alert(s)")
