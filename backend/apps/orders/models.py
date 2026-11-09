import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import Product, ProductVariant
from apps.core.models import BaseModel
from apps.customers.models import Address, CustomerProfile
from apps.stores.models import Store

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I


def generate_order_number() -> str:
    return "CLK-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def generate_checkout_number() -> str:
    return "CLK-C-" + "".join(secrets.choice(_ALPHABET) for _ in range(7))


class OrderStatus(models.TextChoices):
    PLACED = "placed", "Placed"
    CONFIRMED = "confirmed", "Confirmed by store"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready for pickup"
    PACKED = "packed", "Packed"
    SHIPPED = "shipped", "Shipped"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


# The only legal status changes. Enforced in services.transition_order().
# Food and groceries: confirmed -> preparing -> ready -> out for delivery.
# Shopping (retail sellers): confirmed -> packed -> shipped -> out for delivery.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PLACED: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.PACKED, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY},
    OrderStatus.READY: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.PACKED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}
CUSTOMER_CANCELLABLE = {OrderStatus.PLACED, OrderStatus.CONFIRMED}


class CheckoutGroup(BaseModel):
    """One checkout of a marketplace cart. It becomes one order per seller; the group ties them together."""

    number = models.CharField(max_length=16, unique=True, default=generate_checkout_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="checkouts")
    idempotency_key = models.UUIDField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer", "idempotency_key"], name="orders_checkout_idempotency_unique")]

    def __str__(self) -> str:
        return self.number


class Order(BaseModel):
    number = models.CharField(max_length=16, unique=True, default=generate_order_number, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="orders")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="orders")
    checkout = models.ForeignKey(CheckoutGroup, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED)

    # Address is snapshotted (JSON) because orders are historical records; the FK is kept for analytics.
    delivery_address = models.JSONField()
    delivery_address_ref = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    customer_note = models.CharField(max_length=300, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    offer_title = models.CharField(max_length=80, blank=True, help_text="Snapshot of the applied offer.")
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CLICK_DEFAULT_CURRENCY)

    idempotency_key = models.UUIDField(help_text="Client-generated; prevents duplicate orders on retries.")
    estimated_delivery_at = models.DateTimeField(null=True, blank=True)
    # Shopping: the earliest day of the estimated delivery window (latest is estimated_delivery_at).
    estimated_delivery_from = models.DateTimeField(null=True, blank=True)
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
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    product_name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    options_summary = models.CharField(max_length=300, blank=True, help_text="Snapshot, e.g. 'Large · Extra cheese' or 'Black · M'.")
    # Snapshots of the listing's terms at purchase time (the product may change later).
    return_days = models.PositiveSmallIntegerField(null=True, blank=True)
    replacement_only = models.BooleanField(default=False)
    deal_percent = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="orders_item_quantity_positive")]


class OrderReview(BaseModel):
    """A customer's rating of a delivered order (one per order). Feeds the store's rating."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="reviews")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="orders_review_rating_range")]


class OrderStatusEvent(BaseModel):
    """Append-only audit trail of every status change."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, choices=OrderStatus.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at"]


class ReturnRequest(BaseModel):
    """
    A customer's request to return or replace a delivered item, within that item's return window.
    Click staff (later the seller in the Partner App) approve or reject it; an approved return is refunded to the
    Click Wallet by apps.orders.returns (never automatically by the customer's request alone).
    """

    class Kind(models.TextChoices):
        RETURN = "return", "Return for refund"
        REPLACEMENT = "replacement", "Replacement"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REFUNDED = "refunded", "Refunded"
        REPLACED = "replaced", "Replacement sent"

    class Reason(models.TextChoices):
        DAMAGED = "damaged", "Arrived damaged"
        WRONG_ITEM = "wrong_item", "Wrong item"
        NOT_AS_DESCRIBED = "not_as_described", "Not as described"
        SIZE_FIT = "size_fit", "Size or fit issue"
        DEFECTIVE = "defective", "Doesn't work"
        CHANGED_MIND = "changed_mind", "No longer needed"

    item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="returns")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="returns")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.CharField(max_length=500, blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    resolution_note = models.CharField(max_length=300, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="orders_return_quantity_positive")]
