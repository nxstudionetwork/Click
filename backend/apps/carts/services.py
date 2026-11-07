from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.catalog.models import Product
from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import CustomerProfile

from .models import MAX_ITEM_QUANTITY, Cart, CartItem

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    delivery_fee: Decimal
    tax: Decimal
    total: Decimal


def get_or_create_cart(customer: CustomerProfile) -> Cart:
    cart, _ = Cart.objects.get_or_create(customer=customer)
    return cart


def compute_totals(cart: Cart, items) -> Totals:
    subtotal = sum((i.product.price * i.quantity for i in items), Decimal("0"))
    delivery_fee = cart.store.delivery_fee if (cart.store and items) else Decimal("0")
    tax = (subtotal * settings.CLICK_TAX_RATE).quantize(TWO_PLACES)
    return Totals(subtotal.quantize(TWO_PLACES), delivery_fee, tax, (subtotal + delivery_fee + tax).quantize(TWO_PLACES))


@transaction.atomic
def add_item(customer: CustomerProfile, product_id, quantity: int, note: str = "") -> CartItem:
    cart = Cart.objects.select_for_update().get(pk=get_or_create_cart(customer).pk)
    try:
        product = Product.objects.select_related("store").get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        raise DomainError("This item is no longer available.", code="product_not_found", status_code=404)
    if not product.is_available or not product.store.is_open:
        raise DomainError("This item can't be ordered right now.", code="product_unavailable")

    if cart.store_id and cart.store_id != product.store_id and cart.items.exists():
        raise ConflictError(
            "Your cart has items from another store. Clear it to add this item.",
            code="cart_store_conflict",
            details={"cart_store_id": str(cart.store_id)},
        )
    if cart.store_id != product.store_id:
        cart.store = product.store
        cart.save(update_fields=["store", "updated_at"])

    item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity, "note": note})
    if not created:
        item.quantity = min(item.quantity + quantity, MAX_ITEM_QUANTITY)
        item.note = note or item.note
        item.save(update_fields=["quantity", "note", "updated_at"])
    return item


@transaction.atomic
def update_item(item: CartItem, quantity: int, note: str | None = None) -> CartItem:
    item.quantity = quantity
    if note is not None:
        item.note = note
    item.save(update_fields=["quantity", "note", "updated_at"])
    return item


@transaction.atomic
def remove_item(item: CartItem) -> None:
    cart = item.cart
    item.delete()
    if not cart.items.exists():
        cart.store = None
        cart.save(update_fields=["store", "updated_at"])


@transaction.atomic
def clear_cart(cart: Cart) -> None:
    cart.items.all().delete()
    cart.store = None
    cart.save(update_fields=["store", "updated_at"])
