"""
DEVELOPMENT MOCK DATA loader.

    python manage.py seed_dev_data

Repeatable and non-destructive: catalogue rows are upserted by natural keys,
customer history is created once, nothing is ever deleted. Refuses to run
unless DJANGO_DEBUG=true. See devseed/ for the data and docs/development-data.md.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from devseed import MARKER
from devseed.catalog import seed_catalog
from devseed.customer import TEST_CUSTOMER, seed_test_customer
from devseed.events import seed_events


class Command(BaseCommand):
    help = f"Load {MARKER} (catalogue, movies/events, test customer with history). DEVELOPMENT ONLY."

    def add_arguments(self, parser):
        parser.add_argument("--catalog-only", action="store_true", help="Seed catalogue and events, skip the test customer.")

    def handle(self, *args, **opts):
        if not (settings.DEBUG or settings.TESTING):
            raise CommandError("seed_dev_data only runs with DJANGO_DEBUG=true. It must never run against production.")
        log = lambda m: self.stdout.write(f"  {m}")  # noqa: E731
        self.stdout.write(self.style.WARNING(f"Seeding {MARKER}…"))
        with transaction.atomic():
            seed_catalog(log)
            seed_events(log)
        if not opts["catalog_only"]:
            with transaction.atomic():
                seed_test_customer(log)
            self.stdout.write(self.style.SUCCESS(
                f"Test customer: {TEST_CUSTOMER['full_name']} · {TEST_CUSTOMER['customer_code']} · {TEST_CUSTOMER['email']} · "
                f"password {TEST_CUSTOMER['password']} (dev only) · or use “Login as Test Customer” on the login screen."))
        self.stdout.write(self.style.SUCCESS("Done."))
