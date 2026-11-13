from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.catalog.models import Product, ProductOption, ProductVariant
from apps.catalog.pricing import attach_deals, price_of
from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import CustomerProfile
from apps.stores.models import Store, StoreOffer, StoreType

from .models import MAX_ITEM_QUANTITY, Cart, CartItem

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    delivery_fee: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal


@dataclass
class SellerGroup:
    """The part of a cart one seller fulfils: its own delivery fee, tax and (if chosen) offer."""

    store: Store
    items: list = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    delivery_fee: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    offer: StoreOffer | None = None

    @property
    def totals(self) -> Totals:
        return Totals(self.subtotal, self.delivery_fee, self.tax, self.discount, self.total)


def get_or_create_cart(customer: CustomerProfile) -> Cart:
    cart, _ = Cart.objects.get_or_create(customer=customer)
    return cart


def unit_price(item) -> Decimal:
    """Catalogue price of the line (variant price and any active deal, see apps.catalog.pricing) plus chosen options."""
    return price_of(item.product, item.variant).price + sum((o.price_delta for o in item.options.all()), Decimal("0"))


def delivery_fee_for(store: Store, subtotal: Decimal) -> Decimal:
    if store.free_delivery_above is not None and subtotal >= store.free_delivery_above:
        return Decimal("0")
    return store.delivery_fee


def offer_problem(offer: StoreOffer | None, store, subtotal: Decimal) -> str | None:
    """Why `offer` can't be applied to this cart (or this seller's part of it) right now. None means it can."""
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


def seller_groups(cart: Cart, items) -> list[SellerGroup]:
    """Split cart lines by seller and price each part. A single-store cart is one group."""
    attach_deals([i.product for i in items])
    groups: dict = {}
    for i in items:
        store = cart.store if cart.mode == Cart.Mode.STORE and cart.store_id else i.product.store
        groups.setdefault(store.id, SellerGroup(store=store)).items.append(i)
    out = list(groups.values())
    for g in out:
        g.subtotal = sum((unit_price(i) * i.quantity for i in g.items), Decimal("0")).quantize(TWO_PLACES)
        g.delivery_fee = delivery_fee_for(g.store, g.subtotal)
        g.tax = (g.subtotal * settings.CLICK_TAX_RATE).quantize(TWO_PLACES)
        if cart.offer_id and cart.offer.store_id == g.store.id and offer_problem(cart.offer, g.store, g.subtotal) is None:
            g.offer = cart.offer
            g.discount = offer_discount(cart.offer, g.subtotal, g.delivery_fee)
        g.total = max(g.subtotal + g.delivery_fee + g.tax - g.discount, Decimal("0")).quantize(TWO_PLACES)
    return out


def compute_totals(cart: Cart, items) -> Totals:
    groups = seller_groups(cart, items) if items else []
    s = lambda attr: sum((getattr(g, attr) for g in groups), Decimal("0")).quantize(TWO_PLACES)  # noqa: E731
    return Totals(s("subtotal"), s("delivery_fee"), s("tax"), s("discount"), s("total"))


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


def resolve_variant(product: Product, variant_id) -> ProductVariant | None:
    """A product with variants must be bought as one of them (never a silent default); others take none."""
    variants = product.variants.filter(is_active=True)
    if not variants.exists():
        if variant_id:
            raise DomainError("That option isn't available for this item.", code="invalid_variant")
        return None
    if not variant_id:
        raise DomainError("Choose an option (like size or colour) first.", code="variant_required")
    variant = variants.filter(pk=variant_id).first()
    if variant is None:
        raise DomainError("That option isn't available for this item.", code="invalid_variant")
    if not variant.in_stock:
        raise DomainError(f"{variant.label} is out of stock.", code="variant_unavailable")
    return variant


def _mode_for(product: Product) -> str:
    return {StoreType.RETAIL: Cart.Mode.MARKETPLACE, StoreType.GROCERY: Cart.Mode.BASKET}.get(product.store.store_type, Cart.Mode.STORE)


MULTI_STORE = (Cart.Mode.MARKETPLACE, Cart.Mode.BASKET)
_MODE_NOUN = {Cart.Mode.STORE: "food or pharmacy", Cart.Mode.MARKETPLACE: "shopping", Cart.Mode.BASKET: "grocery"}


@transaction.atomic
def add_item(customer: CustomerProfile, product_id, quantity: int, note: str = "", option_ids=None, variant_id=None) -> CartItem:
    cart = Cart.objects.select_for_update().get(pk=get_or_create_cart(customer).pk)
    try:
        product = Product.objects.select_related("store").get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        raise DomainError("This item is no longer available.", code="product_not_found", status_code=404)
    if not product.is_available or not product.store.is_open:
        raise DomainError("This item can't be ordered right now.", code="product_unavailable")

    mode = _mode_for(product)
    has_items = cart.items.exists()
    if has_items and cart.mode and cart.mode != mode:
        # Food, shopping parcels and grocery baskets are checked out separately; ask before clearing.
        raise ConflictError(f"Your cart has {_MODE_NOUN.get(cart.mode, 'other')} items. Clear it to add this item.",
                            code="cart_store_conflict", details={"cart_mode": cart.mode})
    if mode == Cart.Mode.STORE and cart.store_id and cart.store_id != product.store_id and has_items:
        raise ConflictError(
            "Your cart has items from another store. Clear it to add this item.",
            code="cart_store_conflict",
            details={"cart_store_id": str(cart.store_id)},
        )

    variant = resolve_variant(product, variant_id)
    if variant is None and not product.in_stock:
        raise DomainError("This item is out of stock.", code="insufficient_stock", details={"available": 0})
    options = resolve_options(product, option_ids)
    options_key = ",".join(sorted(str(o.id) for o in options))

    new_store = product.store if mode == Cart.Mode.STORE else None
    if cart.mode != mode or cart.store_id != getattr(new_store, "id", None):
        cart.mode, cart.store = mode, new_store
        if mode == Cart.Mode.STORE:
            cart.offer = None  # offers belong to a store
        cart.prescription = None  # a prescription belongs to one pharmacy
        cart.save(update_fields=["mode", "store", "offer", "prescription", "updated_at"])

    from apps.activity.services import record

    record(customer, "cart.added", {"quantity": quantity}, obj=product)
    existing = CartItem.objects.filter(cart=cart, product=product, variant=variant, options_key=options_key).first()
    new_quantity = min((existing.quantity if existing else 0) + quantity, MAX_ITEM_QUANTITY)
    _ensure_line_stock(cart, product, variant, new_quantity, exclude=getattr(existing, "pk", None))
    seen = price_of(product, variant).price  # the price the customer is looking at when they add
    if existing:
        existing.quantity = new_quantity
        existing.note = note or existing.note
        existing.price_seen = seen
        existing.save(update_fields=["quantity", "note", "price_seen", "updated_at"])
        return existing
    item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=new_quantity, note=note,
                                   options_key=options_key, price_seen=seen)
    item.options.set(options)
    return item


def ensure_stock(product: Product, quantity: int, variant: ProductVariant | None = None) -> None:
    available = variant.stock_quantity if variant is not None else product.stock_quantity
    if available is not None and quantity > available:
        raise DomainError(
            f"Only {available} left in stock." if available else "This item is out of stock.",
            code="insufficient_stock",
            details={"available": available},
        )


def _ensure_line_stock(cart, product, variant, quantity, exclude=None) -> None:
    """Stock is per variant when there is one, else per product; other lines of the same stock count too."""
    others = CartItem.objects.filter(cart=cart, product=product, variant=variant).exclude(pk=exclude)
    if product.max_per_order and quantity + sum(others.values_list("quantity", flat=True)) > product.max_per_order:
        raise DomainError(f"You can order up to {product.max_per_order} of this item at a time.", code="quantity_limit", details={"max": product.max_per_order})
    ensure_stock(product, quantity + sum(others.values_list("quantity", flat=True)), variant)


@transaction.atomic
def update_item(item: CartItem, quantity: int | None = None, note: str | None = None, acknowledge_price: bool = False) -> CartItem:
    quantity = quantity or item.quantity
    if quantity > item.quantity:
        _ensure_line_stock(item.cart, item.product, item.variant, quantity, exclude=item.pk)
    item.quantity = quantity
    if note is not None:
        item.note = note
    if acknowledge_price:  # the customer has seen the current price; the notice goes away
        from apps.catalog.pricing import price_of

        item.price_seen = price_of(item.product, item.variant).price
    item.save(update_fields=["quantity", "note", "price_seen", "updated_at"])
    return item


def _reset_if_empty(cart: Cart) -> None:
    if not cart.items.exists():
        cart.mode, cart.store, cart.offer, cart.prescription = Cart.Mode.EMPTY, None, None, None
        cart.save(update_fields=["mode", "store", "offer", "prescription", "updated_at"])
    elif cart.offer_id and cart.mode in MULTI_STORE and not cart.items.filter(product__store_id=cart.offer.store_id).exists():
        cart.offer = None  # the offer's seller is no longer in the cart
        cart.save(update_fields=["offer", "updated_at"])


@transaction.atomic
def remove_item(item: CartItem) -> None:
    cart = item.cart
    item.delete()
    _reset_if_empty(cart)


@transaction.atomic
def clear_cart(cart: Cart) -> None:
    cart.items.all().delete()
    _reset_if_empty(cart)


def cart_items(cart: Cart) -> list[CartItem]:
    return list(cart.items.select_related("product", "product__store", "variant")
                .prefetch_related("options", "product__option_groups__options", "product__variants").order_by("created_at"))


@transaction.atomic
def set_offer(cart: Cart, offer_id) -> Cart:
    """Apply an offer after checking it really applies (seller in the cart, dates, minimum order, redeemable)."""
    cart = Cart.objects.select_for_update(of=("self",)).select_related("store").get(pk=cart.pk)
    items = cart_items(cart)
    if not items:
        raise DomainError("Add items to your cart first.", code="cart_empty")
    offer = StoreOffer.objects.filter(pk=offer_id).first()
    groups = {g.store.id: g for g in seller_groups(cart, items)}
    group = groups.get(getattr(offer, "store_id", None))
    if problem := offer_problem(offer, group.store if group else None, group.subtotal if group else Decimal("0")):
        raise DomainError(problem, code="offer_not_applicable")
    cart.offer = offer
    cart.save(update_fields=["offer", "updated_at"])
    return cart


def remove_offer(cart: Cart) -> Cart:
    cart.offer = None
    cart.save(update_fields=["offer", "updated_at"])
    return cart
