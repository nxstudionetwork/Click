"""
Buddy's Bookings help: temples, tourist spots, parks and experiences ("find temples I can visit this weekend",
"tourist places near Hyderabad", "a water park for 4 people", "what can I book in Vijayawada tomorrow?", "family
activities"), and the customer's own bookings across Click. ("show my upcoming bookings", "what is my booking
tomorrow?"). Answers come only from Click. Bookings data and each domain's own records; availability is checked for
the date asked; information-only places are said to be so. Buddy never books or pays.
"""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import urlencode

from .providers import BuddyReply

KINDS = [("temple", r"\b(temples?|darshan|seva|pooja|puja|mandir|devasthanam|spiritual|pilgrimage)\b"),
         ("water_park", r"\bwater ?parks?\b"), ("theme_park", r"\b(theme|amusement) parks?\b"), ("zoo", r"\bzoos?\b"), ("aquarium", r"\baquariums?\b"),
         ("museum", r"\bmuseums?\b"), ("adventure_park", r"\badventure parks?\b"), ("boat_ride", r"\bboat (rides?|trips?)\b"), ("cruise", r"\bcruises?\b"),
         ("workshop", r"\bworkshops?\b"), ("tour", r"\b(city tours?|walking tours?|tours?|heritage walks?)\b")]
GROUPS = [("tourist", r"\b(tourist (places?|spots?|attractions?)|sightseeing|monuments?|places to (visit|see)|attractions?)\b"),
          ("experiences", r"\b(experiences?|activities|things to do)\b")]
WANTS = re.compile(r"\b(what can i book|things to do|places to visit|family (fun|activities)|kids activities)\b")
MINE = re.compile(r"\b(my|our)\b.{0,20}\b(bookings?|reservations?|tickets?)\b|\bbooking (tomorrow|today)\b")


def wants_bookings(text: str) -> bool:
    return bool(MINE.search(text) or WANTS.search(text) or any(re.search(rx, text) for _, rx in KINDS + GROUPS))


def my_bookings(customer, text: str) -> BuddyReply:
    from datetime import datetime

    from apps.experiences import hub
    from apps.experiences.booking import today, tz

    if customer is None:
        return BuddyReply("Sign in to see your bookings.", actions=[{"label": "Sign in", "path": "/login"}])
    rows = hub.my_bookings(customer, "upcoming")["results"]
    day = today() + timedelta(days=1) if "tomorrow" in text else today() if re.search(r"\btoday\b", text) else None
    if day:
        rows = [r for r in rows if r["when"] and datetime.fromisoformat(r["when"]).astimezone(tz()).date() == day]
    cards = [{"type": "reservation", "reservation": r} for r in rows[:5]]
    if not rows:
        what = "tomorrow" if day and "tomorrow" in text else "today" if day else "coming up"
        return BuddyReply(f"You have no bookings {what}.", actions=[{"label": "My bookings", "path": "/bookings/mine"}, {"label": "Find something to book", "path": "/bookings"}])
    first = rows[0]
    when = datetime.fromisoformat(first["when"]).astimezone(tz())
    lead = (f"You have {len(rows)} upcoming booking{'s' if len(rows) != 1 else ''}. " if not day else "") + \
        f"{'Next' if not day else 'It’s'}: {first['title']} ({first['kind_label']}), {when:%a %d %b}" + (f" at {when:%I:%M %p}" if when.hour or when.minute else "") + \
        f" · {first['status_label']}."
    return BuddyReply(lead, cards=cards, actions=[{"label": "Open booking", "path": first["link"]}, {"label": "All bookings", "path": "/bookings/mine"}])


def reply(text: str, customer) -> BuddyReply | None:
    from apps.experiences import booking
    from apps.experiences.models import Attraction
    from apps.experiences.views import card, listed

    from .event_buddy import parse_date

    if MINE.search(text):
        return my_bookings(customer, text)
    qs = listed()
    kinds = [k for k, rx in KINDS if re.search(rx, text)]
    groups = [g for g, rx in GROUPS if re.search(rx, text)]
    if kinds:
        qs = qs.filter(group="spiritual") if kinds == ["temple"] else qs.filter(kind__in=kinds if "tour" not in kinds else [*kinds, "city_tour", "walking_tour"])
    elif groups:
        qs = qs.filter(group__in=groups)
    cities = sorted(set(Attraction.objects.values_list("city", flat=True)), key=len, reverse=True)
    city = next((c for c in cities if re.search(rf"\b{re.escape(c.lower())}\b", text)), None)
    if city:
        qs = qs.filter(city=city)
    if re.search(r"\b(family|kids?|children)\b", text):
        qs = qs.filter(kids_friendly=True) if re.search(r"\bkids?|children\b", text) else qs.filter(family_friendly=True)
    m = re.search(r"\bfor (\d{1,2}) (people|persons|of us|adults|visitors)\b", text)
    people = int(m.group(1)) if m else None
    today = booking.today()
    dates = []
    if re.search(r"\b(this|next) weekend\b", text):
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        dates = [sat, sat + timedelta(days=1)]
    elif (d := parse_date(text, today)) or re.search(r"\btoday\b", text):
        dates = [d or today]
    rows = list(qs)
    if dates or people:  # only places Click. can book with places left on those days
        def open_for(a):
            for d in dates or [today + timedelta(days=i) for i in range(7)]:
                for o in a.offerings.all():
                    if o.is_active and any(s["status"] == "available" and s["left"] >= (people or 1) for s in booking.slots(o, d)):
                        return True
            return False
        rows = [a for a in rows if a.bookable and open_for(a)]
    rows.sort(key=lambda a: (not a.bookable, -(float(a.rating_average) if a.rating_count >= 3 else 3.5), a.name))
    q = {k: v for k, v in {"group": groups[0] if groups and not kinds else ("spiritual" if kinds == ["temple"] else ""), "city": city or "",
                            "date": dates[0].isoformat() if dates else "", "kind": ",".join(kinds) if kinds and kinds != ["temple"] else ""}.items() if v}
    path = f"/bookings/search?{urlencode(q)}"
    where = f" in {city}" if city else ""
    when = (" this weekend" if len(dates) == 2 else f" on {dates[0]:%a %d %b}" if dates else "")
    if not rows:
        return BuddyReply(f"I couldn’t find anything{where} you can book{when}" + (f" for {people}" if people else "") + ".",
                          actions=[{"label": "Browse Bookings", "path": "/bookings"}])
    bookable = [a for a in rows if a.bookable]
    lead = f"I found {len(rows)} place{'s' if len(rows) != 1 else ''}{where}{when}"
    lead += f" — {len(bookable)} bookable on Click." if bookable and len(bookable) != len(rows) else (" you can book on Click." if bookable else
                                                                                                   ", information only (booked through their official channels).")
    if people and bookable:
        lead += f" Each has room for {people}."
    return BuddyReply(lead, cards=[{"type": "attraction", "attraction": card(a, saved={}, with_next=False)} for a in rows[:4]],
                      actions=[{"label": "See all", "path": path}] + ([{"label": f"Open {bookable[0].name}", "path": f"/bookings/places/{bookable[0].slug}"}] if bookable else []))
