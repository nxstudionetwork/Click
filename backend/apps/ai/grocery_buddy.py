"""
Buddy's grocery help, answered only from Click. Groceries data for the customer's own default address: real listings,
real stores and their real status. Buddy finds, compares and prepares (a shopping list, a search link); it never adds
to the basket, picks substitutions, chooses an address or places an order.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from apps.groceries import catalog as cat
from apps.groceries import discovery, search
from apps.groceries.delivery import address_point

from .providers import BuddyReply

GROCERY_WORDS = (
    "grocery", "groceries", "kirana", "provision", "provisions", "supermarket", "vegetables", "veggies", "vegetable", "fruits", "fruit",
    "milk", "bread", "eggs", "egg", "curd", "paneer", "butter", "rice", "atta", "dal", "toor", "oil", "ghee", "sugar", "salt", "tomatoes",
    "tomato", "onions", "onion", "potatoes", "potato", "spinach", "bananas", "banana", "apples", "detergent", "shampoo", "soap",
    "toothpaste", "diapers", "biscuits", "dishwash",
)
REORDER = re.compile(r"\b(reorder|buy again|bought (last|this) week|usual groceries|usual order)\b")


def wants_groceries(text: str) -> bool:
    return bool(REORDER.search(text)) or any(re.search(rf"\b{re.escape(w)}\b", text) for w in GROCERY_WORDS)


def _point(customer):
    if customer is None:
        return None
    a = customer.addresses.filter(is_default=True).first() or customer.addresses.first()
    return address_point(a)


def _cards(listings) -> list[dict]:
    return [{"type": "grocery", "listing": c} for c in listings]


def _name(c) -> str:
    return f"{c['brand'] + ' ' if c['brand'] else ''}{c['name']} {c['size']}"


def reply(text: str, customer) -> BuddyReply | None:
    point = _point(customer)
    loc_note = " Add a map pin to your default address so I can check which stores deliver to you." if point is None else ""

    if REORDER.search(text):
        if customer is None:
            return BuddyReply("Sign in and I'll show what you usually buy.", actions=[{"label": "Groceries", "path": "/groceries"}])
        rows = discovery.buy_again(customer, point, limit=6)
        if not rows:
            return BuddyReply("You don't have delivered grocery orders yet, so there's nothing to reorder.",
                              actions=[{"label": "Shop groceries", "path": "/groceries"}])
        changed = sum(1 for r in rows if r["listing"]["price"] != r["last_price"])
        lead = ("Here's what you usually buy, at today's prices and stock. Add what you need yourself; I don't add to your basket."
                + (f" {changed} price{'s' if changed > 1 else ''} changed since you last bought." if changed else ""))
        return BuddyReply(lead, cards=_cards([r["listing"] for r in rows]), actions=[{"label": "Buy again", "path": "/groceries/buy-again"}])

    if re.search(r"\bopen\b", text) and re.search(r"\b(stores?|shops?|kirana|grocery|groceries|supermarket)\b", text):
        stores = cat.deliverable_stores(point)
        open_now = [h for h in stores.values() if h["status"]["state"] in ("open", "closing_soon") and (point is None or h["deliverable"])]
        if not open_now:
            return BuddyReply("No grocery stores that deliver to you are open right now. You can schedule a delivery for later." + loc_note,
                              actions=[{"label": "Groceries", "path": "/groceries"}])
        names = ", ".join(f"{h['store'].name} ({h['status']['label'].lower()}{', ' + h['eta_label'] if h['eta_label'] else ''})" for h in open_now[:5])
        return BuddyReply(f"Open now and delivering to you: {names}." + loc_note,
                          cards=[{"type": "grocery_store", "store": discovery.store_card(h, set(), set(), {})} for h in open_now[:4]],
                          actions=[{"label": "All grocery stores", "path": "/groceries"}])

    # "I need milk and bread": several items become a shopping list the customer confirms and matches to a store.
    body = re.sub(r"^.*?\b(need|get|buy|want)\b", "", text)
    items = [" ".join(search.tokens(p)) for p in re.split(r",|\band\b|\+|&", body)]
    items = [i for i in items if i]
    if len(items) >= 2:
        found, missing = [], []
        for i in items[:6]:
            res = search.search({"q": i, "in_stock": "true"}, point)
            (found.append(res["results"][0]) if res["results"] else missing.append(i))
        lead = (f"I found {len(found)} of {len(items)} near you. To see which single store has everything, open your shopping list "
                "and tap Find everything. You choose the store and add items yourself.")
        if missing:
            lead += f" Not found nearby: {', '.join(missing)}."
        return BuddyReply(lead + loc_note, cards=_cards(found),
                          actions=[{"label": "Find everything", "path": f"/groceries/lists?items={quote(','.join(items))}"}])

    cheapest = bool(re.search(r"\b(cheap|cheapest|lowest|best price)\b", text))
    q = " ".join(search.tokens(text))
    if not q:
        return None
    res = search.search({"q": q, "sort": "price_low" if cheapest else "relevance", "in_stock": "true"}, point)
    path = f"/groceries/search?q={quote(q)}" + ("&sort=price_low" if cheapest else "")
    if not res["results"]:
        if not re.search(r"\b(grocery|groceries|kirana|supermarket|provisions?)\b", text):
            return None  # e.g. "dal" may be a dish: let Buddy's general search look across Click.
        return BuddyReply(f"No store near you has “{q}” in stock right now." + loc_note,
                          actions=[{"label": "Search Groceries", "path": path}])
    top = res["results"][:4]
    if cheapest:
        t = top[0]
        lead = (f"Cheapest in stock near you: {_name(t)} at ₹{float(t['price']):.0f} from {t['store']['name']}"
                + (f" ({t['per_unit']})" if t["per_unit"] else "") + ". Each card compares the same pack size only.")
    else:
        lead = f"Here's {q} from stores near you. Open one to see the store, delivery time and other stores' prices."
    if re.search(r"\blocal\b", text):
        lead += " Independent shops carry the Local Store badge."
    return BuddyReply(lead + loc_note, cards=_cards(top), actions=[{"label": "See all results", "path": path}])
