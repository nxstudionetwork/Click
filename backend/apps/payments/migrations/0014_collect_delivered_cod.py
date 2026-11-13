from django.db import migrations


def collect(apps, schema_editor):
    """Cash-on-delivery payments of orders already delivered were collected: mark them captured."""
    Payment = apps.get_model("payments", "Payment")
    Payment.objects.filter(method="cash_on_delivery", status="pending", order__status="delivered").update(status="captured")


class Migration(migrations.Migration):
    dependencies = [("payments", "0013_payment_wallet_topup_alter_payment_method_and_more"), ("orders", "0004_order_estimated_delivery_from_orderitem_deal_percent_and_more")]
    operations = [migrations.RunPython(collect, migrations.RunPython.noop)]
