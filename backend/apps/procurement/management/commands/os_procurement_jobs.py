from django.core.management.base import BaseCommand

from apps.organization.models import Organization


class Command(BaseCommand):
    help = "Procurement jobs: recurring purchase requests and risk / exception detectors (run hourly)."

    def handle(self, *args, **opts):
        from apps.procurement import services

        for org in Organization.objects.filter(is_active=True):
            self.stdout.write(f"{org.code}: recurring={services.run_recurring(org)} new_flags={services.detect(org)}")
