"""
Buddy basic mode: a built-in, deterministic assistant that understands common
Click intents and answers ONLY from real Click data via `tools`. It is the
default provider until a conversational AI provider is configured; it never
invents inventory, prices, availability or order states.
"""

import re

from django.utils import timezone

from . import tools
from .providers import AIContext, AIMessage, BuddyReply

STOPWORDS = set("""
a an the me my i we us please find show get give want need order buy book some good best great nice nearby near around
here today tonight for to of in on at with and or is are can you could would like something any cheap cheapest
looking look search me? options option place places restaurant restaurants store stores shop shops food dish dishes
""".split())

STATUS_TEXT = {
    "placed": "placed and waiting for the store to confirm",
    "confirmed": "confirmed by the store",
    "preparing": "being prepared",
    "ready": "ready and waiting for pickup by the delivery partner",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "cancelled": "cancelled",
}


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{w}\b", text) for w in words)


def _keywords(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9&']+", text) if w not in STOPWORDS and len(w) > 1]
    return " ".join(words[:3])


class ClickBasicBuddy:
    mode = "basic"

    def reply(self, messages: list[AIMessage], context: AIContext) -> BuddyReply:
        text = messages[-1].content.lower().strip()
        customer = context.customer

        if _has(text, "hi", "hello", "hey", "help") and len(text.split()) <= 4:
            return self._help()

        from . import grocery_buddy, parcel_buddy

        if parcel_buddy.wants_parcel(text):
            return parcel_buddy.reply(text, customer)

        if grocery_buddy.wants_groceries(text) and not _has(text, "restaurant", "dinner", "lunch", "biryani", "pizza", "dish", "meal"):
            if (grocery := grocery_buddy.reply(text, customer)) is not None:
                return grocery
        wants_food = _has(text, "dinner", "lunch", "breakfast", "eat", "food", "hungry", "biryani", "pizza", "burger", "dosa", "restaurant")
        movie_text = re.sub(r"\bshow (me|us)\b", "", text)  # "show me smart watches" is not about shows
        wants_movie = _has(movie_text, "movie", "movies", "film", "films", "cinema", "show", "shows", "showtime", "playing", "imax", "4dx", "tickets?", "event", "events", "concert") or bool(re.search(
            r"\b(what|something)\b.{0,20}\bwatch\b|\bwatch\b.{0,12}\b(tonight|today|tomorrow|this weekend|movie|film|show)\b", text))

        if wants_food and wants_movie:
            return self._dinner_and_movie(text)
        if _has(text, "ride", "cab", "taxi", "auto", "bike taxi", "take me", "drop me", "get me to", "go to"):
            return self._ride(messages[-1].content)
        if _has(text, "order", "orders", "delivery", "track", "delayed", "late", "where") and not wants_movie and not _has(text, "pizza", "biryani"):
            return self._orders(customer, text)
        if _has(text, "booking", "bookings", "my tickets"):
            return self._bookings(customer)
        if _has(text, "wallet", "balance", "refund", "refunds"):
            return self._wallet(customer)
        if _has(text, "points", "rewards?"):
            return self._rewards(customer)
        if _has(text, "offers?", "deals?", "discounts?", "coupons?"):
            return BuddyReply("Here are the current offers on Click. Each store applies its own offer.",
                              cards=[{"type": "offer", "offer": o} for o in tools.offers()], actions=[{"label": "All offers", "path": "/offers"}])
        if wants_movie:
            return self._movies(text)
        if _has(text, "compare", "comparison", "difference between"):
            return BuddyReply("Open the products you're deciding between and tap Compare on each. I'll line up their real specs, "
                              "prices, ratings and return terms side by side.", actions=[{"label": "Open Shopping", "path": "/shopping"}])
        if _has(text, "add (this|it|that) to (my )?cart", "buy (this|it|that)"):
            return BuddyReply("Open the product, choose its size or colour if it has one, then tap Add to cart. "
                              "I never add to your cart or pay without you.", actions=[{"label": "Open Shopping", "path": "/shopping"}])
        if _has(text, "plumber", "electrician", "cleaning", "repair"):
            return BuddyReply("That service isn’t live on Click yet, so I can’t book it. Food, groceries, shopping, rides, parcels and Showtime tickets are available now.",
                              actions=[{"label": "Explore Click", "path": "/explore"}])
        if shopping := self._shopping(messages[-1].content):
            return shopping
        return self._search(text)

    # --- intents ---------------------------------------------------------
    def _ride(self, original: str):
        """Hand a ride request to Click. Ride with the destination pre-filled. Buddy never books or pays for a ride."""
        import re
        from urllib.parse import quote

        m = re.search(r"(?:to|towards|till)\s+(?:the\s+)?(.+?)[.?!]*$", original.strip(), flags=re.I)
        dest = m.group(1).strip()[:60] if m else ""
        lead = (f"Let's get you to {dest}. " if dest else "Let's plan your ride. ") + (
            "Confirm your pickup, pick the destination, then compare Bike, Auto and Cab fares before you confirm.")
        path = f"/rides?to={quote(dest)}" if dest else "/rides"
        return BuddyReply(lead, actions=[{"label": "Plan this ride", "path": path}])

    def _shopping(self, original: str):
        """Shopping requests ("wireless earbuds under 2000", "gift for a 10 year old") use Shopping search itself."""
        result = tools.shop_search(original)
        if result is None:
            return None
        understood = ", ".join(result["understood"])
        if not result["products"]:
            return BuddyReply(f"I looked in Click. Shopping for {understood.lower() or 'that'} but nothing matches right now. "
                              "Try a wider price or another category.", actions=[{"label": "Open Shopping", "path": "/shopping"}])
        lead = (f"Here’s what I found in Click. Shopping ({understood}). " if understood else "Here’s what I found in Click. Shopping. ") + (
            "Open one to see sizes, delivery and reviews, then add it to your cart yourself.")
        return BuddyReply(lead, cards=[{"type": "product", "product": p} for p in result["products"]],
                          actions=[{"label": f"See all {result['count']} in Shopping", "path": result["path"]}])

    def _help(self):
        return BuddyReply(
            "Hi, I’m Buddy. I can find restaurants, dishes, groceries and products, find what’s on in Showtime tonight, "
            "check your orders and bookings, and explain your wallet and rewards. I prepare things for you; you always review and pay yourself.",
            actions=[{"label": "Find biryani", "prompt": "Find me a good biryani"}, {"label": "Movies tonight", "prompt": "Movies tonight"},
                     {"label": "Where is my order?", "prompt": "Where is my order?"}, {"label": "Dinner and a movie", "prompt": "Plan dinner and a movie tonight"}],
        )

    def _search(self, text):
        q = _keywords(text)
        if not q:
            return self._help()
        cheapest = _has(text, "cheap", "cheapest", "budget", "affordable")
        products = tools.search_products(q, cheapest=cheapest)
        stores = tools.search_stores(q)
        if not products and not stores:
            return BuddyReply(f"I couldn’t find anything for “{q}” on Click right now.",
                              actions=[{"label": f"Search “{q}”", "path": f"/search?q={q}"}])
        lead = f"Here’s what I found for “{q}”" + (", cheapest first" if cheapest else "") + ". Tap one to see details, or add it to your cart."
        cards = [{"type": "product", "product": p} for p in products] + [{"type": "store", "store": s} for s in stores[:2]]
        return BuddyReply(lead, cards=cards, actions=[{"label": "See all results", "path": f"/search?q={q}"}])

    def _orders(self, customer, text):
        orders, data = tools.recent_orders(customer)
        if not orders:
            return BuddyReply("You don’t have any orders yet.", actions=[{"label": "Order food", "path": "/food"}])
        o = orders[0]
        msg = f"Your latest order {o.number} from {o.store.name} is {STATUS_TEXT.get(o.status, o.status)}."
        actions = [{"label": "Open order", "path": f"/orders/{o.id}"}]
        if o.status not in ("delivered", "cancelled") and o.estimated_delivery_at:
            eta = timezone.localtime(o.estimated_delivery_at)
            if eta < timezone.now():
                msg += f" It was expected by {eta.strftime('%I:%M %p').lstrip('0')}, so it’s running late. I can’t see the reason from here; support can check with the store."
                actions.append({"label": "Get help with this order", "path": f"/help/new?orderId={o.id}&category=order"})
            else:
                msg += f" Estimated arrival by {eta.strftime('%I:%M %p').lstrip('0')}."
        return BuddyReply(msg, cards=[{"type": "order", "order": d} for d in data], actions=actions)

    def _bookings(self, customer):
        data = tools.upcoming_bookings(customer)
        if not data:
            return BuddyReply("You have no upcoming tickets.", actions=[{"label": "Open Showtime", "path": "/showtime"}])
        return BuddyReply(f"You have {len(data)} upcoming booking{'s' if len(data) > 1 else ''}.",
                          cards=[{"type": "booking", "booking": b} for b in data], actions=[{"label": "All bookings", "path": "/bookings"}])

    def _wallet(self, customer):
        bal = tools.wallet(customer)
        return BuddyReply(f"Your Click Wallet balance is ₹{bal:.2f}. Refunds for wallet payments come back here automatically.",
                          actions=[{"label": "Open wallet", "path": "/wallet"}])

    def _rewards(self, customer):
        r = tools.rewards(customer)
        return BuddyReply(f"You have {r['balance']} Click points ({r['earned']} earned, {r['used']} used). You earn points on delivered orders.",
                          actions=[{"label": "Open rewards", "path": "/rewards"}])

    def _movies(self, text):
        """Showtime: search with the app's own interpretation. Buddy suggests; the customer picks the showtime,
        seats and payment themselves (Buddy never books)."""
        if _has(text, "book", "seats?", "tickets?") and re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", text):
            lead = "I can’t pick seats or pay for you. Open the show, choose the time and your seats, then confirm. "
        else:
            lead = ""
        tonight = _has(text, "tonight", "today")
        result = tools.showtime_search(text)
        if not result["events"]:
            result = tools.showtime_search("tonight" if tonight else "")
            if not result["events"]:
                return BuddyReply("I couldn’t find shows matching that" + (" tonight" if tonight else "") + ".",
                                  actions=[{"label": "Open Showtime", "path": "/showtime"}])
            lead += "Nothing matched exactly, so here’s what’s playing. "
        understood = ", ".join(result["understood"])
        lead += (f"Here’s what’s on ({understood})." if understood else "Here’s what’s on.") + " Pick one to see cinemas, times and seats."
        return BuddyReply(lead, cards=[{"type": "event", "event": e} for e in result["events"]],
                          actions=[{"label": f"See all {result['count']} in Showtime", "path": result["path"]}])

    def _dinner_and_movie(self, text):
        cuisine = _keywords(re.sub(r"\b(dinner|movie|movies|film|plan|tonight|and|then|after|before)\b", " ", text))
        stores = tools.search_stores(cuisine, store_type="restaurant", limit=3) or tools.search_stores("", store_type="restaurant", limit=3)
        events = tools.find_events(tonight=True, limit=3)
        if not events:
            return BuddyReply("I found restaurants, but there are no more shows tonight. Here are dinner options:",
                              cards=[{"type": "store", "store": s} for s in stores], actions=[{"label": "Open Showtime", "path": "/showtime"}])
        return BuddyReply(
            "Here’s a plan: order dinner from one of these open restaurants (delivery times shown), then pick a show tonight. "
            "Leave about an hour between delivery and showtime. I’ll take you to the restaurant and the show; you confirm and pay in each checkout.",
            cards=[{"type": "store", "store": s} for s in stores] + [{"type": "event", "event": e} for e in events],
            actions=[{"label": "Tonight in Showtime", "path": "/showtime/search?when=tonight"}],
        )
