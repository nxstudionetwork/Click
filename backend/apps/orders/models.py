import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import Product
from apps.core.models import BaseModel
from apps.customers.models import Address, CustomerProfile
from apps.stores.models import Store

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I


def generate_order_number() -> str:
    return "CLK-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class OrderStatus(models.TextChoices):
    PLACED = "placed", "Placed"
    CONFIRMED = "confirmed", "Confirmed by store"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready for pickup"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


# The only legal status changes. Enforced in services.transition_order().
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PLACED: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY},
    OrderStatus.READY: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}
CUSTOMER_CANCELLABLE = {OrderStatus.PLACED, OrderStatus.CONFIRMED}


class Order(BaseModel):
    number = models.CharField(max_length=16, unique=True, default=generate_order_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="orders")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED)

    # Address is snapshotted (JSON) because orders are historical records; the FK is kept for analytics.
    delivery_address = models.JSONField()
    delivery_address_ref = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    customer_note = models.CharField(max_length=300, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)

    idempotency_key = models.UUIDField(help_text="Client-generated; prevents duplicate orders on retries.")
    estimated_delivery_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"], name="orders_customer_recent_idx"),
            models.Index(fields=["store", "status"], name="orders_store_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="orders_customer_idempotency_unique"),
            models.CheckConstraint(condition=Q(total__gte=0, subtotal__gte=0), name="orders_amounts_non_negative"),
        ]

    def __str__(self) -> str:
        return self.number


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name="+")
    product_name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="orders_item_quantity_positive")]


class OrderStatusEvent(BaseModel):
    """Append-only audit trail of every status change."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, choices=OrderStatus.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at"]
