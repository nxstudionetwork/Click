from django.db import migrations

from apps.customers.models import CUSTOMER_CODE_SEQUENCE


class Migration(migrations.Migration):
    """New customers get sequential CL-CU-000001 IDs; existing CLK-CS-XXXXXX IDs are kept."""

    dependencies = [("customers", "0004_address_delivery_instructions_customerprofile_avatar_and_more")]
    operations = [migrations.RunSQL(f"CREATE SEQUENCE IF NOT EXISTS {CUSTOMER_CODE_SEQUENCE} START 1 INCREMENT 1 NO CYCLE;",
                                    f"DROP SEQUENCE IF EXISTS {CUSTOMER_CODE_SEQUENCE};")]
