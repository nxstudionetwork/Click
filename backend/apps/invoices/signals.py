"""Issue the invoice as soon as a payment is captured or refunded (not only when the customer opens Invoices)."""

import logging

from django.db import transaction
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def _on_payment(sender, instance, **kwargs):
    if instance.status not in ("captured", "refunded") or instance.wallet_topup_id:
        return
    pk = instance.pk

    def build():
        from apps.payments.models import Payment

        from .builder import ensure

        try:
            p = Payment.objects.filter(pk=pk).first()
            if p:
                ensure(p)
        except Exception:  # noqa: BLE001 — an invoice problem must never affect the payment itself
            logger.exception("invoice for payment %s", pk)

    transaction.on_commit(build)


def connect():
    from apps.payments.models import Payment

    post_save.connect(_on_payment, sender=Payment, dispatch_uid="invoices.on_payment")
