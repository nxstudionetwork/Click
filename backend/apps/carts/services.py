from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.catalog.models import Product, ProductOption
from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import CustomerProfile
from apps.stores.models import StoreOffer

from .models import MAX_ITEM_QUANTITY, Cart, CartItem

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    delivery_fee: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal


def get_or_create_cart(customer: CustomerProfile) -> Cart:
    cart, _ = Cart.objects.get_or_create(customer=customer)
    return cart


def unit_price(item) -> Decimal:
    """Product price plus the chosen options' price changes, always read from the catalogue."""
    return item.product.price + sum((o.price_delta for o in item.options.all()), Decimal("0"))


def offer_problem(offer: StoreOffer | None, store, subtotal: Decimal) -> str | None:
    """Why `offer` can't be applied to this cart right now (None means it can)."""
    from apps.stores.views import active_offers

    if offer is None:
        return "Choose an offer."
    if not offer.is_redeemable:
        return "This offer is shown by the store and can't be applied at checkout."
    if store is None or offer.store_id != store.id:
        return "This offer is for a different store."
    if not active_offers().filter(pk=offer.pk).exists():
        return "This offer has ended."
    if subtotal < offer.min_order_amount:
        return f"Add items worth {offer.min_order_amount - subtotal:.2f} more to use this offer."
    return None


def offer_discount(offer: StoreOffer, subtotal: Decimal, delivery_fee: Decimal) -> Decimal:
    if offer.discount_type == StoreOffer.DiscountType.PERCENT:
        d = (subtotal * offer.discount_value / 100).quantize(TWO_PLACES)
        return min(d, offer.max_discount) if offer.max_discount is not None else d
    if offer.discount_type == StoreOffer.DiscountType.FLAT:
        return min(offer.discount_value, subtotal)
    if offer.discount_type == StoreOffer.DiscountType.FREE_DELIVERY:
        return delivery_fee
    return Decimal("0")


def compute_totals(cart: Cart, items) -> Totals:
    subtotal = sum((unit_price(i) * i.quantity for i in items), Decimal("0")).quantize(TWO_PLACES)
    delivery_fee = cart.store.delivery_fee if (cart.store and items) else Decimal("0")
    tax = (subtotal * settings.CLICK_TAX_RATE).quantize(TWO_PLACES)
    discount = Decimal("0")
    if cart.offer_id and items and offer_problem(cart.offer, cart.store, subtotal) is None:
        discount = offer_discount(cart.offer, subtotal, delivery_fee)
    total = max(subtotal + delivery_fee + tax - discount, Decimal("0")).quantize(TWO_PLACES)
    return Totals(subtotal, delivery_fee, tax, discount, total)


def resolve_options(product: Product, option_ids) -> list[ProductOption]:
    """Validate chosen options against the product's groups: required choices, limits and availability."""
    groups = list(product.option_groups.prefetch_related("options"))
    by_id = {str(o.id): (g, o) for g in groups for o in g.options.all()}
    chosen = []
    for oid in dict.fromkeys(str(x) for x in option_ids or []):
        if oid not in by_id:
            raise DomainError("That choice isn't available for this item.", code="invalid_option")
        g, o = by_id[oid]
        if not o.is_available:
            raise DomainError(f"{o.name} isn't available right now.", code="option_unavailable")
        chosen.append((g, o))
    for g in groups:
        n = sum(1 for cg, _ in chosen if cg.id == g.id)
        if n < g.min_select:
            raise DomainError(f"Choose {g.name.lower()}.", code="option_required", details={"group": g.name})
        if n > g.max_select:
            raise DomainError(f"Choose up to {g.max_select} for {g.name.lower()}.", code="option_limit", details={"group": g.name})
    return [o for _, o in chosen]


@transaction.atomic
def add_item(customer: CustomerProfile, product_id, quantity: int, note: str = "", option_ids=None) -> CartItem:
    cart = Cart.objects.select_for_update().get(pk=get_or_create_cart(customer).pk)
    try:
        product = Product.objects.select_related("store").get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        raise DomainError("This item is no longer available.", code="product_not_found", status_code=404)
    if not product.is_orderable or not product.store.is_open:
        raise DomainError("This item can't be ordered right now.", code="product_unavailable")

    if cart.store_id and cart.store_id != product.store_id and cart.items.exists():
        raise ConflictError(
            "Your cart has items from another store. Clear it to add this item.",
            code="cart_store_conflict",
            details={"cart_store_id": str(cart.store_id)},
        )
    options = resolve_options(product, option_ids)
    options_key = ",".join(sorted(str(o.id) for o in options))
    if cart.store_id != product.store_id:
        cart.store = product.store
        cart.offer = None  # offers belong to a store
        cart.save(update_fields=["store", "offer", "updated_at"])

    from apps.activity.services import record

    record(customer, "cart.added", {"quantity": quantity}, obj=product)
    existing = CartItem.objects.filter(cart=cart, product=product, options_key=options_key).first()
    other_lines = CartItem.objects.filter(cart=cart, product=product).exclude(pk=getattr(existing, "pk", None))
    new_quantity = min((existing.quantity if existing else 0) + quantity, MAX_ITEM_QUANTITY)
    ensure_stock(product, new_quantity + sum(other_lines.values_list("quantity", flat=True)))
    if existing:
        existing.quantity = new_quantity
        existing.note = note or existing.note
        existing.save(update_fields=["quantity", "note", "updated_at"])
        return existing
    item = CartItem.objects.create(cart=cart, product=product, quantity=new_quantity, note=note, options_key=options_key)
    item.options.set(options)
    return item


def ensure_stock(product: Product, quantity: int) -> None:
    if product.stock_quantity is not None and quantity > product.stock_quantity:
        raise DomainError(
            f"Only {product.stock_quantity} left in stock." if product.stock_quantity else "This item is out of stock.",
            code="insufficient_stock",
            details={"available": product.stock_quantity},
        )


@transaction.atomic
def update_item(item: CartItem, quantity: int, note: str | None = None) -> CartItem:
    if quantity > item.quantity:
        others = CartItem.objects.filter(cart=item.cart, product=item.product).exclude(pk=item.pk)
        ensure_stock(item.product, quantity + sum(others.values_list("quantity", flat=True)))
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
        cart.offer = None
        cart.save(update_fields=["store", "offer", "updated_at"])


@transaction.atomic
def clear_cart(cart: Cart) -> None:
    cart.items.all().delete()
    cart.store = None
    cart.offer = None
    cart.save(update_fields=["store", "offer", "updated_at"])


@transaction.atomic
def set_offer(cart: Cart, offer_id) -> Cart:
    """Apply an offer to the cart after checking it really applies (store, dates, minimum order, redeemable)."""
    cart = Cart.objects.select_for_update(of=("self",)).select_related("store").get(pk=cart.pk)
    items = list(cart.items.select_related("product").prefetch_related("options"))
    if not items:
        raise DomainError("Add items to your cart first.", code="cart_empty")
    offer = StoreOffer.objects.filter(pk=offer_id).first()
    subtotal = sum((unit_price(i) * i.quantity for i in items), Decimal("0"))
    if problem := offer_problem(offer, cart.store, subtotal):
        raise DomainError(problem, code="offer_not_applicable")
    cart.offer = offer
    cart.save(update_fields=["offer", "updated_at"])
    return cart


def remove_offer(cart: Cart) -> Cart:
    cart.offer = None
    cart.save(update_fields=["offer", "updated_at"])
    return cart
