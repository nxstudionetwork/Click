"""
Click. Buzz: an actionable discovery feed.

Every Buzz item is a real Click record (an active offer, a show that can be booked, a store taking orders) presented
as a short "instant" with exactly one action that leads into the matching Click flow (order, shop, book). Nothing is
invented here: if a domain has no live records, it contributes no items.

Extension point: partner-published media posts (short videos and photos) will be a `BuzzPost` model owned by
`apps.partners`. They plug into `build_feed` as one more source with the same item shape; the API and the
Customer App do not change.
"""

from dataclasses import asdict, dataclass
from itertools import chain, zip_longest

from apps.bookings.models import Event
from apps.bookings.views import public_events
from apps.stores.models import Store, StoreType
from apps.stores.views import active_offers, public_stores

THEME = {StoreType.RESTAURANT: "food", StoreType.GROCERY: "grocery", StoreType.RETAIL: "shopping"}
STORE_VERB = {StoreType.RESTAURANT: "Order now", StoreType.GROCERY: "Shop groceries", StoreType.RETAIL: "Shop now"}
MAX_ITEMS = 30


@dataclass(frozen=True)
class BuzzSource:
    name: str
    handle: str  # partner handle shown as @handle (the store/venue slug)


@dataclass(frozen=True)
class BuzzAction:
    label: str
    path: str  # an in-app Click route


@dataclass(frozen=True)
class BuzzItem:
    id: str
    kind: str  # "offer" | "event" | "trailer" | "store" | "product" (later: "post")
    theme: str  # Click service theme, so the client can style it
    title: str
    body: str
    tag: str  # short label, e.g. "Offer", "Now showing", "Top rated"
    source: BuzzSource
    media_url: str  # real image/video URL when the source has one; empty otherwise (never generated)
    media_type: str  # "image" | "video" | ""
    action: BuzzAction
    published_at: str


def _offer_items(limit):
    offers = active_offers().filter(store__status=Store.Status.ACTIVE, store__is_accepting_orders=True).select_related("store")
    for o in offers.order_by("-created_at")[:limit]:
        s = o.store
        yield BuzzItem(
            id=f"offer:{o.id}", kind="offer", theme=THEME[s.store_type], title=o.title,
            body=o.description or f"At {s.name}, {s.locality or s.city}.", tag="Offer",
            source=BuzzSource(s.name, s.slug), media_url=s.image_url, media_type="image" if s.image_url else "",
            action=BuzzAction(STORE_VERB[s.store_type], (f"/groceries/store/{s.slug}" if s.store_type == StoreType.GROCERY else f"/stores/{s.slug}")), published_at=o.created_at.isoformat(),
        )


def _trailer_items(limit):
    """Titles with a licensed trailer: watch in Buzz, then open the title to book."""
    for e in public_events().exclude(trailer_url="").order_by("title")[:limit]:
        yield BuzzItem(
            id=f"trailer:{e.id}", kind="trailer", theme="movies", title=e.title, body=e.tagline or e.genres.replace(",", " ·"),
            tag="Trailer", source=BuzzSource("Click. Showtime", "showtime"), media_url=e.trailer_url, media_type="video",
            action=BuzzAction("See showtimes", f"/showtime/{e.slug}"), published_at=e.created_at.isoformat(),
        )


def _event_items(limit):
    events = public_events().filter(status=Event.Status.NOW_SHOWING, next_show_at__isnull=False).order_by("next_show_at")
    for e in events[:limit]:
        verb = "Book tickets" if e.kind == Event.Kind.MOVIE else "Book now"
        yield BuzzItem(
            id=f"event:{e.id}", kind="event", theme="movies", title=e.title,
            body=e.tagline or e.genres.replace(",", " ·"), tag="Now showing" if e.kind == Event.Kind.MOVIE else "Live event",
            source=BuzzSource("Click. Showtime", "showtime"), media_url=e.poster_url, media_type="image" if e.poster_url else "",
            action=BuzzAction(verb, f"/showtime/{e.slug}"), published_at=e.created_at.isoformat(),
        )


def _store_items(limit):
    stores = public_stores().filter(is_accepting_orders=True, rating_count__gt=0).order_by("-rating_average", "-rating_count")
    for s in stores[:limit]:
        cats = ", ".join(c.name for c in s.categories.all()[:2])
        yield BuzzItem(
            id=f"store:{s.id}", kind="store", theme=THEME[s.store_type], title=s.name,
            body=f"{cats} · rated {s.rating_average} by {s.rating_count:,} customers", tag="Top rated",
            source=BuzzSource(s.name, s.slug), media_url=s.image_url, media_type="image" if s.image_url else "",
            action=BuzzAction(STORE_VERB[s.store_type], (f"/groceries/store/{s.slug}" if s.store_type == StoreType.GROCERY else f"/stores/{s.slug}")), published_at=s.created_at.isoformat(),
        )


def _product_deal_items(limit):
    """Shoppable Shopping deals: each opens the real product page (where it can be added to the cart)."""
    from apps.catalog.images import image_urls
    from apps.catalog.pricing import active_deals
    from apps.shop.listings import listings

    seen = set()
    for d in active_deals().filter(product__in=listings().values("id")).select_related("product__store").order_by("ends_at"):
        p = d.product
        if p.id in seen:
            continue
        seen.add(p.id)
        img = p.images.first()
        media = image_urls(img)["src"] if img else p.image_url
        yield BuzzItem(
            id=f"product:{p.id}", kind="product", theme="shopping", title=p.name,
            body=f"{d.percent_off}% off at {p.store.name} · {d.get_kind_display()}", tag=d.get_kind_display(),
            source=BuzzSource(p.store.name, p.store.slug), media_url=media, media_type="image" if media else "",
            action=BuzzAction("View product", f"/products/{p.id}"), published_at=d.starts_at.isoformat(),
        )
        if len(seen) >= limit:
            break


def _grocery_items(limit):
    """Produce a local store actually received today (from its stock records), opening that listing."""
    from apps.groceries.catalog import orderable_listings
    from apps.groceries.delivery import now_local

    seen = set()
    rows = orderable_listings().filter(received_on=now_local().date()).exclude(grocery_item__image_url="").order_by("-units_sold")
    for p in rows[:60]:
        if p.store_id in seen:
            continue
        seen.add(p.store_id)
        item = p.grocery_item
        yield BuzzItem(
            id=f"grocery:{p.id}", kind="product", theme="grocery", title=f"Fresh {item.name.lower()} at {p.store.name}",
            body=f"Received today · {item.size_label} for ₹{p.price:.0f}", tag="Fresh today",
            source=BuzzSource(p.store.name, p.store.slug), media_url=item.image_url, media_type="image",
            action=BuzzAction("View", f"/groceries/p/{p.id}"), published_at=p.updated_at.isoformat(),
        )
        if len(seen) >= limit:
            break


def build_feed(limit: int = 12) -> list[dict]:
    """Interleave sources so the feed alternates between offers, shows and places."""
    limit = max(1, min(limit, MAX_ITEMS))
    per_source = limit
    sources = [list(_offer_items(per_source)), list(_product_deal_items(per_source)), list(_event_items(per_source)), list(_trailer_items(per_source)),
               list(_grocery_items(per_source)), list(_store_items(per_source))]
    mixed = [item for item in chain.from_iterable(zip_longest(*sources)) if item is not None]
    return [asdict(i) for i in mixed[:limit]]
