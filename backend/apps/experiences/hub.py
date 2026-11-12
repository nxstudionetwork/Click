"""
The central Bookings list: every reservation the customer holds across Click., read from each domain's own records
(Showtime tickets, hotel stays, travel tickets, event bookings, service bookings, attraction / temple / experience
bookings) and normalised to one shape. Nothing is copied, so there is exactly one record per transaction and each row
links to its own detail page.

  group   upcoming (still ahead / awaiting payment / in progress), completed, cancelled (incl. failed)
"""

from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone

from . import booking as exp_booking


def _dt(d, t=None) -> datetime:
    return datetime.combine(d, t or time(0, 0), tzinfo=exp_booking.tz())


def _row(kind, kind_label, theme, obj_id, ref, title, subtitle, when, group, status_label, amount, link, payment_label="") -> dict:
    return {"id": f"{kind}:{obj_id}", "kind": kind, "kind_label": kind_label, "theme": theme, "reference": ref, "title": title,
            "subtitle": subtitle, "when": when.isoformat() if when else None, "group": group, "status_label": status_label,
            "payment_label": payment_label, "amount": f"{amount:.2f}" if amount is not None else None, "link": link}


def _experiences(c) -> list[dict]:
    exp_booking.sweep()
    out = []
    for b in c.experience_bookings.select_related("attraction", "offering"):
        g = "upcoming" if b.status in ("pending_payment", "confirmed") else "completed" if b.status == "completed" else "cancelled"
        kind = "temple" if b.attraction.group == "spiritual" else "experience" if b.attraction.group == "experiences" else "attraction"
        label = {"temple": "Temple", "experience": b.attraction.get_kind_display(), "attraction": b.attraction.get_kind_display()}[kind]
        out.append(_row(kind, label, "bookings", b.id, b.number, b.offering.name, f"{b.attraction.name} · {b.attraction.city}",
                        _dt(b.visit_date, b.slot_time), g, b.get_status_display(), b.total, f"/bookings/r/{b.id}", b.get_payment_status_display()))
    return out


def _travel(c) -> list[dict]:
    from apps.travel import booking as tb

    tb.sweep()
    out = []
    for b in c.travel_bookings.select_related("from_stop__place__city", "to_stop__place__city"):
        g = "upcoming" if b.status in ("pending_payment", "confirmed") else "completed" if b.status == "completed" else "cancelled"
        out.append(_row("travel", b.get_mode_display(), "travel", b.id, b.pnr or b.number,
                        f"{b.from_stop.place.city_place.name} → {b.to_stop.place.city_place.name}", f"{b.operator_name} · {b.class_name}",
                        b.departs_at, g, b.get_status_display(), b.total, f"/travel/bookings/{b.id}", b.get_payment_status_display()))
    return out


def _hotels(c) -> list[dict]:
    from apps.hotels import booking as hb

    hb.expire_holds()
    hb.complete_past()
    out = []
    for b in c.hotel_bookings.select_related("property__partner", "property__destination"):
        g = "upcoming" if b.status in ("pending_payment", "confirmed") else "completed" if b.status == "completed" else "cancelled"
        out.append(_row("hotel", "Hotel", "hotels", b.id, b.number, b.property.partner.business_name,
                        f"{b.nights} night{'s' if b.nights != 1 else ''} · {b.room_name}", _dt(b.check_in), g, b.get_status_display(), b.total,
                        f"/hotels/bookings/{b.id}", b.get_payment_status_display()))
    return out


def _shows(c) -> list[dict]:
    now = timezone.now()
    out = []
    for b in c.bookings.select_related("show__event", "show__venue"):
        s = b.show
        g = "cancelled" if b.status == "cancelled" else "upcoming" if s.starts_at > now else "completed"
        out.append(_row("show", "Show", "movies", b.id, b.reference, s.event.title, s.venue.name, s.starts_at, g,
                        "Cancelled" if g == "cancelled" else "Confirmed" if g == "upcoming" else "Attended" if b.checked_in_at else "Completed",
                        b.total, f"/tickets/{b.id}"))
    return out


def _events(c) -> list[dict]:
    out = []
    for b in c.event_bookings.select_related("provider__partner"):
        g = "cancelled" if b.status == "cancelled" else "completed" if b.status == "completed" else "upcoming"
        out.append(_row("event", "Event", "events", b.id, b.number, b.title, b.provider.partner.business_name,
                        _dt(b.event_date, b.start_time), g, b.get_status_display(), b.total, f"/events/bookings/{b.id}", b.get_payment_status_display()))
    return out


def _services(c) -> list[dict]:
    out = []
    for b in c.service_bookings.select_related("category"):
        g = "cancelled" if b.status in ("cancelled", "unassigned") else "completed" if b.status in ("completed", "paid") else "upcoming"
        out.append(_row("service", "Service", "services", b.id, b.number, b.category.name,
                        "Scheduled" if b.scheduled_start else "As soon as possible", b.scheduled_start or b.created_at, g, b.get_status_display(),
                        b.total, f"/services/bookings/{b.id}"))
    return out


SOURCES = {"experience": _experiences, "travel": _travel, "hotel": _hotels, "show": _shows, "event": _events, "service": _services}
KIND_SOURCE = {"temple": "experience", "attraction": "experience", "experience": "experience", "travel": "travel", "hotel": "hotel",
               "show": "show", "event": "event", "service": "service"}


def my_bookings(customer, group: str = "upcoming", kind: str = "") -> dict:
    sources = [KIND_SOURCE[kind]] if kind in KIND_SOURCE else list(SOURCES)
    rows, failed = [], []
    for name in sources:
        try:
            rows += SOURCES[name](customer)
        except Exception:  # one domain failing never hides the others; the client says which couldn't load
            failed.append(name)
    if kind in KIND_SOURCE and kind not in ("travel", "hotel", "show", "event", "service"):
        rows = [r for r in rows if r["kind"] == kind]
    counts = {g: sum(1 for r in rows if r["group"] == g) for g in ("upcoming", "completed", "cancelled")}
    counts["all"] = len(rows)
    if group != "all":
        rows = [r for r in rows if r["group"] == group]
    far = "9999-12-31T00:00:00+00:00"
    rows.sort(key=lambda r: r["when"] or far, reverse=group != "upcoming")
    return {"results": rows[:100], "counts": counts, "unavailable": failed}
