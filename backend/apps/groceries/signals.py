"""'Notify me' delivery: when a listing becomes orderable again or a store starts taking orders again, everyone who
asked is notified once (after the change commits)."""

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.catalog.models import Product
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.stores.models import Store, StoreType

from .models import StockAlert


def _product_orderable(p: Product) -> bool:
    return bool(p.is_active and p.is_available and (p.stock_quantity is None or p.stock_quantity > 0))


@receiver(pre_save, sender=Product)
def _remember_product(sender, instance: Product, **kwargs):
    if instance.pk and instance.grocery_item_id:
        old = Product.objects.filter(pk=instance.pk).only("is_active", "is_available", "stock_quantity").first()
        instance._was_orderable = _product_orderable(old) if old else None


@receiver(post_save, sender=Product)
def _product_back(sender, instance: Product, created, **kwargs):
    if created or getattr(instance, "_was_orderable", None) is not False or not _product_orderable(instance):
        return
    transaction.on_commit(lambda: send_product_alerts(instance.pk))


def send_product_alerts(product_id) -> int:
    p = Product.objects.select_related("store", "grocery_item").filter(pk=product_id).first()
    if p is None or not _product_orderable(p):
        return 0
    n = 0
    for a in StockAlert.objects.filter(product=p, notified_at__isnull=True).select_related("customer"):
        notify(a.customer, NotificationCategory.OFFERS, f"Back in stock: {p.grocery_item.name if p.grocery_item_id else p.name}",
               f"{p.store.name} has it again.", f"/groceries/p/{p.id}")
        a.notified_at = timezone.now()
        a.save(update_fields=["notified_at", "updated_at"])
        n += 1
    return n


@receiver(pre_save, sender=Store)
def _remember_store(sender, instance: Store, **kwargs):
    if instance.pk and instance.store_type == StoreType.GROCERY:
        old = Store.objects.filter(pk=instance.pk).only("status", "is_accepting_orders").first()
        instance._was_open = old.is_open if old else None


@receiver(post_save, sender=Store)
def _store_back(sender, instance: Store, created, **kwargs):
    if created or getattr(instance, "_was_open", None) is not False or not instance.is_open:
        return
    transaction.on_commit(lambda: send_store_alerts(instance.pk))


def send_store_alerts(store_id) -> int:
    s = Store.objects.filter(pk=store_id).first()
    if s is None or not s.is_open:
        return 0
    n = 0
    for a in StockAlert.objects.filter(store=s, notified_at__isnull=True).select_related("customer"):
        notify(a.customer, NotificationCategory.ORDERS, f"{s.name} is taking orders again", "", f"/groceries/store/{s.slug}")
        a.notified_at = timezone.now()
        a.save(update_fields=["notified_at", "updated_at"])
        n += 1
    return n
