"""
Buddy's Services help: works out the likely service from the customer's words ("my kitchen tap is leaking" -> Plumbing),
shows real professionals who serve the customer's default address with their real availability and pricing model, and
links to the booking with the job pre-selected. Buddy never invents professionals, prices or availability and never books.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from .providers import BuddyReply

PROBLEM_WORDS = re.compile(
    r"\b(leak|leaking|tap|pipe|drain|blocked|toilet|flush|electrician|plumber|carpenter|painter|cleaner|cleaning|clean my|"
    r"switch|socket|fan|wiring|power cut|no power|tripping|ac\b|air ?conditioner|not cooling|washing machine|fridge|refrigerator|"
    r"\bro\b|water purifier|pest|cockroach|termite|laundry|ironing|cook|chef|beautician|facial|waxing|movers|packers|shifting|"
    r"gardener|handyman|mount|laptop|phone screen|repair|fix my|broken)\b")


def wants_service(text: str) -> bool:
    return bool(PROBLEM_WORDS.search(text))


def reply(text: str, customer) -> BuddyReply | None:
    from apps.professionals import engine

    cats = engine.match_categories(text)
    if not cats:
        return None
    cat = cats[0][0]
    jobs = [j for j in engine.match_jobs(text, limit=3) if j.category_id == cat.id]
    job = jobs[0] if jobs else None
    point = None
    if customer is not None:
        a = customer.addresses.filter(is_default=True).first() or customer.addresses.first()
        if a is not None and a.latitude is not None:
            point = (float(a.latitude), float(a.longitude))
    pros = [engine.card(p, point, cat, job) for p in engine.providers_for(cat, point)]
    pros.sort(key=lambda c: (c["availability"] != "now", -(float(c["rating"]["average"]) if c["rating"] else 0)))
    path = f"/services/{cat.slug}" + (f"?job={job.id}" if job else "")
    if not pros:
        return BuddyReply(f"That sounds like {cat.name.lower()}, but no {cat.profession.lower()} on Click serves your address right now. "
                          "You can tell Click what you need and we'll look for someone.",
                          actions=[{"label": "Tell Click what you need", "path": f"/services/request?text={quote(text[:200])}"}])
    now = [p for p in pros if p["availability"] == "now"]
    pricing = ""
    if job is not None:
        pricing = {"fixed": f"{job.name} is a fixed price", "starting": f"{job.name} starts at a set price; any extra work needs your approval",
                   "hourly": f"{job.name} is charged by the hour, never more than the hours you book",
                   "quote": f"{job.name} is quoted after the professional sees it, and starts only when you approve"}[job.pricing]
        pricing = f" {pricing}."
    lead = (f"Sounds like {cat.name.lower()}. {len(now)} {cat.profession.lower()}{'s are' if len(now) != 1 else ' is'} available now near you"
            if now else f"Sounds like {cat.name.lower()}. No {cat.profession.lower()} is free right now, but you can schedule one") + \
        f".{pricing} I can send a request for you once you confirm; you pay only after the work, and I never pay for you." + \
        ("" if point else " Add a map pin to your address so I can check who serves it.")
    lines = "; ".join(f"{p['name']} ({p['availability_label'].lower()}, {p['price_label']}"
                      f"{', ' + p['rating']['average'] + '★' if p['rating'] else ''})" for p in pros[:3])
    book = []
    if job is not None and now and job.instant and customer is not None:
        first = now[0]
        book = [{"label": f"Request {first['name'].split()[0]} now", "action": "book_service", "args": {"provider_id": first["id"], "job_id": str(job.id)}}]
    return BuddyReply(f"{lead} Options: {lines}.", actions=[*book, {"label": f"See {cat.profession.lower()}s", "path": path},
                                                            *[{"label": f"Book {p['name'].split()[0]}", "path": f"/services/pro/{p['id']}" + (f"?job={job.id}" if job else "")}
                                                              for p in pros[:2]]])
