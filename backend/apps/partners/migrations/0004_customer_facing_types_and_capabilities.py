"""Partner types aligned with the Customer App's services, retired types hidden, and Click-granted capabilities."""

from django.db import migrations, models


def load_catalog(apps, schema_editor):
    from apps.partners.catalog import apply_catalog

    apply_catalog(apps.get_model("partners", "PartnerType"), apps.get_model("partners", "PartnerCategory"),
                  apps.get_model("partners", "Partner"))


class Migration(migrations.Migration):
    dependencies = [("partners", "0003_operations_links_availability_notifications")]

    operations = [
        migrations.AddField(
            model_name="partner",
            name="capabilities",
            field=models.JSONField(
                blank=True, default=None, null=True,
                help_text="Capability keys Click has granted (see catalog.py). Empty = the category's default capabilities apply. "
                          "Staff set an explicit list to grant or revoke; partners can never change it.",
            ),
        ),
        migrations.RunPython(load_catalog, migrations.RunPython.noop),
    ]
