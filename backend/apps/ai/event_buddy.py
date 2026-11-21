"""
Buddy's Events help: understands "plan a birthday party for 30 people next Saturday", asks for what's missing, and
answers only from Click. Events records — event teams and venues that take that event type and guest count and are
free that day (blocked dates and bookings), their real packages and prices, and the event type's checklist. It opens the
planning flow pre-filled; it never sends requests, books or pays for the customer.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urlencode

from .providers import BuddyReply

PLAN = re.compile(
    r"\b(plan|planning|organi[sz]e|host|hosting|arrange|throw|celebrate)\b.{0,50}\b(party|birthday|wedding|engagement|anniversary|"
    r"shower|reception|function|celebration|event|ceremony|housewarming|farewell|reunion|conference|seminar|workshop|launch)\b")
VENDOR = re.compile(
    r"\b((birthday|party|wedding|event|engagement|anniversary|corporate) (planner|organi[sz]er|decorator|team)s?|planners?|event team|event management|decorator|decoration for|caterer|catering for|banquet|"
    r"party hall|wedding venue|event venue|venue for|dj for|photographer for|videographer|anchor for|emcee|mehendi|mehndi|"
    r"stage setup|tent house)\b")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def wants_event(text: str) -> bool:
    return bool(PLAN.search(text) or VENDOR.search(text))


def parse_guests(text: str) -> int | None:
    m = re.search(r"\b(\d{1,5})\s*(?:\+\s*)?(people|persons|guests|pax|members|adults|kids|children|attendees)\b", text)
    return int(m.group(1)) if m else None


def parse_date(text: str, today: date) -> date | None:
    if re.search(r"\btomorrow\b", text):
        return today + timedelta(days=1)
    m = re.search(r"\bin (\d{1,3}) (day|days|week|weeks)\b", text)
    if m:
        n = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
        return today + timedelta(days=n)
    m = re.search(r"\b(next|this|coming)?\s*(" + "|".join(DAYS) + r")\b", text)
    if m:
        target = DAYS.index(m.group(2))
        delta = (target - today.weekday()) % 7 or 7  # the coming one ("next Saturday" said midweek)
        if m.group(1) == "next" and delta <= 2:  # said on Thursday/Friday, "next Saturday" means the one after tomorrow's
            delta += 7
        return today + timedelta(days=delta)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")[a-z]*\b", text) or \
        re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", text)
    if m:
        a, b = m.group(1), m.group(2)
        day, mon = (int(a), b) if a.isdigit() else (int(b), a)
        month = MONTHS.index(mon[:3]) + 1
        try:
            d = date(today.year, month, day)
            return d if d >= today else date(today.year + 1, month, day)
        except ValueError:
            return None
    return None


def reply(text: str, customer) -> BuddyReply | None:
    from apps.eventhub import engine

    today = engine.today()
    types = engine.match_types(text)
    services = engine.match_services(text)
    etype = types[0] if types else None
    guests = parse_guests(text)
    day = parse_date(text, today)
    point = None
    if customer is not None:
        a = customer.addresses.filter(is_default=True).first() or customer.addresses.first()
        if a is not None and a.latitude is not None:
            point = (float(a.latitude), float(a.longitude))

    params = {"type": etype.slug if etype else "", "guests": str(guests or ""), "date": day.isoformat() if day else "",
              "available": "true" if day else "", "service": ",".join(s.slug for s in services if s.slug != "venue")}
    if any(s.slug == "venue" for s in services) and len(services) == 1:
        params["kind"] = "venue"
        params["service"] = ""
    cards = engine.search_providers({k: v for k, v in params.items() if v}, point)
    plan_q = urlencode({k: v for k, v in {"type": etype.slug if etype else "", "guests": guests or "", "date": day.isoformat() if day else "",
                                           "services": ",".join(s.slug for s in services)}.items() if v})
    actions = [{"label": "Start planning", "path": f"/events/plan{'?' + plan_q if plan_q else ''}"}]
    teams_q = urlencode({k: v for k, v in params.items() if v and k in ("type", "guests", "date", "service", "kind")})
    actions.append({"label": "See matching teams", "path": f"/events/teams{'?' + teams_q if teams_q else ''}"})

    asks = []
    if etype is None and not services:
        asks.append("what kind of event it is (birthday, wedding, corporate…)")
    if guests is None:
        asks.append("roughly how many guests")
    if day is None:
        asks.append("the date (or say it’s flexible)")
    what = f"a {etype.name.lower()}" if etype else ", ".join(s.name.lower() for s in services[:3]) or "your event"
    when = f" on {day.strftime('%a %d %b').replace(' 0', ' ')}" if day else ""
    who = f" for {guests} guests" if guests else ""
    lead = f"Planning {what}{who}{when}. "

    if not cards:
        lead += ("No event team on Click. matches that yet" + (" for that date" if day else "") +
                 ". Start a plan and we’ll show every team and venue that can take it as they become available.")
        return BuddyReply(lead + (f" Also tell me {', '.join(asks)}." if asks else ""), actions=actions)

    lines = []
    for c in cards[:3]:
        bits = [c["kind_label"].lower()]
        if c["rating"]:
            bits.append(f"{c['rating']['average']}★ ({c['rating']['count']})")
        if c["price_from"]:
            bits.append(c["price_from"]["label"].lower())
        else:
            bits.append("quote on request")
        if c["availability"]:
            bits.append(c["availability"]["label"][0].lower() + c["availability"]["label"][1:])
        lines.append(f"{c['name']} ({', '.join(bits)})")
    checklist = ""
    if etype and etype.checklist:
        checklist = " A checklist to start: " + "; ".join(i["label"] for i in etype.checklist[:5]) + "."
    lead += f"{len(cards)} team{'s' if len(cards) != 1 else ''} and venue{'s' if len(cards) != 1 else ''} fit: " + "; ".join(lines) + "." + checklist
    if asks:
        lead += f" To narrow it down, tell me {', '.join(asks)}."
    lead += " I don’t send requests, book or pay for you — you choose and confirm."
    actions += [{"label": f"View {c['name']}", "path": f"/events/providers/{c['id']}"} for c in cards[:2]]
    return BuddyReply(lead, actions=actions[:4])
