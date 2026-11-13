"""
Buddy's Travel help. "Find me a bus from Hyderabad to Delhi tomorrow", "the cheapest train from Chennai to Odisha",
"which is faster, the bus or the flight?" run the same Click. Travel search the app uses (apps.travel.search) and
answer only from its results — counts, fares, times and availability are never invented. "Book this train" opens the
journey so the customer chooses seats / passengers and reviews the total; Buddy never buys a ticket.
"""

from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlencode

from .providers import BuddyReply

MODES = {"bus": r"\b(bus|buses|coach|sleeper bus|volvo)\b", "train": r"\b(trains?|rail|railway)\b", "flight": r"\b(flights?|fly|flying|plane|airline)\b"}
ROUTE = re.compile(r"\bfrom\s+[a-z].{1,40}?\bto\s+[a-z]|\bto\s+[a-z]+.{0,20}\bfrom\s+[a-z]")
MINE = re.compile(r"\b(my|our)\b.{0,20}\b(journey|trip|ticket|pnr|bus|train|flight)s?\b|\bpnr\b")
COMPARE = re.compile(r"\b(which is|what'?s) (faster|quicker|cheaper)\b|\bfaster\b.{0,30}\bor\b|\bcompare\b")


def mode_of(text: str) -> list[str]:
    return [m for m, rx in MODES.items() if re.search(rx, text)]


def wants_travel(text: str) -> bool:
    modes = mode_of(text)
    if MINE.search(text) and (modes or "journey" in text or "pnr" in text):
        return True
    return bool(modes) and (bool(ROUTE.search(text)) or bool(COMPARE.search(text)) or bool(re.search(r"\b(book|find|search|cheapest|fastest)\b", text)))


def _cities():
    from apps.travel.models import Place

    out = []
    for p in Place.objects.filter(kind="city", is_active=True):
        for n in [p.name, *[a.strip() for a in p.aliases.split(",") if a.strip()]]:
            out.append((n.lower(), p))
    return sorted(out, key=lambda x: -len(x[0]))


def _endpoints(text: str):
    names = _cities()

    def find(after: str):
        m = re.search(rf"\b{after}\s+([a-z .]+?)(?=\s+(?:to|from|on|for|tomorrow|today|this|next|by|in|under|\d)|[?.!,]|$)", text)
        if not m:
            return None
        chunk = m.group(1).strip()
        return next((p for n, p in names if re.search(rf"\b{re.escape(n)}\b", chunk)), None)

    return find("from"), find("to")


def _option_line(o: dict) -> str:
    from apps.travel import engine
    from datetime import datetime

    dep = datetime.fromisoformat(o["departs_at"]).astimezone(engine.tz())
    h, m = divmod(o["duration_minutes"], 60)
    return f"{o['operator']['name']} {o['service']['number']} at {dep:%I:%M %p}, {h}h {m:02d}m, from ₹{Decimal(o['lowest']):,.0f}"


def _card(o: dict) -> dict:
    return {"type": "journey", "journey": {k: o[k] for k in ("id", "mode", "journey_id", "from_stop_id", "to_stop_id", "departs_at", "arrives_at",
                                                              "duration_minutes", "lowest", "available", "stops")}
            | {"operator": o["operator"]["name"], "number": o["service"]["number"], "name": o["service"]["name"], "from": o["from"]["name"],
               "to": o["to"]["name"], "class": next((c["name"] for c in o["classes"] if c["bookable"]), o["classes"][0]["name"] if o["classes"] else "")}}


def _mine(customer) -> BuddyReply:
    from django.utils import timezone

    from apps.travel import engine
    from apps.travel.models import ACTIVE

    if customer is None:
        return BuddyReply("Sign in to see your journeys.", actions=[{"label": "Sign in", "path": "/login"}])
    b = customer.travel_bookings.filter(status__in=ACTIVE, departs_at__gt=timezone.now()).order_by("departs_at").first()
    if b is None:
        return BuddyReply("You don’t have an upcoming journey booked on Click.", actions=[{"label": "Plan a journey", "path": "/travel"}])
    dep = b.departs_at.astimezone(engine.tz())
    pax = ", ".join(f"{p.name} {p.seat or p.get_seat_status_display()}" for p in b.passengers.all())
    return BuddyReply(f"Your next journey: {b.from_label.split(' — ')[0]} → {b.to_label.split(' — ')[0]}, {b.get_mode_display().lower()} "
                      f"{b.service_label}, {dep:%a %d %b at %I:%M %p}. {b.get_status_display()}" + (f", PNR {b.pnr}" if b.pnr else "")
                      + (f". Seats: {pax}." if pax else "."), actions=[{"label": "View journey", "path": f"/travel/bookings/{b.id}"}])


def reply(text: str, customer) -> BuddyReply | None:
    from apps.travel import engine, search
    from apps.travel.models import Mode

    from .event_buddy import parse_date

    if MINE.search(text) and not ROUTE.search(text):
        return _mine(customer)
    origin, dest = _endpoints(text)
    modes = mode_of(text) or ["bus", "train", "flight"]
    if origin is None or dest is None:
        missing = "where you’re starting from" if origin is None else "where you’re going"
        return BuddyReply(f"Tell me {missing} — e.g. “a {modes[0]} from Hyderabad to Delhi tomorrow”. I only search cities Click. Travel serves.",
                          actions=[{"label": "Open Travel", "path": "/travel"}])
    if origin.id == dest.id:
        return BuddyReply("From and To are the same city. Where are you going?", actions=[{"label": "Open Travel", "path": "/travel"}])
    today = engine.today()
    d = parse_date(text, today) or today
    if re.search(r"\btoday\b|\btonight\b", text):
        d = today
    m = re.search(r"\bfor (\d) (people|persons|passengers|adults|of us)\b", text)
    seats = int(m.group(1)) if m else 1
    cheapest, fastest = bool(re.search(r"\b(cheap|cheapest|lowest|budget)\b", text)), bool(re.search(r"\b(fast|fastest|quickest|quick)\b", text))
    found = {}
    for mode in modes:
        try:
            opts = search.gather(mode, origin, dest, d, seats)
        except search.TravelUnavailable:
            return BuddyReply("Travel options are temporarily unavailable. Try again in a moment.", actions=[{"label": "Open Travel", "path": "/travel"}])
        f = {"available_only": True}
        if mode == Mode.BUS:
            f["bus_type"] = [t for t, w in (("sleeper", "sleeper"), ("seater", "seater"), ("ac", r"\bac\b"), ("non_ac", "non[- ]ac")) if re.search(w, text)]
        found[mode] = search.sort(search.apply_filters(opts, f), "price" if cheapest else "duration" if fastest else "recommended")
    q = {"origin": origin.slug, "destination": dest.slug, "date": d.isoformat(), "adults": seats}
    when = "today" if d == today else "tomorrow" if (d - today).days == 1 else f"{d:%a %d %b}"
    if len(modes) > 1 and COMPARE.search(text):
        lines, best = [], None
        for mode, rows in found.items():
            if rows:
                fast = min(rows, key=lambda o: o["duration_minutes"])
                low = min(rows, key=lambda o: Decimal(o["lowest"]))
                lines.append(f"{mode.title()}: fastest {fast['duration_minutes'] // 60}h {fast['duration_minutes'] % 60:02d}m, cheapest ₹{Decimal(low['lowest']):,.0f}")
                if best is None or fast["duration_minutes"] < best[1]["duration_minutes"]:
                    best = (mode, fast)
        if not lines:
            return BuddyReply(f"I couldn’t find any journeys from {origin.name} to {dest.name} {when}.", actions=[{"label": "Open Travel", "path": "/travel"}])
        missing = [m for m in modes if not found.get(m)]
        verdict = (f"The {best[0]} is faster." if len(lines) > 1 else
                   f"There’s no {' or '.join(missing)} with seats on this route {when}, so I can’t compare — only {best[0]} options exist.")
        return BuddyReply(f"{origin.name} → {dest.name}, {when}. " + "; ".join(lines) + f". {verdict}",
                          cards=[_card(rows[0]) for rows in found.values() if rows][:3],
                          actions=[{"label": f"See {m} options", "path": f"/travel/search?{urlencode({**q, 'mode': m})}"} for m, rows in found.items() if rows][:3])
    mode = max(found, key=lambda k: len(found[k])) if len(modes) > 1 else modes[0]
    rows = found[mode]
    path = f"/travel/search?{urlencode({**q, 'mode': mode, 'sort': 'price' if cheapest else 'duration' if fastest else 'recommended'})}"
    word = {"bus": "bus", "train": "train", "flight": "flight"}[mode]
    if not rows:
        alts = [m for m in ("bus", "train", "flight") if m != mode and m in found and found[m]]
        return BuddyReply(f"There are no {word}s with seats from {origin.name} to {dest.name} {when}." + (f" There are {alts[0]} options." if alts else ""),
                          actions=[{"label": "Try other dates", "path": path}])
    top = rows[0]
    lead = (f"There {'is' if len(rows) == 1 else 'are'} {len(rows)} {word}{'' if len(rows) == 1 else 'es' if word == 'bus' else 's'} with seats from "
            f"{origin.name} to {dest.name} {when}. {'Cheapest' if cheapest else 'Fastest' if fastest else 'Top pick'}: {_option_line(top)}. "
            "Fares are per person including GST; the final fare is checked again before you pay.")
    actions = [{"label": "See all options", "path": path}]
    if re.search(r"\bbook\b", text):
        actions.insert(0, {"label": f"Choose {'seats' if mode == 'bus' else 'class'} & passengers",
                           "path": f"/travel/journey/{top['journey_id']}/{top['from_stop_id']}/{top['to_stop_id']}?adults={seats}"})
        lead += " I’ll open it so you choose seats and passengers and review the total — I don’t buy tickets for you."
    return BuddyReply(lead, cards=[_card(o) for o in rows[:3]], actions=actions)
