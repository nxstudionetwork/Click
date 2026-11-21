import secrets

from django.db import migrations, models

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_customer_code() -> str:
    """Frozen copy of the original (pre-sequence) generator. Migrations must not import live model code: the
    current generator uses a database sequence that only exists from migration 0005, so importing it here broke
    every fresh database (tests, CI, new installs)."""
    return "CLK-CS-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def backfill(apps, schema_editor):
    CustomerProfile = apps.get_model("customers", "CustomerProfile")
    used = set()
    for profile in CustomerProfile.objects.filter(customer_code__isnull=True):
        code = apps_code()
        while code in used or CustomerProfile.objects.filter(customer_code=code).exists():
            code = apps_code()
        used.add(code)
        profile.customer_code = code
        profile.save(update_fields=["customer_code"])


def apps_code():
    return generate_customer_code()


class Migration(migrations.Migration):
    dependencies = [("customers", "0002_initial")]

    operations = [
        migrations.AddField("customerprofile", "customer_code", models.CharField(max_length=16, null=True, editable=False)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            "customerprofile", "customer_code",
            models.CharField(default=generate_customer_code, editable=False, max_length=16, unique=True),
        ),
    ]
