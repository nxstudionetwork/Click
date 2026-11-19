"""Daily People & HR jobs (run once a day from the scheduler): scheduled promotions/transfers, joiners going live,
offer expiry, document/certification expiry and probation reminders."""

from django.core.management.base import BaseCommand

from apps.organization.models import Organization
from apps.people.services import daily_jobs


class Command(BaseCommand):
    help = "Run the daily People & HR jobs for every organization."

    def handle(self, *args, **opts):
        for org in Organization.objects.filter(is_active=True):
            self.stdout.write(f"{org.name}: {daily_jobs(org)}")
