from django.core.management.base import BaseCommand

from apps.partners.catalog import apply_catalog
from apps.partners.models import Partner, PartnerCategory, PartnerType


class Command(BaseCommand):
    help = "Upsert partner types and categories from apps/partners/catalog.py (idempotent)."

    def handle(self, *args, **options):
        apply_catalog(PartnerType, PartnerCategory, Partner)
        self.stdout.write(self.style.SUCCESS(
            f"{PartnerType.objects.count()} partner types, {PartnerCategory.objects.count()} categories."
        ))
