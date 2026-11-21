from django.core.management.base import BaseCommand

from apps.rides.services import dispatch_due_scheduled


class Command(BaseCommand):
    help = "Start matching for scheduled rides whose pickup is within 15 minutes. Run every minute (cron/scheduler)."

    def handle(self, **_):
        self.stdout.write(f"Dispatched {dispatch_due_scheduled()} scheduled ride(s).")
