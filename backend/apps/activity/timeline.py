"""
The Activity timeline: what the customer did across Click., read from each service's own records (orders, rides, parcels,
bookings, payments, wallet, rewards, wishlist, Buddy, support) — nothing is copied, every row links to the real record,
and a failed action is shown as failed, never as done.

Cursor paging: each source returns its newest rows before the cursor (indexed by customer + created_at); the merged page
is the newest PAGE of those, and the next cursor is the last row's time.
"""

from __future__ import annotations

from datetime import datetime


PAGE = 20


def _row(cat, kind, title, subtitle, at, link, *, amount=None, status="", tone="", ref="", obj_id="") -> dict:
    return {"id": f"{cat}:{kind}:{obj_id}", "category": cat, "kind": kind, "title": title, "subtitle": subtitle, "at": at.isoformat(),
            "link": link, "amount": f"{amount:.2f}" if amount is not None else None, "status": status, "tone": tone, "reference": ref}


def _tone(status: str) -> str:
    s = status.lower()
    if any(w in s for w in ("cancel", "fail", "not completed", "rejected", "expired")):
        return "bad"
    if any(w in s for w in ("deliver", "complet", "paid", "confirm", "success", "refund", "credited", "resolved", "added", "earned")):
        return "ok"
    return "pending"


def _orders(c, before, n, cats):
    from apps.orders.models import Order

    types = {"food": "restaurant", "groceries": "grocery", "shop": "retail"}
    want = [t for k, t in types.items() if k in cats]
    if not want:
        return []
    out = []
    cat_of = {v: k for k, v in types.items()}
    for o in Order.objects.filter(customer=c, created_at__lt=before, store__store_type__in=want).select_related("store").order_by("-created_at")[:n]:
        cat = cat_of[o.store.store_type]
        verb = {"food": "Ordered from", "groceries": "Groceries from", "shop": "Bought from"}[cat]
        st = o.get_status_display()
        out.append(_row(cat, "order", f"{verb} {o.store.name}", o.number, o.created_at, f"/orders/{o.id}", amount=o.total, status=st, tone=_tone(st),
                        ref=o.number, obj_id=o.id))
    return out


def _simple(cat, qs, n, build):
    return [build(x) for x in qs.order_by("-created_at")[:n]]


def gather(c, before: datetime, cats: set[str], n: int) -> list[dict]:
    rows: list[dict] = []
    rows += _orders(c, before, n, cats)
    if "ride" in cats:
        rows += _simple("ride", c.rides.filter(created_at__lt=before), n, lambda r: _row(
            "ride", "ride", "Ride" + (" completed" if r.status == "completed" else " booked"), f"{r.pickup_label} → {r.drop_label}", r.created_at,
            f"/rides/{r.id}", amount=r.total, status=r.get_status_display(), tone=_tone(r.get_status_display()), ref=r.number, obj_id=r.id))
    if "parcel" in cats:
        rows += _simple("parcel", c.parcels.filter(created_at__lt=before), n, lambda p: _row(
            "parcel", "parcel", "Parcel sent", f"{p.pickup_label} → {p.drop_label}", p.created_at, f"/parcels/{p.id}", amount=p.total,
            status=p.get_status_display(), tone=_tone(p.get_status_display()), ref=p.number, obj_id=p.id))
    if "services" in cats:
        rows += _simple("services", c.service_bookings.filter(created_at__lt=before).select_related("category"), n, lambda b: _row(
            "services", "service", f"Booked {b.category.profession.lower()}", b.category.name, b.created_at, f"/services/bookings/{b.id}",
            amount=b.total, status=b.get_status_display(), tone=_tone(b.get_status_display()), ref=b.number, obj_id=b.id))
    if "events" in cats:
        rows += _simple("events", c.event_bookings.filter(created_at__lt=before).select_related("provider__partner"), n, lambda b: _row(
            "events", "event", f"Event booked · {b.title}", b.provider.partner.business_name, b.created_at, f"/events/bookings/{b.id}", amount=b.total,
            status=b.get_status_display(), tone=_tone(b.get_status_display()), ref=b.number, obj_id=b.id))
    if "hotels" in cats:
        rows += _simple("hotels", c.hotel_bookings.filter(created_at__lt=before).select_related("property__partner"), n, lambda b: _row(
            "hotels", "hotel", f"Hotel booked · {b.property.partner.business_name}", f"{b.check_in:%d %b} – {b.check_out:%d %b} · {b.nights} night{'s' if b.nights > 1 else ''}",
            b.created_at, f"/hotels/bookings/{b.id}", amount=b.total, status=b.get_status_display(), tone=_tone(b.get_status_display()), ref=b.number, obj_id=b.id))
    if "travel" in cats:
        rows += _simple("travel", c.travel_bookings.filter(created_at__lt=before).select_related("from_stop__place__city", "to_stop__place__city"), n, lambda b: _row(
            "travel", "travel", f"{b.get_mode_display()} ticket · {b.from_stop.place.city_place.name} → {b.to_stop.place.city_place.name}", b.operator_name,
            b.created_at, f"/travel/bookings/{b.id}", amount=b.total, status=b.get_status_display(), tone=_tone(b.get_status_display()),
            ref=b.pnr or b.number, obj_id=b.id))
    if "bookings" in cats:
        rows += _simple("bookings", c.experience_bookings.filter(created_at__lt=before).select_related("attraction", "offering"), n, lambda b: _row(
            "bookings", "visit", f"Booked {b.offering.name}", b.attraction.name, b.created_at, f"/bookings/r/{b.id}", amount=b.total,
            status=b.get_status_display(), tone=_tone(b.get_status_display()), ref=b.number, obj_id=b.id))
    if "shows" in cats:
        rows += _simple("shows", c.bookings.filter(created_at__lt=before).select_related("show__event", "show__venue"), n, lambda b: _row(
            "shows", "show", f"Tickets · {b.show.event.title}", b.show.venue.name, b.created_at, f"/tickets/{b.id}", amount=b.total,
            status=b.get_status_display(), tone=_tone(b.get_status_display()), ref=b.reference, obj_id=b.id))
    if "payments" in cats:
        from apps.payments.records import describe, owned, status_of, with_relations

        for p in with_relations(owned(c).filter(created_at__lt=before)).order_by("-created_at")[:n]:
            st, label = status_of(p)
            d = describe(p)
            title = {"successful": "Payment successful", "failed": "Payment failed", "pending": "Payment pending", "refunded": "Payment refunded",
                     "partly_refunded": "Payment partly refunded", "cancelled": "Payment cancelled"}[st]
            rows.append(_row("payments", "payment", title, f"{d['label']} · {p.get_method_display()}", p.created_at, f"/account/payments/{p.id}",
                             amount=p.amount, status=label, tone=_tone(label), ref=f"PAY-{str(p.id)[:8].upper()}", obj_id=p.id))
    if "wallet" in cats:
        rows += _simple("wallet", c.wallet_transactions.filter(created_at__lt=before), n, lambda t: _row(
            "wallet", t.kind, t.get_kind_display(), t.description, t.created_at, f"/wallet/activity/{t.id}",
            amount=t.amount, status="Credited" if t.amount > 0 else ("Expired" if t.kind == "expiry" else "Debited"),
            tone="bad" if t.kind == "expiry" else "ok", ref=str(t.id)[:8].upper(), obj_id=t.id))
    if "rewards" in cats:
        rows += _simple("rewards", c.reward_transactions.filter(created_at__lt=before), n, lambda t: _row(
            "rewards", t.kind, f"{'+' if t.points > 0 else '−'}{abs(t.points):,} points", t.description, t.created_at, "/rewards", status=t.get_kind_display(),
            tone="ok" if t.points > 0 else "", ref=str(t.id)[:8].upper(), obj_id=t.id))
    if "wishlist" in cats:
        rows += _wishlist(c, before, n)
    if "buddy" in cats:
        rows += _simple("buddy", c.buddy_conversations.filter(created_at__lt=before), n, lambda v: _row(
            "buddy", "conversation", f"Asked Buddy: {v.title or 'conversation'}", "Buddy", v.created_at, f"/buddy?c={v.id}", obj_id=v.id))
    if "support" in cats:
        rows += _simple("support", c.support_tickets.filter(created_at__lt=before), n, lambda t: _row(
            "support", "ticket", f"Support request · {t.subject}", t.get_category_display(), t.created_at, f"/help/tickets/{t.id}",
            status=t.get_status_display(), tone=_tone(t.get_status_display()), ref=t.reference, obj_id=t.id))
    return rows


def _wishlist(c, before, n):
    out = []
    for w in c.wishlist_items.filter(created_at__lt=before).select_related("store", "product", "hotel__partner", "attraction", "travel_route__origin",
                                                                         "travel_route__destination").order_by("-created_at")[:n]:
        if w.store_id:
            name, link = w.store.name, f"/stores/{w.store.slug}"
        elif w.product_id:
            name, link = w.product.name, f"/products/{w.product_id}"
        elif w.hotel_id:
            name, link = w.hotel.partner.business_name, f"/hotels/{w.hotel_id}"
        elif w.attraction_id:
            name, link = w.attraction.name, f"/bookings/places/{w.attraction.slug}"
        elif w.travel_route_id:
            name, link = f"{w.travel_route.origin.name} → {w.travel_route.destination.name}", f"/travel?to={w.travel_route.destination.slug}"
        else:
            name, link = "Saved item", "/wishlist"
        out.append(_row("wishlist", "saved", f"Saved {name}", "Wishlist", w.created_at, link, obj_id=w.id))
    return out


CATEGORIES = ["food", "groceries", "shop", "ride", "parcel", "services", "travel", "hotels", "shows", "events", "bookings", "payments", "wallet",
              "rewards", "wishlist", "buddy", "support"]


def timeline(c, category: str | None, before: datetime, q: str = "", status: str = "") -> dict:
    """One page of the timeline. Each source returns at most n rows, so the merged list is only complete down to the
    newest "last row" of any source that hit its limit (the horizon). Rows older than that wait for the next page;
    with a search or status filter a page can hold fewer than PAGE matches and still have a cursor to look further back."""
    cats = {category} if category in CATEGORIES else set(CATEGORIES)
    n = PAGE * 3 if (q or status) else PAGE
    rows = gather(c, before, cats, n)
    per_source: dict[str, list[str]] = {}
    for r in rows:
        per_source.setdefault("orders" if r["category"] in ("food", "groceries", "shop") else r["category"], []).append(r["at"])
    full = [min(ats) for ats in per_source.values() if len(ats) >= n]
    horizon = max(full) if full else None
    if horizon:
        rows = [r for r in rows if r["at"] >= horizon]
    if q:
        ql = q.lower().replace("₹", "").replace(",", "").strip()
        rows = [r for r in rows if ql in r["title"].lower() or ql in r["subtitle"].lower() or ql in r["reference"].lower() or (r["amount"] and ql in r["amount"])]
    if status in ("ok", "bad", "pending"):
        rows = [r for r in rows if r["tone"] == status]
    rows.sort(key=lambda r: r["at"], reverse=True)
    page = rows[:PAGE]
    nxt = page[-1]["at"] if len(page) == PAGE else horizon
    return {"results": page, "next_cursor": nxt, "categories": CATEGORIES}
