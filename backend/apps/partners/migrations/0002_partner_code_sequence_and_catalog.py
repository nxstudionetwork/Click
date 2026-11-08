from django.db import migrations

from apps.partners.models import PARTNER_CODE_SEQUENCE


def load_catalog(apps, schema_editor):
    from apps.partners.catalog import apply_catalog

    apply_catalog(apps.get_model("partners", "PartnerType"), apps.get_model("partners", "PartnerCategory"))


class Migration(migrations.Migration):
    dependencies = [("partners", "0001_initial")]

    operations = [
        # Click Partner IDs (CLK-PT-000001) come from their own sequence: unique, never reused,
        # and unrelated to row IDs. Gaps are possible (rolled-back submissions) and harmless.
        migrations.RunSQL(
            f"CREATE SEQUENCE IF NOT EXISTS {PARTNER_CODE_SEQUENCE} START 1 INCREMENT 1 NO CYCLE;",
            f"DROP SEQUENCE IF EXISTS {PARTNER_CODE_SEQUENCE};",
        ),
        migrations.RunPython(load_catalog, migrations.RunPython.noop),
    ]
