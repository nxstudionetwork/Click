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

        from . import bookings_buddy, event_buddy, grocery_buddy, hotel_buddy, parcel_buddy, service_buddy, travel_buddy

        if nav := self._navigate(text):
            return nav
        if cart := self._add_to_cart(customer, messages[-1].content):
            return cart
        note = ""
        if _has(text, "remind", "reminder", "reminders", "alarm"):
            note = "Reminders aren’t available in Click yet, so I can’t set one"

        if travel_buddy.wants_travel(text):
            if (tr := travel_buddy.reply(text, customer)) is not None:
                return tr
        if hotel_buddy.wants_hotel(text):
            if (h := hotel_buddy.reply(text, customer)) is not None:
                return h
        if bookings_buddy.wants_bookings(text) and not event_buddy.wants_event(text):
            if (bk := bookings_buddy.reply(text, customer)) is not None:
                return bk
        if event_buddy.wants_event(text):
            if (ev := event_buddy.reply(text, customer)) is not None:
                return ev
        if parcel_buddy.wants_parcel(text):
            return parcel_buddy.reply(text, customer)
        if service_buddy.wants_service(text) and not grocery_buddy.REORDER.search(text):
            if (svc := service_buddy.reply(text, customer)) is not None:
                return svc

        if grocery_buddy.wants_groceries(text) and not _has(text, "restaurant", "dinner", "lunch", "biryani", "pizza", "dish", "meal"):
            if (grocery := grocery_buddy.reply(text, customer)) is not None:
                return grocery
        wants_food = _has(text, "dinner", "lunch", "breakfast", "eat", "food", "hungry", "biryani", "pizza", "burger", "dosa", "restaurant")
        movie_text = re.sub(r"\bshow (me|us|my|our)\b", "", text)  # "show me smart watches" is not about shows
        wants_movie = _has(movie_text, "movie", "movies", "film", "films", "cinema", "show", "shows", "showtime", "playing", "imax", "4dx", "tickets?", "event", "events", "concert") or bool(re.search(
            r"\b(what|something)\b.{0,20}\bwatch\b|\bwatch\b.{0,12}\b(tonight|today|tomorrow|this weekend|movie|film|show)\b", text))

        if wants_food and wants_movie and not note:
            return self._dinner_and_movie(text)
        if (_has(text, "restaurants?", "places to eat", "somewhere to eat", "veg", "vegetarian", "pure veg") or re.search(r"\bfood (near|nearby|around)", text)) \
                and not _has(text, "groceries", "grocery"):
            return self._restaurants(text)
        if _has(text, "ride", "cab", "taxi", "auto", "bike taxi", "take me", "drop me", "get me to", "go to"):
            r = self._ride(messages[-1].content)
            if note:
                r.content = f"{note}, but here’s the ride. {r.content}"
            return r
        if note:
            return BuddyReply(f"{note}. Tell me what you’d like me to find or open instead.")
        if _has(text, "order", "orders", "delivery", "track", "delayed", "late", "where", "cancel") and not wants_movie and not _has(text, "pizza", "biryani"):
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
        if shopping := self._shopping(messages[-1].content):
            return shopping
        return self._search(text)

    # --- intents ---------------------------------------------------------
    NAV = [("wishlist", "/wishlist", "Wishlist"), ("payments?|payment methods?", "/account/payments", "Payments"), ("wallet", "/wallet", "Wallet"),
           ("rewards?|points", "/rewards", "Rewards"), ("(saved )?addresses", "/account/addresses", "Addresses"), ("profile|account", "/account", "Profile"),
           ("settings", "/settings", "Settings"), ("support|help", "/help", "Support"), ("buzz", "/buzz", "Buzz"), ("explore", "/explore", "Explore"),
           ("home", "/", "Home"), ("food", "/food", "Food"), ("rides?", "/rides", "Ride"), ("shop|shopping", "/shopping", "Shop"),
           ("groceries", "/groceries", "Groceries"), ("parcels?", "/parcels", "Parcel"), ("services", "/services", "Services"),
           ("events", "/events", "Events"), ("hotels", "/hotels", "Hotels"), ("shows|showtime|movies", "/showtime", "Shows"),
           ("travel|my journeys", "/travel", "Travel"), ("bookings|my bookings", "/bookings/mine", "Bookings"),
           ("orders", "/orders", "Orders"), ("cart|basket", "/cart", "Cart"), ("notifications", "/notifications", "Notifications"),
           ("activity|history", "/activity", "Activity"), ("offers", "/offers", "Offers"), ("click id|id card", "/account/card", "Click ID card")]

    def _navigate(self, text):
        """“Open my wishlist”, “take me to Payments”: a safe action the app performs straight away."""
        m = re.match(r"^(?:please\s+)?(?:open|go to|goto|take me to|show me|show|launch|navigate to)\s+(?:my\s+|the\s+)?(.+?)[.!?]*$", text)
        if not m:
            return None
        target = m.group(1).strip()
        for words, path, name in self.NAV:
            if re.fullmatch(rf"(?:{words})(?: page| screen| tab)?", target):
                return BuddyReply(f"Opening {name}.", actions=[{"label": f"Open {name}", "action": "open_page", "args": {"path": path}, "auto": True}])
        return None

    def _add_to_cart(self, customer, original):
        """“Add milk and bread to my cart”: preparing a cart is a safe action. Buddy picks the clear match (what you bought
        before, else the cheapest in-stock item), adds it through the cart service and says exactly what it added;
        nothing is ordered or paid."""
        m = re.search(r"\badd\s+(.+?)\s+(?:to|in|into)\s+(?:my\s+|the\s+)?(?:cart|basket)\b", original, flags=re.I)
        if not m:
            return None
        if customer is None:
            return BuddyReply("Sign in so I can add things to your cart.", actions=[{"label": "Sign in", "path": "/login"}])
        items, missing = [], []
        for it in re.split(r"\s*(?:,|\band\b|&)\s*", m.group(1).lower()):
            qty = 1
            mq = re.match(r"^(\d{1,2})\s+(.+)$", it.strip())
            if mq:
                qty, it = int(mq.group(1)), mq.group(2)
            it = re.sub(r"^(a|an|some|the)\s+", "", it.strip())
            if not it:
                continue
            p = tools.grocery_match(customer, it)
            if p is not None:
                items.append({"label": f"Add {p.name}", "action": "cart_add", "args": {"product_id": str(p.id), "quantity": qty}, "auto": True})
                continue
            found = tools.search_products(it, limit=1)
            if found:
                items.append({"label": f"Add {found[0]['name']}", "action": "cart_add", "args": {"product_id": str(found[0]["id"]), "quantity": qty}, "auto": True})
            else:
                missing.append(it)
        lead = "" if items else "I couldn’t find any of those on Click right now."
        if missing and items:
            lead = f"Nothing on Click matches {', '.join(missing)} right now."
        return BuddyReply(lead, actions=[*items, {"label": "View cart", "path": "/cart"}])

    def _restaurants(self, text):
        veg = _has(text, "veg", "vegetarian", "pure veg") and not re.search(r"\bnon[- ]?veg", text)
        cheapest = _has(text, "cheap", "cheapest", "budget", "affordable", "cheaper")
        q = _keywords(re.sub(r"\b(veg|vegetarian|pure|only|just|one|ones|the|first|cheaper|nearest|closest|best|top|nearby|near|me)\b", " ", text))
        stores = tools.search_restaurants(q, veg=veg, cheapest=cheapest) or (tools.search_restaurants("", veg=veg, cheapest=cheapest) if q else [])
        if not stores:
            return BuddyReply("No restaurant on Click matches that right now" + (" among pure-veg kitchens" if veg else "") + ".",
                              actions=[{"label": "Open Food", "path": "/food"}])
        bits = [x for x in [f"“{q}”" if q else "", "pure-veg kitchens" if veg else "", "lowest prices first" if cheapest else ""] if x]
        lead = ("Here are restaurants taking orders now" + (f" ({', '.join(bits)})" if bits else "") + ". "
                + ("Pure veg means no non-veg dish on their menu. " if veg else "") + "Ratings and delivery times come from each restaurant.")
        if cheapest:
            lead += f" The most affordable is {stores[0]['name']}."
        return BuddyReply(lead, cards=[{"type": "store", "store": st} for st in stores], actions=[{"label": "Open Food", "path": "/food"}])

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
            "Hi, I’m Buddy. I can find restaurants, dishes, groceries and products, buses, trains and flights, temples and things to do, "
            "what’s on in Showtime tonight, check your orders and bookings, and explain your wallet and rewards. I prepare things for you; you always review and pay yourself.",
            actions=[{"label": "Find biryani", "prompt": "Find me a good biryani"}, {"label": "Movies tonight", "prompt": "Movies tonight"},
                     {"label": "Where is my order?", "prompt": "Where is my order?"}, {"label": "Dinner and a movie", "prompt": "Plan dinner and a movie tonight"}],
        )

    def _search(self, text):
        q = _keywords(text)
        if not q:
            return BuddyReply("I’m not sure what you mean. Do you want me to search Click, open a feature, or help you complete something?",
                              actions=[{"label": "Search Click", "path": "/search"}, {"label": "Open Explore", "path": "/explore"},
                                       {"label": "What can you do?", "prompt": "What can you do?"}])
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
        if _has(text, "cancel"):
            from apps.orders.models import CUSTOMER_CANCELLABLE

            if o.status in CUSTOMER_CANCELLABLE:
                actions.insert(0, {"label": f"Cancel {o.number}", "action": "cancel_order", "args": {"order_id": str(o.id)}})
                msg += " I can cancel it — you’ll confirm first."
            else:
                msg += " It can’t be cancelled at this stage."
        if o.status not in ("delivered", "cancelled") and o.estimated_delivery_at:
            eta = timezone.localtime(o.estimated_delivery_at)
            if eta < timezone.now():
                msg += f" It was expected by {eta.strftime('%I:%M %p').lstrip('0')}, so it’s running late. I can’t see the reason from here; support can check with the store."
                actions.append({"label": "Get help with this order", "path": f"/help/new?orderId={o.id}&category=order"})
            else:
                msg += f" Estimated arrival by {eta.strftime('%I:%M %p').lstrip('0')}."
        return BuddyReply(msg, cards=[{"type": "order", "order": d} for d in data], actions=actions)

    def _bookings(self, customer):
        from . import bookings_buddy

        return bookings_buddy.my_bookings(customer, "")

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
