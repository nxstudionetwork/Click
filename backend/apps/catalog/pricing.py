"""
The one place prices are decided. Cart lines, checkout, product cards and the product page all use it, so a deal
or variant price can never differ between what is shown and what is charged.

  base price      = the variant's price, else the product's price (seller-set list price)
  reference price = the seller's genuine compare-at (MRP) price; during a deal, at least the base price
  effective price = base price minus an active deal's percentage, rounded to the rupee-paisa
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import F, Q
from django.utils import timezone

from .models import Product, ProductDeal, ProductVariant

TWO_PLACES = Decimal("0.01")
_UNSET = object()


def active_deals():
    now = timezone.now()
    return ProductDeal.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now).filter(
        Q(quantity_limit__isnull=True) | Q(units_sold__lt=F("quantity_limit")))


def attach_deals(products) -> None:
    """Load the active deal of many products in one query (sets `product._active_deal`)."""
    products = [p for p in products if p is not None]
    if not products:
        return
    deals = {}
    for d in active_deals().filter(product_id__in=[p.pk for p in products]).order_by("-percent_off"):
        deals.setdefault(d.product_id, d)
    for p in products:
        p._active_deal = deals.get(p.pk)


def deal_for(product: Product) -> ProductDeal | None:
    deal = getattr(product, "_active_deal", _UNSET)
    if deal is _UNSET:
        deal = active_deals().filter(product=product).order_by("-percent_off").first()
        product._active_deal = deal
    return deal


def apply_deal(base: Decimal, deal: ProductDeal | None) -> Decimal:
    if deal is None:
        return base
    return (base * (100 - deal.percent_off) / 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Price:
    price: Decimal                 # what the customer pays per unit
    reference: Decimal | None      # struck-out price (genuine compare-at, or list price during a deal)
    discount_percent: int | None
    deal: ProductDeal | None


def price_of(product: Product, variant: ProductVariant | None = None) -> Price:
    base = variant.price if variant is not None else product.price
    compare = variant.compare_at_price if variant is not None else product.compare_at_price
    deal = deal_for(product)
    price = apply_deal(base, deal)
    reference = compare if compare and compare > price else (base if deal else None)
    discount = int(round((1 - price / reference) * 100)) if reference else None
    return Price(price, reference, discount or None, deal)
