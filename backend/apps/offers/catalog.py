"""
Reads live offers from every Click. service (each service's own offer table — nothing is copied) and normalises them to
one shape for the Offers hub, Home and Buddy. Badges and rankings are derived from the offer data with stated rules:

  ending_soon   ends within 48 hours            new         started within the last 3 days
  coupon        needs a code                     cashback    credited to Click. Wallet after the purchase
  click_offer   funded by Click. (no partner)    partner     run by a partner business
  new_user      first booking / order only (hidden once the customer has used that service)
  best value    estimated saving at the offer's minimum spend ÷ that spend (shown with the rule)
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

SERVICE_THEME = {"food": "food", "groceries": "grocery", "shop": "shopping", "ride": "ride", "parcel": "parcel", "services": "services",
                 "travel": "travel", "hotels": "hotels", "shows": "movies", "events": "events", "bookings": "bookings", "wallet": "wallet",
                 "rewards": "rewards"}
SERVICE_LABEL = {"food": "Food", "groceries": "Groceries", "shop": "Shop", "ride": "Ride", "parcel": "Parcel", "services": "Services",
                 "travel": "Travel", "hotels": "Hotels", "shows": "Shows", "events": "Events", "bookings": "Bookings", "wallet": "Wallet",
                 "rewards": "Rewards"}
STORE_SERVICE = {"restaurant": "food", "grocery": "groceries", "retail": "shop"}


def _live(qs, now, nullable=True):
    if nullable:
        return qs.filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now), Q(ends_at__isnull=True) | Q(ends_at__gt=now))
    return qs.filter(starts_at__lte=now, ends_at__gt=now)


def _money(x) -> str | None:
    return f"{Decimal(x):.2f}" if x is not None else None


def _row(ref, service, kind, title, description, *, percent=None, flat=None, max_discount=None, min_amount=None, code="", starts=None, ends=None,
         partner=None, link="", conditions=None, terms="", new_user=False, label="") -> dict:
    if not label:
        label = (f"{percent:g}% off" if percent else f"₹{flat:,.0f} off" if flat else "Offer")
        if kind == "cashback":
            label = f"{percent:g}% cashback"
        if kind == "free_delivery":
            label = "Free delivery"
    return {"id": ref, "service": service, "service_label": SERVICE_LABEL[service], "theme": SERVICE_THEME[service], "kind": kind,
            "title": title, "description": description, "benefit": label, "percent": float(percent) if percent else None,
            "flat": _money(flat), "max_discount": _money(max_discount), "min_amount": _money(min_amount) if min_amount else None,
            "code": code or None, "starts_at": starts.isoformat() if starts else None, "ends_at": ends.isoformat() if ends else None,
            "partner": partner, "link": link, "conditions": [c for c in (conditions or []) if c], "terms": terms, "new_user": new_user}


def _store_offers(now) -> list[dict]:
    from apps.stores.models import StoreOffer

    out = []
    for o in _live(StoreOffer.objects.filter(is_active=True, store__status="active").select_related("store"), now):
        s = o.store
        service = STORE_SERVICE.get(s.store_type, "shop")
        kind = "free_delivery" if o.discount_type == "free_delivery" else "discount" if o.discount_type else "info"
        link = f"/groceries/store/{s.slug}" if service == "groceries" else f"/stores/{s.slug}"
        out.append(_row(f"store:{o.id}", service, kind, o.title, o.description or f"At {s.name}",
                        percent=o.discount_value if o.discount_type == "percent" else None, flat=o.discount_value if o.discount_type == "flat" else None,
                        max_discount=o.max_discount, min_amount=o.min_order_amount, starts=o.starts_at, ends=o.ends_at,
                        partner={"name": s.name, "kind": SERVICE_LABEL[service], "rating": f"{s.rating_average:.1f}" if s.rating_count else None, "link": link},
                        link=link, conditions=[f"On orders from ₹{o.min_order_amount:,.0f}" if o.min_order_amount else "", f"Up to ₹{o.max_discount:,.0f} off" if o.max_discount else "",
                                               "Applied automatically at checkout"]))
    return out


def _hotel_offers(now) -> list[dict]:
    from apps.hotels.models import HotelOffer

    out = []
    for o in _live(HotelOffer.objects.filter(is_active=True).select_related("property__partner"), now, nullable=False):
        p = o.property
        link = f"/hotels/{p.id}" if p else "/hotels"
        out.append(_row(f"hotel:{o.id}", "hotels", "coupon" if o.code else "discount", o.title, o.get_kind_display(), percent=o.percent, max_discount=o.max_discount,
                        code=o.code, starts=o.starts_at, ends=o.ends_at, link=link,
                        partner={"name": p.partner.business_name, "kind": "Hotel", "rating": None, "link": link} if p else None,
                        conditions=[f"{o.min_nights}+ nights" if o.min_nights > 1 else "", f"Book {o.min_days_ahead}+ days ahead" if o.min_days_ahead else "",
                                    f"Check-in within {o.max_days_ahead} days" if o.max_days_ahead is not None else "",
                                    f"Up to ₹{o.max_discount:,.0f} off" if o.max_discount else "", f"Enter code {o.code} on the review page" if o.code else "Applied automatically on the review page"]))
    return out


def _show_offers(now) -> list[dict]:
    from apps.bookings.models import ShowOffer

    out = []
    for o in _live(ShowOffer.objects.filter(is_active=True).select_related("venue", "event"), now):
        link = f"/showtime/{o.event.slug}" if o.event_id else "/showtime"
        out.append(_row(f"show:{o.id}", "shows", "discount", o.title, o.description or (o.venue.name if o.venue_id else "Showtime"),
                        percent=o.discount_value if o.discount_type == "percent" else None, flat=o.discount_value if o.discount_type == "flat" else None,
                        max_discount=o.max_discount, min_amount=o.min_amount, starts=o.starts_at, ends=o.ends_at, link=link,
                        partner={"name": o.venue.name, "kind": "Cinema", "rating": None, "link": "/showtime"} if o.venue_id else None,
                        conditions=[f"{o.min_seats}+ seats" if o.min_seats > 1 else "", "Pay with Click. Wallet" if o.payment_method == "wallet" else "",
                                    f"Tickets from ₹{o.min_amount:,.0f}" if o.min_amount else ""]))
    return out


def _service_offers(now, customer) -> list[dict]:
    from apps.professionals.models import ServiceOffer

    used = bool(customer and customer.service_bookings.exists())
    out = []
    for o in _live(ServiceOffer.objects.filter(is_active=True).select_related("category"), now):
        if o.first_booking_only and used:
            continue  # new-customer offer the customer no longer qualifies for
        link = f"/services/{o.category.slug}" if o.category_id else "/services"
        out.append(_row(f"service:{o.id}", "services", "discount", o.title, o.description or (o.category.name if o.category_id else "Any service"),
                        percent=o.value if o.kind == "percent" else None, flat=o.value if o.kind == "flat" else None, max_discount=o.max_discount,
                        min_amount=o.min_amount, starts=o.starts_at, ends=o.ends_at, link=link, new_user=o.first_booking_only,
                        conditions=["Your first Services booking" if o.first_booking_only else "", f"Jobs from ₹{o.min_amount:,.0f}" if o.min_amount else ""]))
    return out


def _ride_offers(now) -> list[dict]:
    from apps.rides.models import RideOffer

    return [_row(f"ride:{o.id}", "ride", "discount", o.title, o.description or "On Click. rides",
                 percent=o.discount_value if o.discount_type == "percent" else None, flat=o.discount_value if o.discount_type == "flat" else None,
                 max_discount=o.max_discount, min_amount=o.min_fare, starts=o.starts_at, ends=o.ends_at, link="/rides",
                 conditions=[f"Fares from ₹{o.min_fare:,.0f}" if o.min_fare else "", ", ".join(t.name for t in o.ride_types.all()) or "Every ride type"])
            for o in _live(RideOffer.objects.filter(is_active=True).prefetch_related("ride_types"), now)]


def _travel_offers(now) -> list[dict]:
    from apps.travel.models import TravelOffer

    return [_row(f"travel:{o.id}", "travel", "coupon" if o.code else "discount", o.title, f"{o.get_mode_display() if o.mode else 'Bus, train and flight'} bookings",
                 percent=o.percent, max_discount=o.max_discount, min_amount=o.min_fare, code=o.code, starts=o.starts_at, ends=o.ends_at,
                 link=f"/travel?mode={o.mode}" if o.mode else "/travel",
                 conditions=[f"Fares from ₹{o.min_fare:,.0f}" if o.min_fare else "", f"Up to ₹{o.max_discount:,.0f} off" if o.max_discount else "",
                             f"Enter code {o.code} on the passenger page" if o.code else "Applied automatically at review"])
            for o in _live(TravelOffer.objects.filter(is_active=True), now, nullable=False)]


def _experience_offers(now) -> list[dict]:
    from apps.experiences.models import ExperienceOffer

    out = []
    for o in _live(ExperienceOffer.objects.filter(is_active=True).select_related("attraction"), now, nullable=False):
        a = o.attraction
        link = f"/bookings/places/{a.slug}" if a else (f"/bookings/search?group={o.group}" if o.group else "/bookings")
        out.append(_row(f"experience:{o.id}", "bookings", "coupon" if o.code else "discount", o.title, a.name if a else "Places & experiences",
                        percent=o.percent, max_discount=o.max_discount, min_amount=o.min_amount, code=o.code, starts=o.starts_at, ends=o.ends_at, link=link,
                        conditions=[f"Bookings from ₹{o.min_amount:,.0f}" if o.min_amount else "", f"Up to ₹{o.max_discount:,.0f} off" if o.max_discount else ""]))
    return out


SERVICE_LINK = {"food": "/food", "groceries": "/groceries", "shop": "/shopping", "travel": "/travel", "bookings": "/bookings", "hotels": "/hotels", "any": "/explore"}


def _cashback_offers(now) -> list[dict]:
    from apps.wallet.models import CashbackOffer

    out = []
    for o in CashbackOffer.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now):
        service = o.service if o.service in SERVICE_LABEL else "wallet"
        out.append(_row(f"cashback:{o.id}", "wallet" if o.service == "any" else service, "cashback", o.title,
                        f"Credited to your Click. Wallet after the {'order is delivered' if o.service in ('food', 'groceries', 'shop') else 'booking is completed'}",
                        percent=o.percent, max_discount=o.max_cashback, min_amount=o.min_amount, starts=o.starts_at, ends=o.ends_at,
                        link=SERVICE_LINK.get(o.service, "/wallet"),
                        conditions=["Pay with Click. Wallet" if o.wallet_payment_only else "", f"Up to ₹{o.max_cashback:,.0f} cashback",
                                    f"On ₹{o.min_amount:,.0f}+" if o.min_amount else "", f"Credit valid {o.credit_valid_days} days, spent before your cash balance"]))
    return out


def _reward_campaigns(now) -> list[dict]:
    from apps.rewards.models import RewardCampaign

    return [_row(f"rewards:{c.id}", "rewards", "reward_boost", c.title, c.description or "Bonus Click. points", starts=c.starts_at, ends=c.ends_at,
                 link=SERVICE_LINK.get(c.service, "/rewards"), label=f"{c.multiplier:g}× points",
                 conditions=[f"On {SERVICE_LABEL.get(c.service, 'every eligible service')} purchases" if c.service != "any" else "On every eligible purchase",
                             "Points are added after the order is delivered or the booking completed"])
            for c in RewardCampaign.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)]


def badges(o: dict, now) -> list[str]:
    out = []
    ends = o["ends_at"] and timezone.datetime.fromisoformat(o["ends_at"])
    starts = o["starts_at"] and timezone.datetime.fromisoformat(o["starts_at"])
    if ends and ends - now <= timedelta(hours=48):
        out.append("ending_soon")
    if starts and now - starts <= timedelta(days=3):
        out.append("new")
    if o["kind"] in ("coupon", "cashback", "free_delivery", "reward_boost"):
        out.append(o["kind"])
    out.append("partner" if o["partner"] else "click_offer")
    if o["new_user"]:
        out.append("new_user")
    return out


def value_score(o: dict) -> float:
    """Estimated saving at the minimum spend (or ₹500 when there's none) ÷ that spend — a transparent best-value rule."""
    spend = float(o["min_amount"] or 500)
    if o["percent"]:
        saving = spend * o["percent"] / 100
        if o["max_discount"]:
            saving = min(saving, float(o["max_discount"]))
    elif o["flat"]:
        saving = float(o["flat"])
    else:
        return 0.0
    return saving / spend


def all_offers(customer=None) -> list[dict]:
    now = timezone.now()
    rows = (_store_offers(now) + _hotel_offers(now) + _show_offers(now) + _service_offers(now, customer) + _ride_offers(now) + _travel_offers(now)
            + _experience_offers(now) + _cashback_offers(now) + _reward_campaigns(now))
    for o in rows:
        o["badges"] = badges(o, now)
        o["value_score"] = round(value_score(o), 4)
    return rows


def get(ref: str, customer=None) -> dict | None:
    return next((o for o in all_offers(customer) if o["id"] == ref), None)
