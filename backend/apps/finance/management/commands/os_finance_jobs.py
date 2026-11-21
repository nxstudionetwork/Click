from django.core.management.base import BaseCommand

from apps.organization.models import Organization


class Command(BaseCommand):
    help = "Finance jobs: bring captured / refunded platform payments into the ledger and detect gateway exceptions (run every 15 min)."

    def handle(self, *args, **opts):
        from apps.finance import platform, services

        for org in Organization.objects.filter(is_active=True):
            try:
                out = platform.sync(org)
            except Exception as e:  # finance not configured for this organization yet
                self.stdout.write(f"{org.code}: skipped ({e})")
                continue
            out["gateway_exceptions"] = services.detect_gateway_exceptions(org)
            self.stdout.write(f"{org.code}: {out}")
