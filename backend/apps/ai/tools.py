"""
Buddy's tools: the only way Buddy reads Click data. Every tool is scoped to
the requesting customer, returns API-contract shaped data, and is read-only.
Buddy never places orders or payments; it links the customer into the
normal flows where they review and confirm.
"""

from django.db.models import Q
from django.utils import timezone

from apps.bookings.serializers import BookingSerializer, EventSerializer
from apps.bookings.views import public_events
from apps.catalog.serializers import ProductWithStoreSerializer
from apps.catalog.views import public_products
from apps.orders.serializers import OrderSummarySerializer
from apps.rewards.services import balance as reward_balance
from apps.stores.serializers import OfferWithStoreSerializer, StoreSerializer
from apps.stores.views import active_offers, public_stores
from apps.wallet.services import balance as wallet_balance


def search_stores(q: str, store_type: str | None = None, limit: int = 4):
    qs = public_stores().filter(is_accepting_orders=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(categories__name__icontains=q) | Q(products__name__icontains=q))
    if store_type:
        qs = qs.filter(store_type=store_type)
    return StoreSerializer(qs.distinct().order_by("-rating_average")[:limit], many=True).data


def search_products(q: str, cheapest: bool = False, limit: int = 4):
    qs = public_products().filter(is_available=True, store__is_accepting_orders=True)
    qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(category__name__icontains=q))
    qs = qs.filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0))
    qs = qs.order_by("price") if cheapest else qs.order_by("-is_featured", "name")
    return ProductWithStoreSerializer(qs[:limit], many=True).data


def shop_search(text: str, limit: int = 4) -> dict | None:
    """Shopping search through the same interpreter and filters as the Shopping app. None when the text isn't
    recognisably a shopping request (no category, brand, audience or price understood)."""
    from urllib.parse import urlencode

    from apps.shop.query import interpret
    from apps.shop.services import search

    it = interpret(text)
    if not (it.category or it.brand or it.categories or it.colour):
        return None
    data = search({"q": text}, None)
    ids = [r["id"] for r in data["results"][:limit]]
    products = sorted(public_products().filter(pk__in=ids), key=lambda p: ids.index(str(p.pk)))
    return {"understood": [u["label"] for u in it.understood], "count": data["count"],
            "products": ProductWithStoreSerializer(products, many=True).data, "path": "/shopping/search?" + urlencode({"q": text})}


def showtime_search(text: str, limit: int = 4) -> dict:
    """Showtime search with the same plain-language interpretation as the app (language, genre, format, tonight)."""
    from urllib.parse import urlencode

    from apps.bookings import showtime

    it = showtime.interpret(text)
    params = {"q": text}
    data = showtime.search(params, None)
    slugs = [t["slug"] for t in data["titles"][:limit]]
    events = sorted(public_events().filter(slug__in=slugs), key=lambda e: slugs.index(e.slug))
    return {"understood": [u["label"] for u in it["understood"]], "count": data["count"],
            "events": EventSerializer(events, many=True).data, "path": "/showtime/search?" + urlencode(params)}


def find_events(q: str = "", tonight: bool = False, limit: int = 4):
    qs = public_events().filter(status="now_showing", next_show_at__isnull=False)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(genres__icontains=q))
    if tonight:
        end = timezone.localtime().replace(hour=23, minute=59)
        qs = qs.filter(shows__starts_at__gt=timezone.now(), shows__starts_at__lte=end, shows__status="scheduled").distinct()
    return EventSerializer(qs[:limit], many=True).data


def recent_orders(customer, limit: int = 3):
    qs = customer.orders.select_related("store").prefetch_related("items", "payments")[:limit]
    return list(qs), OrderSummarySerializer(qs, many=True).data


def upcoming_bookings(customer, limit: int = 3):
    qs = (customer.bookings.filter(status="confirmed", show__starts_at__gte=timezone.now())
          .select_related("show__event", "show__venue").prefetch_related("seats", "payments").order_by("show__starts_at")[:limit])
    return BookingSerializer(qs, many=True).data


def offers(limit: int = 4):
    return OfferWithStoreSerializer(active_offers().filter(store__status="active").select_related("store")[:limit], many=True).data


def wallet(customer):
    return wallet_balance(customer)


def rewards(customer):
    return reward_balance(customer)


def search_restaurants(q: str = "", veg: bool = False, cheapest: bool = False, limit: int = 4):
    """Restaurants taking orders. `veg` = pure-veg kitchens (no non-veg dish on the menu); `cheapest` = lowest average
    dish price first. Both come from the menus themselves, never from a label someone typed."""
    from django.db.models import Avg, Count

    qs = public_stores().filter(is_accepting_orders=True, store_type="restaurant")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(categories__name__icontains=q) | Q(products__name__icontains=q))
    ids = list(qs.values_list("pk", flat=True).distinct())
    qs = public_stores().filter(pk__in=ids).annotate(
        avg_price=Avg("products__price"), nonveg=Count("products", filter=Q(products__dietary="non_veg"), distinct=True))
    if veg:
        qs = qs.filter(nonveg=0)
    qs = qs.order_by("avg_price") if cheapest else qs.order_by("-rating_average")
    return StoreSerializer(qs[:limit], many=True).data


def grocery_match(customer, item: str):
    """The grocery product to add for "milk": what this customer bought before if it's still available, otherwise the
    cheapest in-stock match from an open grocery store. None when nothing matches (Buddy then says so)."""
    from apps.orders.models import OrderItem

    qs = (public_products().filter(store__store_type="grocery", store__is_accepting_orders=True, is_available=True, name__icontains=item)
          .filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0)).select_related("store"))
    if customer is not None:
        bought = list(OrderItem.objects.filter(order__customer=customer, product__in=qs).order_by("-order__created_at")
                      .values_list("product_id", flat=True)[:1])
        if bought:
            return qs.filter(pk=bought[0]).first()
    return qs.order_by("price").first()
