"""
Click. Reviews & Ratings: one layer over the reviews each service already keeps (orders, products, rides, hotels,
travel, places & experiences, events, services, shows). It answers three questions from those records:

  pending(customer)  completed transactions the customer may still review (the backend decides eligibility)
  history(customer)  every review the customer has written, with its linked order / booking
  submit(...)        writes through the owning service's own review function, so its rules, uniqueness and rating
                     aggregates stay in one place — no second review table

Ratings are 1–5 stars in the app; services that keep 1–10 (hotels) are converted here. "What did you like?" and
"What could be better?" are stored in the service's comment.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.core.api.exceptions import DomainError

WINDOW_DAYS = 60  # how long after completion a transaction is offered for review

# kind -> (label, aspects asked for, service, icon theme)
KINDS = {
    "order": ("Order", [], "food"),
    "product": ("Product", [], "shop"),
    "ride": ("Ride", [], "ride"),
    "hotel": ("Stay", ["cleanliness", "location", "comfort", "facilities", "staff", "value"], "hotels"),
    "travel": ("Journey", [], "travel"),
    "experience": ("Visit", [], "bookings"),
    "event": ("Event", ["quality", "communication", "value"], "events"),
    "service": ("Service", ["quality", "behaviour", "timeliness"], "services"),
    "show": ("Show", [], "shows"),
}
ASPECT_LABEL = {"cleanliness": "Cleanliness", "location": "Location", "comfort": "Comfort", "facilities": "Facilities", "staff": "Staff",
                "value": "Value", "quality": "Quality", "communication": "Communication", "behaviour": "Professionalism", "timeliness": "Punctuality"}


def _since():
    return timezone.now() - timedelta(days=WINDOW_DAYS)


def _row(kind, target_id, title, subtitle, at, link):
    label, aspects, service = KINDS[kind]
    return {"kind": kind, "kind_label": label, "target_id": str(target_id), "title": title, "subtitle": subtitle, "completed_at": at.isoformat() if at else None,
            "link": link, "service": service, "aspects": [{"code": a, "label": ASPECT_LABEL[a]} for a in aspects]}


def pending(customer) -> list[dict]:
    from apps.orders.models import OrderItem

    out, since = [], _since()
    for o in customer.orders.filter(status="delivered", review__isnull=True, delivered_at__gte=since).select_related("store")[:20]:
        if o.store.store_type != "retail":
            out.append(_row("order", o.id, o.store.name, f"Order {o.number}", o.delivered_at, f"/orders/{o.id}"))
    reviewed = set(customer.product_reviews.values_list("product_id", flat=True))
    seen = set()
    for i in OrderItem.objects.filter(order__customer=customer, order__status="delivered", order__store__store_type="retail",
                                      order__delivered_at__gte=since).select_related("order", "product")[:40]:
        if i.product_id and i.product_id not in reviewed and i.product_id not in seen:
            seen.add(i.product_id)
            out.append(_row("product", i.product_id, i.product_name, f"Order {i.order.number}", i.order.delivered_at, f"/products/{i.product_id}"))
    for r in customer.rides.filter(status="completed", rating__isnull=True, driver__isnull=False, created_at__gte=since)[:10]:
        out.append(_row("ride", r.id, f"{r.pickup_label} → {r.drop_label}", f"Ride {r.number}", r.created_at, f"/rides/{r.id}"))
    for b in customer.hotel_bookings.filter(status="completed", review__isnull=True, check_out__gte=since.date()).select_related("property__partner")[:10]:
        out.append(_row("hotel", b.id, b.property.partner.business_name, f"Stay {b.number}", b.updated_at, f"/hotels/bookings/{b.id}"))
    for b in customer.travel_bookings.filter(status="completed", rating__isnull=True, departs_at__gte=since).select_related("from_stop__place", "to_stop__place")[:10]:
        out.append(_row("travel", b.id, f"{b.from_stop.place.name} → {b.to_stop.place.name}", f"{b.operator_name} · {b.pnr or b.number}", b.arrives_at, f"/travel/bookings/{b.id}"))
    for b in customer.experience_bookings.filter(status="completed", review__isnull=True, visit_date__gte=since.date()).select_related("attraction")[:10]:
        out.append(_row("experience", b.id, b.attraction.name, f"Booking {b.number}", b.updated_at, f"/bookings/r/{b.id}"))
    for b in customer.event_bookings.filter(status="completed", review__isnull=True, updated_at__gte=since).select_related("provider__partner")[:10]:
        out.append(_row("event", b.id, b.provider.partner.business_name, b.title, b.updated_at, f"/events/bookings/{b.id}"))
    for b in customer.service_bookings.filter(status__in=["paid", "completed"], review__isnull=True, provider__isnull=False,
                                              updated_at__gte=since).select_related("provider__partner", "category")[:10]:
        out.append(_row("service", b.id, b.provider.partner.business_name, f"{b.category.name} · {b.number}", b.updated_at, f"/services/bookings/{b.id}"))
    shown = set(customer.show_reviews.values_list("event_id", flat=True))
    for b in customer.bookings.filter(status="confirmed", show__starts_at__lte=timezone.now(), show__starts_at__gte=since).select_related("show__event")[:20]:
        if b.show.event_id not in shown:
            shown.add(b.show.event_id)
            out.append(_row("show", b.show.event_id, b.show.event.title, f"Ticket {b.reference}", b.show.starts_at, f"/showtime/{b.show.event.slug}"))
    out.sort(key=lambda r: r["completed_at"] or "", reverse=True)
    return out


def _five(v10) -> int:
    return max(1, min(5, round(v10 / 2)))


def history(customer) -> list[dict]:
    rows = []

    def add(kind, r, title, rating, comment, link, status="published", target=""):
        rows.append({"id": str(r.id), "kind": kind, "kind_label": KINDS[kind][0], "title": title, "rating": rating, "comment": comment,
                     "created_at": r.created_at.isoformat(), "link": link, "status": status, "service": KINDS[kind][2], "target": target})

    for r in customer.reviews.select_related("order", "store"):
        add("order", r, r.store.name, r.rating, r.comment, f"/orders/{r.order_id}", target=f"Order {r.order.number}")
    for r in customer.product_reviews.select_related("product"):
        add("product", r, r.product.name, r.rating, r.body, f"/products/{r.product_id}", r.status, target="Verified purchase" if r.verified_purchase else "")
    from apps.rides.models import RideRating

    for r in RideRating.objects.filter(ride__customer=customer).select_related("ride"):
        add("ride", r, f"{r.ride.pickup_label} → {r.ride.drop_label}", r.stars, r.comment, f"/rides/{r.ride_id}", target=f"Ride {r.ride.number}")
    for r in customer.hotel_reviews.select_related("property__partner", "booking"):
        add("hotel", r, r.property.partner.business_name, _five(r.overall), r.comment, f"/hotels/bookings/{r.booking_id}", "published" if r.is_published else "hidden",
            target=f"Stay {r.booking.number}")
    for r in customer.trip_ratings.select_related("booking", "operator"):
        add("travel", r, r.operator.name, r.rating, r.comment, f"/travel/bookings/{r.booking_id}", target=f"Journey {r.booking.pnr or r.booking.number}")
    for r in customer.experience_reviews.select_related("attraction", "booking"):
        add("experience", r, r.attraction.name, r.rating, r.comment, f"/bookings/r/{r.booking_id}", "published" if r.is_published else "hidden", target=f"Booking {r.booking.number}")
    for r in customer.event_reviews.select_related("provider__partner", "booking"):
        add("event", r, r.provider.partner.business_name, r.overall, r.comment, f"/events/bookings/{r.booking_id}", "published" if r.is_published else "hidden",
            target=r.booking.title)
    for r in customer.service_reviews.select_related("provider__partner", "booking"):
        add("service", r, r.provider.partner.business_name, r.overall, r.comment, f"/services/bookings/{r.booking_id}", r.status, target=f"Job {r.booking.number}")
    for r in customer.show_reviews.select_related("event"):
        add("show", r, r.event.title, r.rating, r.body, f"/showtime/{r.event.slug}", r.status)
    rows.sort(key=lambda x: x["created_at"], reverse=True)
    return rows


def _text(liked: str, better: str) -> str:
    liked, better = (liked or "").strip(), (better or "").strip()
    return "\n\n".join(p for p in [liked, f"Could be better: {better}" if better else ""] if p)[:1000]


def submit(customer, kind: str, target_id: str, rating: int, liked: str = "", better: str = "", aspects: dict | None = None):
    """Writes the review through the owning service. Ownership and eligibility are that service's checks."""
    aspects = {k: max(1, min(5, int(v))) for k, v in (aspects or {}).items() if k in ASPECT_LABEL}
    if kind not in KINDS:
        raise DomainError("This can’t be reviewed.", code="review_not_allowed")
    if not 1 <= int(rating) <= 5:
        raise DomainError("Choose 1 to 5 stars.", code="validation_error")
    a = lambda k: aspects.get(k, rating)  # noqa: E731 — aspects the customer skipped take the overall rating
    text = _text(liked, better)
    nf = DomainError("Not found.", code="not_found", status_code=404)
    if kind == "order":
        from apps.orders.services import submit_review

        o = customer.orders.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return submit_review(o, customer=customer, rating=rating, comment=text[:500])
    if kind == "product":
        from apps.catalog.models import Product
        from apps.shop.reviews import save_review

        p = Product.objects.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return save_review(customer, p, rating=rating, body=text, create=True)
    if kind == "ride":
        from apps.rides.services import rate

        r = customer.rides.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return rate(r, stars=rating, comment=text[:500])
    if kind == "hotel":
        from apps.hotels.booking import review

        b = customer.hotel_bookings.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return review(customer, b, {"overall": rating * 2, **{k: a(k) * 2 for k in KINDS["hotel"][1]}, "comment": text})
    if kind == "travel":
        from apps.travel.booking import rate as rate_trip

        b = customer.travel_bookings.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return rate_trip(customer, b, rating, text)
    if kind == "experience":
        from apps.experiences.booking import review

        b = customer.experience_bookings.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return review(customer, b, rating, text)
    if kind == "event":
        from apps.eventhub.lifecycle import review

        b = customer.event_bookings.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return review(customer, b, {"overall": rating, "quality": a("quality"), "communication": a("communication"), "value": a("value"), "comment": text})
    if kind == "service":
        from apps.professionals.lifecycle import review

        b = customer.service_bookings.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
        return review(customer, b, {"overall": rating, "quality": a("quality"), "behaviour": a("behaviour"), "timeliness": a("timeliness"), "comment": text})
    from apps.bookings.engagement import save_review
    from apps.bookings.models import Event

    e = Event.objects.filter(pk=target_id).first() or (_ for _ in ()).throw(nf)
    return save_review(customer, e, rating=rating, body=text, create=True)


REVIEW_MODELS = {  # for reports: kind -> (app_label.Model, hide field, hidden value)
    "product": ("shop.ProductReview", "status", "hidden"), "service": ("professionals.ServiceReview", "status", "hidden"),
    "show": ("bookings.ShowReview", "status", "hidden"), "hotel": ("hotels.HotelReview", "is_published", False),
    "experience": ("experiences.ExperienceReview", "is_published", False), "event": ("eventhub.EventReview", "is_published", False),
}
AUTO_HIDE_REPORTS = 3


def report(customer, kind: str, review_id: str, reason: str, note: str = "") -> bool:
    """Report a published review. After AUTO_HIDE_REPORTS different customers report it, it is hidden pending review."""
    from django.apps import apps as django_apps
    from django.db import IntegrityError

    from .models import ReviewReport

    if kind not in REVIEW_MODELS:
        raise DomainError("This review can’t be reported here.", code="validation_error")
    path, field, hidden = REVIEW_MODELS[kind]
    Model = django_apps.get_model(path)
    r = Model.objects.filter(pk=review_id).first()
    if r is None:
        raise DomainError("Not found.", code="not_found", status_code=404)
    if r.customer_id == customer.id:
        raise DomainError("You can’t report your own review.", code="validation_error")
    try:
        ReviewReport.objects.create(kind=kind, review_id=r.id, reporter=customer, reason=reason, note=note[:300])
    except IntegrityError:
        return False
    if ReviewReport.objects.filter(kind=kind, review_id=r.id, resolved=False).count() >= AUTO_HIDE_REPORTS:
        hidden_value = hidden
        if field == "status" and hidden_value not in [c[0] for c in Model._meta.get_field("status").choices]:
            hidden_value = next((c[0] for c in Model._meta.get_field("status").choices if c[0] != "published"), "published")
        Model.objects.filter(pk=r.pk).update(**{field: hidden_value})
    return True
