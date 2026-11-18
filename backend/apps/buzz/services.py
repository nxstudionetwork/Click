"""
Click. Buzz: an actionable discovery feed.

Every Buzz item is a real Click record (an active offer, a show that can be booked, a store taking orders) presented
as a short "instant" with exactly one action that leads into the matching Click flow (order, shop, book). Nothing is
invented here: if a domain has no live records, it contributes no items.

Partner posts (apps.buzz.models.BuzzPost, written from the Partner App and approved by Click) are one more source
with the same item shape, plus a `post` block with engagement and the attached item/offer. Their action is always
one of the partner's own live listings, re-checked when served.
"""

from dataclasses import asdict, dataclass
from itertools import chain, zip_longest

from apps.bookings.models import Event
from apps.bookings.views import public_events
from apps.stores.models import Store, StoreType
from apps.stores.views import active_offers, public_stores

THEME = {StoreType.RESTAURANT: "food", StoreType.GROCERY: "grocery", StoreType.RETAIL: "shopping", StoreType.PHARMACY: "shopping"}
STORE_VERB = {StoreType.RESTAURANT: "Order now", StoreType.GROCERY: "Shop groceries", StoreType.RETAIL: "Shop now",
              StoreType.PHARMACY: "Shop pharmacy"}


def _store_path(s) -> str:
    """Where a store opens in the Customer App (every store type has one)."""
    return {StoreType.GROCERY: f"/groceries/store/{s.slug}", StoreType.PHARMACY: "/pharma"}.get(s.store_type, f"/stores/{s.slug}")
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
    kind: str  # "offer" | "event" | "trailer" | "store" | "product" | "event_team" (later: "post")
    theme: str  # Click service theme, so the client can style it
    title: str
    body: str
    tag: str  # short label, e.g. "Offer", "Now showing", "Top rated"
    source: BuzzSource
    media_url: str  # real image/video URL when the source has one; empty otherwise (never generated)
    media_type: str  # "image" | "video" | ""
    action: BuzzAction
    published_at: str
    post: dict | None = None  # partner posts only: {likes, liked, saved, item, offer}


def _offer_items(limit):
    offers = active_offers().filter(store__status=Store.Status.ACTIVE, store__is_accepting_orders=True).select_related("store")
    for o in offers.order_by("-created_at")[:limit]:
        s = o.store
        yield BuzzItem(
            id=f"offer:{o.id}", kind="offer", theme=THEME[s.store_type], title=o.title,
            body=o.description or f"At {s.name}, {s.locality or s.city}.", tag="Offer",
            source=BuzzSource(s.name, s.slug), media_url=s.image_url, media_type="image" if s.image_url else "",
            action=BuzzAction(STORE_VERB[s.store_type], _store_path(s)), published_at=o.created_at.isoformat(),
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
            action=BuzzAction(STORE_VERB[s.store_type], _store_path(s)), published_at=s.created_at.isoformat(),
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


def _event_team_items(limit):
    """Click. Events: listed event teams and venues with a real package (featured first). Media only if they uploaded a cover."""
    from apps.eventhub import engine as events

    providers = events.listed().filter(packages__is_active=True).distinct().order_by("-is_featured", "-rating_average")
    for p in providers[:limit]:
        pkg = min((x for x in p.packages.all() if x.is_active), key=lambda x: x.price)
        cover = events.cover_url(p)
        services = " · ".join(s.name for s in list(p.services.all())[:3])
        yield BuzzItem(
            id=f"eventteam:{p.id}", kind="event_team", theme="events", title=events.name_of(p),
            body=f"{pkg.name} {events.package_label(pkg).lower()}" + (f" · {services}" if services else ""),
            tag="Venue" if p.kind == "venue" else ("Featured event team" if p.is_featured else p.get_kind_display()),
            source=BuzzSource("Click. Events", "events"), media_url=cover, media_type="image" if cover else "",
            action=BuzzAction("View packages", f"/events/providers/{p.id}"), published_at=p.created_at.isoformat(),
        )


def _post_items(limit, user=None):
    """Approved, live partner posts. A post whose listing, item or offer is no longer live is not served."""
    from .models import BuzzReaction
    from .partner import CTA_LABEL, THEME, listings, live_posts, media_url, partner_mode

    posts = list(live_posts().order_by("-publish_at", "-reviewed_at")[: limit * 2])
    mine = set()
    if user is not None and user.is_authenticated:
        mine = set(BuzzReaction.objects.filter(user=user, post__in=posts).values_list("post_id", "kind"))
    n, by_partner = 0, {}
    for p in posts:
        if p.partner_id not in by_partner:  # one lookup per partner, not per post
            by_partner[p.partner_id] = listings(p.partner)
        listing = next((x for x in by_partner[p.partner_id] if x["type"] == p.target_type and x["id"] == p.target_id), None)
        if listing is None or (p.store_offer_id and not _offer_live(p.store_offer)):
            continue
        media = next(iter(p.media.all()), None)
        mode = partner_mode(p.partner)
        theme = "grocery" if listing.get("store_type") == "grocery" else THEME.get(mode, "shopping")
        yield BuzzItem(
            id=f"post:{p.id}", kind="post", theme=theme, title=p.headline, body=p.caption, tag=p.get_kind_display(),
            source=BuzzSource(p.partner.business_name, listing["handle"]),
            media_url=media_url(media, 1080) if media else "", media_type=media.kind if media else "",
            action=BuzzAction(CTA_LABEL[p.cta], listing["link"]),
            published_at=(p.publish_at or p.reviewed_at or p.created_at).isoformat(),
            post={"likes": p.likes, "liked": (p.id, "like") in mine, "saved": (p.id, "save") in mine,
                  "item": {"name": p.product.name, "price": f"{p.product.price:.2f}", "available": p.product.is_available}
                  if p.product and p.product.is_active else None,
                  "offer": p.store_offer.title if p.store_offer_id else None},
        )
        n += 1
        if n >= limit:
            break


def _offer_live(offer) -> bool:
    from apps.stores.views import active_offers

    return active_offers().filter(pk=offer.pk).exists()


def build_feed(limit: int = 12, user=None) -> list[dict]:
    """Interleave sources so the feed alternates between partner posts, offers, shows and places."""
    limit = max(1, min(limit, MAX_ITEMS))
    per_source = limit
    sources = [list(_post_items(per_source, user)), list(_offer_items(per_source)), list(_product_deal_items(per_source)), list(_event_items(per_source)), list(_trailer_items(per_source)),
               list(_grocery_items(per_source)), list(_event_team_items(per_source)), list(_store_items(per_source))]
    mixed = [item for item in chain.from_iterable(zip_longest(*sources)) if item is not None]
    return [asdict(i) for i in mixed[:limit]]


# --- engagement on partner posts ---------------------------------------------------------------------------------

def _live_post(post_id):
    from apps.core.api.exceptions import DomainError

    from .partner import live_posts

    post = live_posts(audience=None).filter(pk=post_id).first()
    if post is None:
        raise DomainError("This post isn't available any more.", code="not_found", status_code=404)
    return post


def toggle_reaction(user, post_id, kind: str) -> dict:
    from django.db import transaction

    from .models import BuzzPost, BuzzReaction

    post = _live_post(post_id)
    with transaction.atomic():
        existing = BuzzReaction.objects.filter(post=post, user=user, kind=kind)
        on = not existing.exists()
        if on:
            BuzzReaction.objects.get_or_create(post=post, user=user, kind=kind)
        else:
            existing.delete()
        count = BuzzReaction.objects.filter(post=post, kind=kind).count()
        BuzzPost.objects.filter(pk=post.pk).update(**{"likes" if kind == "like" else "saves": count})
    return {"on": on, "count": count}


def record_event(post_id, kind: str, viewer: str) -> bool:
    """A view or CTA click, counted once per viewer per day."""
    from django.db import IntegrityError, transaction
    from django.db.models import F
    from django.utils import timezone

    from .models import BuzzEvent, BuzzPost

    post = _live_post(post_id)
    try:
        with transaction.atomic():
            BuzzEvent.objects.create(post=post, kind=kind, viewer=viewer, day=timezone.localdate())
            BuzzPost.objects.filter(pk=post.pk).update(**{"views" if kind == "view" else "cta_clicks": F("views" if kind == "view" else "cta_clicks") + 1})
    except IntegrityError:
        return False
    return True


def report(user, post_id, reason: str, note: str = "") -> None:
    from apps.core.api.exceptions import DomainError

    from .models import BuzzReport

    post = _live_post(post_id)
    if reason not in BuzzReport.Reason.values:
        raise DomainError("Choose a reason.", code="validation_error", details={"reason": ["Choose a reason."]})
    if post.partner.memberships.filter(user=user).exists():
        raise DomainError("You can’t report your own post.", code="own_post")
    BuzzReport.objects.get_or_create(post=post, reporter=user, status=BuzzReport.Status.OPEN,
                                     defaults={"reason": reason, "note": str(note)[:300]})
