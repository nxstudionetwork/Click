"""
Buddy's Hotels help. Turns "a hotel in Hyderabad for 2 adults under ₹5,000 with breakfast" into a structured Click.
Hotels search (destination, dates, party, budget, breakfast, free cancellation, stars, property type, near the airport /
station / centre) and answers only from that search — real properties, prices for the dates, policies. It also reads the
customer's own hotel bookings. It never books, pays or cancels: cancelling opens the booking, where the policy and the
refund are shown before the customer confirms.
"""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import urlencode

from .providers import BuddyReply

HOTEL = re.compile(r"\b(hotels?|resorts?|homestays?|hostels?|villas?|guest ?houses?|accommodation|place to stay|somewhere to stay|"
                   r"room for (the )?night|stay in|stays? (in|at|near))\b")
MINE = re.compile(r"\b(my|our)\b.{0,20}\b(hotel|stay|room|reservation)s?\b")


def wants_hotel(text: str) -> bool:
    return bool(HOTEL.search(text) or MINE.search(text))


def _dates(text: str, today):
    from .event_buddy import parse_date

    m = re.search(r"\bfor (\d{1,2}) nights?\b", text)
    nights = int(m.group(1)) if m else 1
    if re.search(r"\b(this|next) weekend\b", text):
        sat = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        if "next weekend" in text and (5 - today.weekday()) % 7 > 1:
            sat += timedelta(days=7)
        ci = sat - timedelta(days=1)
        return ci, ci + timedelta(days=max(nights, 2)), False
    d = parse_date(text, today)
    if d:
        return d, d + timedelta(days=nights), False
    return today + timedelta(days=1), today + timedelta(days=1 + nights), True


def _int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def reply(text: str, customer) -> BuddyReply | None:
    from apps.hotels import engine
    from apps.hotels.models import Destination, HotelBooking, Landmark
    from apps.hotels.search import inventory

    if MINE.search(text) or re.search(r"\b(cancel|how much did i pay)\b.{0,30}\bhotel", text):
        if customer is None:
            return BuddyReply("Sign in to see your hotel bookings.", actions=[{"label": "Sign in", "path": "/login"}])
        rows = list(HotelBooking.objects.filter(customer=customer).select_related("property__partner").order_by("-check_in")[:5])
        if not rows:
            return BuddyReply("You don’t have any hotel bookings yet.", actions=[{"label": "Find a hotel", "path": "/hotels"}])
        cards = [{"type": "hotel_booking", "booking": {"id": str(b.id), "number": b.number, "property": b.property.partner.business_name,
                                                        "check_in": b.check_in.isoformat(), "check_out": b.check_out.isoformat(), "status": b.get_status_display(),
                                                        "payment": b.get_payment_status_display(), "total": f"{b.total:.2f}"}} for b in rows]
        b = rows[0]
        if re.search(r"\bcancel", text):
            live = next((x for x in rows if x.status in ("confirmed", "pending_payment")), None)
            if live is None:
                return BuddyReply("You have no active hotel booking to cancel.", cards=cards)
            return BuddyReply(f"{live.property.partner.business_name} ({live.number}, {live.check_in:%d %b}). I’ll open it so you can see the cancellation "
                              "policy and the exact refund before you confirm. I don’t cancel for you.",
                              cards=cards[:1], actions=[{"label": "Review cancellation", "path": f"/hotels/bookings/{live.id}?cancel=1"}])
        lead = (f"Your latest hotel booking is {b.property.partner.business_name}, {b.check_in:%d %b} – {b.check_out:%d %b} ({b.get_status_display().lower()}). "
                f"Total ₹{b.total:,.2f} · {b.get_payment_status_display().lower()}.")
        return BuddyReply(lead, cards=cards, actions=[{"label": "Open booking", "path": f"/hotels/bookings/{b.id}"}, {"label": "All hotel bookings", "path": "/hotels/bookings"}])

    dest = None
    for d in Destination.objects.filter(is_active=True, parent__isnull=True):
        if any(re.search(rf"\b{re.escape(n.lower())}\b", text) for n in [d.name, d.slug, *d.synonyms]):
            dest = d
            break
    if dest is None:
        return BuddyReply("Where would you like to stay? Tell me a city, e.g. “a hotel in Hyderabad for two nights this weekend”.",
                          actions=[{"label": "Open Hotels", "path": "/hotels"}])
    ci, co, assumed = _dates(text, engine.today())
    adults = _int(r"\b(\d{1,2})\s*(?:adults?|people|persons|guests)\b", text) or (2 if re.search(r"\b(couple|family|two of us|2 of us)\b", text) else 2)
    children = _int(r"\b(\d)\s*(?:child|children|kids?)\b", text) or (1 if re.search(r"\b(a|one) (child|kid)\b", text) else 0)
    rooms = _int(r"\b(\d)\s*rooms?\b", text) or 1
    budget = re.search(r"\b(?:under|below|less than|upto|up to|max|within)\s*(?:rs\.?|₹|inr)?\s*([\d,]+)\s*(k)?\b", text)
    params = {"destination": dest.slug, "check_in": ci, "check_out": co, "adults": adults, "children": children, "rooms": rooms,
              "breakfast": bool(re.search(r"\bbreakfast\b", text)), "free_cancellation": bool(re.search(r"\b(free cancell?ation|refundable|flexible)\b", text)),
              "pay_at_property": bool(re.search(r"\bpay at (the )?(hotel|property)\b", text)), "sort": "recommended"}
    if budget:
        n = int(budget.group(1).replace(",", "")) * (1000 if budget.group(2) else 1)
        params["max_price"] = n
        params["sort"] = "value"
    stars = _int(r"\b([1-5])[- ]?star\b", text)
    if stars:
        params["stars"] = [s for s in range(stars, 6)]
    types = [t for t, w in [("resort", "resort"), ("villa", "villa"), ("hostel", "hostel"), ("homestay", "homestay"), ("apartment", "apartment"), ("guest_house", "guest house")]
             if re.search(rf"\b{w}s?\b", text)]
    if types:
        params["type"] = types
    if re.search(r"\bfamily\b", text):
        params["room_class"] = ["family"]
    for kind, words in (("airport", r"airport"), ("station", r"(railway |train )?station"), ("centre", r"(city )?cent(re|er)"), ("beach", r"beach")):
        if re.search(rf"\bnear (the )?{words}\b", text):
            lm = Landmark.objects.filter(destination=dest, kind=kind).first()
            if lm:
                params["near"] = lm.id
                params["sort"] = "distance"
    if engine.validate_stay(ci, co, rooms, adults, children):
        return BuddyReply(engine.validate_stay(ci, co, rooms, adults, children), actions=[{"label": "Open Hotels", "path": "/hotels"}])
    res = inventory().search({**params, "page": 1})
    q = {"destination": dest.name, "check_in": ci.isoformat(), "check_out": co.isoformat(), "adults": adults, "children": children, "rooms": rooms,
         **{k: "true" for k in ("breakfast", "free_cancellation", "pay_at_property") if params[k]}, "sort": params["sort"]}
    if "max_price" in params:
        q["max_price"] = params["max_price"]
    if "stars" in params:
        q["stars"] = ",".join(map(str, params["stars"]))
    if "type" in params:
        q["type"] = ",".join(params["type"])
    if "near" in params:
        q["near"] = str(params["near"])
    path = f"/hotels/search?{urlencode(q)}"
    when = f"{ci:%a %d %b} – {co:%a %d %b}".replace(" 0", " ")
    asked = ", ".join(x for x in [f"under ₹{params['max_price']:,}/night" if "max_price" in params else "", "breakfast" if params["breakfast"] else "",
                                  "free cancellation" if params["free_cancellation"] else "", f"{stars}+ stars" if stars else ""] if x)
    if not res["results"]:
        return BuddyReply(f"No stays in {dest.name} match {asked or 'that'} for {when}. Try other dates or loosen a filter.",
                          actions=[{"label": "Change the search", "path": path}])
    top = res["results"][:3]
    lines = "; ".join(f"{c['name']} ({c['type_label'].lower()}{f', {c['star_rating']}★' if c['star_rating'] else ''}"
                      f"{', ' + c['rating']['average'] + '/10' if c['rating'] else ', new'}, ₹{float(c['price']['per_night']):,.0f}/night, "
                      f"₹{float(c['price']['total']):,.0f} total incl. tax{', free cancellation' if c['free_cancellation'] else ''})" for c in top)
    lead = (f"{res['count']} stay{'s' if res['count'] != 1 else ''} in {dest.name} for {when}, {adults} adult{'s' if adults > 1 else ''}"
            f"{f', {children} child' + ('ren' if children > 1 else '') if children else ''}{f' ({asked})' if asked else ''}: {lines}."
            + (" I assumed tomorrow for one night — change the dates on the results page." if assumed else "")
            + " Pick a room and review the price and policy; I don’t book or pay for you.")
    return BuddyReply(lead, cards=[{"type": "hotel", "hotel": c} for c in top],
                      actions=[{"label": f"See all {res['count']}", "path": path}, *[{"label": f"Rooms at {c['name']}", "path": f"/hotels/{c['id']}?" + urlencode({k: q[k] for k in ('check_in', 'check_out', 'adults', 'children', 'rooms')})} for c in top[:2]]])
