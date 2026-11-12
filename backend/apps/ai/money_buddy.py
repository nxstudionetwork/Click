"""
Buddy for Wallet, Payments, Rewards, Offers, Notifications, Activity and Support: "what's my wallet balance?",
"when does my credit expire?", "where is my refund?", "did my payment fail?", "how many points do I have?", "how far
to Gold?", "any offers on hotels?", "unread notifications", "what did I do this week?", "status of my support
request". Answers are read from the same ledgers and records the pages use. Buddy never adds money, pays, redeems
points or raises a request by itself: it opens the screen where the customer does that.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .providers import BuddyReply

ADD = re.compile(r"\b(add|load|top ?up|recharge)\b.{0,20}\b(money|wallet|balance|funds?)\b|\btop ?up\b")
WITHDRAW = re.compile(r"\b(withdraw|cash ?out|transfer|send money|move money)\b")
REFUND = re.compile(r"\brefunds?\b")
EXPIRY = re.compile(r"\b(expir\w*|valid till|validity)\b")
CASHBACK = re.compile(r"\bcash ?back\b")
WALLET = re.compile(r"\b(wallet|balance|promo credit|click credit)\b")
PAYMENT = re.compile(r"\b(payments?|paid|charged|debited|transactions?)\b")
FAILED = re.compile(r"\b(fail\w*|declined|stuck|pending|deducted)\b")
POINTS = re.compile(r"\b(points?|rewards?|tiers?|missions?|redeem)\b|\b(gold|silver|platinum|bronze) (tier|member|status)\b|\bhow far (to|from) (gold|silver|platinum)\b")
OFFERS = re.compile(r"\b(offers?|deals?|discounts?|coupons?|promo ?codes?)\b")
NOTIF = re.compile(r"\b(notifications?|alerts?|unread)\b")
ACTIVITY = re.compile(r"\b(my activity|activity timeline|what did i (do|order|book)|my history)\b")
SUPPORT = re.compile(r"\b(support (request|ticket)s?|my (requests?|tickets?|complaints?)|complaint|contact support|talk to (support|someone))\b")
SERVICES = {"food": "food", "restaurant": "food", "grocer": "groceries", "shop": "shop", "ride": "ride", "cab": "ride", "parcel": "parcel",
            "hotel": "hotels", "stay": "hotels", "travel": "travel", "flight": "travel", "train": "travel", "bus": "travel", "movie": "shows",
            "shows": "shows", "showtime": "shows", "event": "events", "temple": "bookings", "booking": "bookings", "service": "services"}


def _r(v) -> str:
    return f"₹{Decimal(v):,.2f}".replace(".00", "")


def wants_money(text: str) -> bool:
    return any(rx.search(text) for rx in (ADD, WITHDRAW, REFUND, EXPIRY, CASHBACK, WALLET, POINTS, OFFERS, NOTIF, SUPPORT)) or \
        bool(PAYMENT.search(text) and FAILED.search(text)) or bool(re.search(r"\bmy payments?\b", text)) or bool(ACTIVITY.search(text))


def _signin(what: str) -> BuddyReply:
    return BuddyReply(f"Sign in to see your {what}.", actions=[{"label": "Sign in", "path": "/login"}])


def reply(text: str, customer) -> BuddyReply | None:
    if WITHDRAW.search(text) and WALLET.search(text):
        return BuddyReply("Click. Wallet money can be spent on Click. services, but it can’t be withdrawn to a bank or sent to someone else.",
                          actions=[{"label": "Open wallet", "path": "/wallet"}])
    if ADD.search(text):
        return _add_money(customer)
    if SUPPORT.search(text):
        return _support(customer)
    if REFUND.search(text):
        return _refunds(customer)
    if PAYMENT.search(text) and (FAILED.search(text) or re.search(r"\bmy payments?\b", text)):
        return _payments(customer, text)
    if CASHBACK.search(text):
        return _cashback(customer)
    if POINTS.search(text) and not re.search(r"\bpromo credit\b", text):
        return _rewards(customer, text)
    if WALLET.search(text) or (EXPIRY.search(text) and "credit" in text):
        return _wallet(customer, text)
    if OFFERS.search(text):
        return _offers(customer, text)
    if NOTIF.search(text):
        return _notifications(customer)
    if ACTIVITY.search(text):
        return _activity(customer, text)
    return None


def _add_money(customer) -> BuddyReply:
    from apps.wallet import services as wallet

    if customer is None:
        return _signin("wallet")
    if not wallet.topup_available():
        return BuddyReply("Adding money isn’t available right now because no payment provider is connected. Refunds, cashback and rewards still arrive in your wallet.",
                          actions=[{"label": "Open wallet", "path": "/wallet"}])
    acc = wallet.account(customer)
    if acc.status != "active":
        return BuddyReply(f"Your wallet is {acc.get_status_display().lower()}, so adding money is paused. {acc.status_reason}".strip(),
                          actions=[{"label": "Contact support", "path": "/help/new?category=wallet"}])
    lim = wallet.limits()
    return BuddyReply(f"I’ll open Add money. You choose the amount ({_r(lim['min_topup'])}–{_r(lim['max_topup'])}) and pay with the payment provider; "
                      "your wallet is credited only after the payment is confirmed. I never add money for you.",
                      actions=[{"label": "Add money", "path": "/wallet?add=1"}])


def _wallet(customer, text: str) -> BuddyReply:
    from apps.wallet import services as wallet

    if customer is None:
        return _signin("wallet")
    b = wallet.breakdown(customer)
    total = b["cash"] + b["promo"]
    lots = [(t, rem) for t, rem in wallet.lots(customer) if t.expires_at]
    soon = [(t, rem) for t, rem in lots if t.expires_at <= timezone.now() + timedelta(days=7)]
    if EXPIRY.search(text):
        if not b["promo"]:
            return BuddyReply("You have no promotional credit, so nothing is expiring. Your wallet balance doesn’t expire.", actions=[{"label": "Open wallet", "path": "/wallet"}])
        t, rem = sorted(lots, key=lambda x: x[0].expires_at)[0]
        return BuddyReply(f"You have {_r(b['promo'])} of promo credit. The next {_r(rem)} expires on {timezone.localtime(t.expires_at):%d %b %Y}. "
                          "Promo credit is used first at checkout.", actions=[{"label": "See credits", "path": "/wallet"}])
    rows = list(customer.wallet_transactions.order_by("-created_at")[:3])
    recent = "; ".join(f"{t.get_kind_display()} {'+' if t.amount > 0 else '−'}{_r(abs(t.amount))}" for t in rows)
    msg = f"Your Click. Wallet balance is {_r(total)} ({_r(b['cash'])} wallet balance + {_r(b['promo'])} promo credit)."
    if soon:
        msg += f" {_r(sum(rem for _, rem in soon))} of promo credit expires within 7 days."
    if recent and re.search(r"\b(recent|last|latest|activity|transactions?|history)\b", text):
        msg += f" Latest: {recent}."
    return BuddyReply(msg, actions=[{"label": "Open wallet", "path": "/wallet"}, {"label": "Wallet activity", "path": "/wallet#mn-activity"}])


def _cashback(customer) -> BuddyReply:
    from apps.wallet.models import CashbackOffer

    now = timezone.now()
    live = list(CashbackOffer.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)[:3])
    earned = ""
    if customer is not None:
        got = customer.wallet_transactions.filter(kind="cashback")
        if got.exists():
            last = got.order_by("-created_at").first()
            earned = f"Your last cashback was {_r(last.amount)} for {last.description}. "
    if not live:
        return BuddyReply(earned + "There’s no cashback offer running right now.", actions=[{"label": "See offers", "path": "/offers"}])
    lines = "; ".join(f"{o.title} (up to {_r(o.max_cashback)}, min {_r(o.min_amount)})" for o in live)
    return BuddyReply(f"{earned}Cashback offers now: {lines}. Cashback is added as promo credit after the order is delivered or the trip is completed.",
                      actions=[{"label": "Cashback offers", "path": "/offers?kind=cashback"}])


def _refunds(customer) -> BuddyReply:
    if customer is None:
        return _signin("refunds")
    rows = list(customer.wallet_transactions.filter(kind="refund").order_by("-created_at")[:3])
    if not rows:
        return BuddyReply("I don’t see any refunds on your account. Refunds of wallet payments are credited to your Click. Wallet as soon as a cancellation or return is approved.",
                          actions=[{"label": "Payments", "path": "/account/payments"}, {"label": "Get help", "path": "/help/articles/refund-status"}])
    t = rows[0]
    more = f" You’ve had {len(rows)} recent refunds." if len(rows) > 1 else ""
    return BuddyReply(f"Your latest refund of {_r(t.amount)} ({t.description}) was credited to your Click. Wallet on {timezone.localtime(t.created_at):%d %b}.{more}",
                      actions=[{"label": "Refund details", "path": f"/wallet/activity/{t.id}"}, {"label": "All refunds", "path": "/account/payments?tab=refunds"}])


def _payments(customer, text: str) -> BuddyReply:
    from apps.payments.records import describe, owned, with_relations

    if customer is None:
        return _signin("payments")
    qs = with_relations(owned(customer)).order_by("-created_at")
    failed = list(qs.filter(status="failed")[:3])
    pending = list(qs.filter(status__in=["pending", "authorized"]).exclude(method__in=["cash_on_delivery", "cash", "pay_at_venue"])[:3])
    if FAILED.search(text):
        if not failed and not pending:
            return BuddyReply("None of your recent payments failed or are stuck.", actions=[{"label": "Payments", "path": "/account/payments"}])
        p = (failed or pending)[0]
        d = describe(p)
        state = "failed" if p.status == "failed" else "is waiting for confirmation"
        return BuddyReply(f"Your {_r(p.amount)} payment for {d['label']} {d['reference']} {state}. "
                          + ("If money left your account, your bank or payment app returns it." if p.status == "failed" else "It updates only when the provider confirms; nothing is assumed."),
                          actions=[{"label": "Payment details", "path": f"/account/payments/{p.id}"}, {"label": "Report a problem", "path": f"/help/new?category=payment&related=payment:{p.id}"}])
    rows = list(qs[:3])
    if not rows:
        return BuddyReply("You haven’t made any payments yet.", actions=[{"label": "Payments", "path": "/account/payments"}])
    lines = "; ".join(f"{describe(p)['label']} {_r(p.amount)} by {p.get_method_display()}" for p in rows)
    return BuddyReply(f"Your latest payments: {lines}.", actions=[{"label": "All payments", "path": "/account/payments"}])


def _rewards(customer, text: str) -> BuddyReply:
    from apps.rewards import services as rewards

    if customer is None:
        return _signin("Click. points")
    b = rewards.balance(customer)
    t = rewards.tier_of(customer)
    if "redeem" in text:
        return BuddyReply(f"You have {b['balance']:,} points. Pick a reward and confirm it on the Redeem screen; I won’t redeem points for you.",
                          actions=[{"label": "Redeem points", "path": "/rewards?tab=redeem"}])
    if re.search(r"\bmissions?\b", text):
        ms = [m for m in rewards.missions(customer) if not m["completed"] and not m["expired"]]
        if not ms:
            return BuddyReply("You’ve completed every mission that’s running. New ones appear on the Rewards page.", actions=[{"label": "Rewards", "path": "/rewards?tab=earn"}])
        m = ms[0]
        return BuddyReply(f"{len(ms)} mission{'s' if len(ms) > 1 else ''} in progress. Closest: {m['title']} — {m['progress']}/{m['target']}, worth {m['points']} points.",
                          actions=[{"label": "See missions", "path": "/rewards?tab=earn"}])
    msg = f"You have {b['balance']:,} Click. points and you’re {t['name']} ({t['multiplier']}× points)."
    if t.get("next"):
        msg += f" {t['to_next']:,} more points in 12 months gets you {t['next']['name']}."
    if b.get("expiring"):
        e, pts = b["expiring"][0]
        msg += f" {pts:,} points expire on {timezone.localtime(e.expires_at):%d %b}."
    return BuddyReply(msg, actions=[{"label": "Open rewards", "path": "/rewards"}, {"label": "Redeem", "path": "/rewards?tab=redeem"}])


def _offers(customer, text: str) -> BuddyReply:
    from apps.offers import catalog

    service = next((s for k, s in SERVICES.items() if re.search(rf"\b{k}", text)), "")
    rows = [o for o in catalog.all_offers(customer) if not service or o["service"] == service]
    rows.sort(key=lambda o: -o["value_score"])
    if not rows:
        return BuddyReply(f"There are no live offers{f' on {catalog.SERVICE_LABEL.get(service, service)}' if service else ''} right now.", actions=[{"label": "All offers", "path": "/offers"}])
    top = rows[:3]
    lines = "; ".join(f"{o['benefit']} — {o['title']}" + (f" (code {o['code']})" if o["code"] else "") for o in top)
    where = f" on {catalog.SERVICE_LABEL.get(service, service)}" if service else ""
    return BuddyReply(f"{len(rows)} live offer{'s' if len(rows) != 1 else ''}{where}. Best value: {lines}. Each one is checked again at checkout.",
                      actions=[{"label": "See offers", "path": f"/offers?service={service}" if service else "/offers"}])


def _notifications(customer) -> BuddyReply:
    if customer is None:
        return _signin("notifications")
    unread = customer.notifications.filter(read_at__isnull=True)
    n = unread.count()
    if not n:
        return BuddyReply("You’re all caught up — no unread notifications.", actions=[{"label": "Notifications", "path": "/notifications"}])
    latest = unread.order_by("-created_at").first()
    return BuddyReply(f"You have {n} unread notification{'s' if n > 1 else ''}. Latest: {latest.title}.",
                      actions=[{"label": "Open notifications", "path": "/notifications"}] + ([{"label": "Open latest", "path": latest.link_path}] if latest.link_path else []))


def _activity(customer, text: str) -> BuddyReply:
    from apps.activity.timeline import timeline

    if customer is None:
        return _signin("activity")
    rows = timeline(customer, None, timezone.now())["results"][:4]
    if not rows:
        return BuddyReply("There’s no activity on your account yet.", actions=[{"label": "Activity", "path": "/activity"}])
    lines = "; ".join(f"{r['title']}" + (f" ({r['status']})" if r["status"] else "") for r in rows)
    return BuddyReply(f"Your latest activity: {lines}.", actions=[{"label": "Open activity", "path": "/activity"}])


def _support(customer) -> BuddyReply:
    if customer is None:
        return BuddyReply("You can browse help articles now, or sign in to raise a support request.", actions=[{"label": "Help & Support", "path": "/help"}])
    open_ = customer.support_tickets.exclude(status__in=["resolved", "closed"]).order_by("-updated_at")
    if not open_.exists():
        return BuddyReply("You have no open support requests. If something’s wrong, raise one and the order or booking is attached automatically.",
                          actions=[{"label": "Contact support", "path": "/help/new"}, {"label": "My requests", "path": "/help/tickets"}])
    t = open_.first()
    return BuddyReply(f"You have {open_.count()} open request{'s' if open_.count() > 1 else ''}. Latest: {t.reference} “{t.subject}” — {t.get_status_display()}.",
                      actions=[{"label": "Open request", "path": f"/help/tickets/{t.id}"}, {"label": "All requests", "path": "/help/tickets"}])
