from django.core.management.base import BaseCommand

from apps.access.governance import run_jobs


class Command(BaseCommand):
    help = "Identity & Access housekeeping: end temporary and emergency access, warn before expiry, expire accounts (run every 15 min)."

    def handle(self, *args, **opts):
        self.stdout.write(str(run_jobs()))
