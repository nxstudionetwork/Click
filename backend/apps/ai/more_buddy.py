"""
Buddy for Invoices, Gift Cards, Safety Center, Pharma and Discover. Answers come from the same records the pages use.
Pharma rule: Buddy finds medicines by name or salt, never suggests a medicine for a symptom, and never replaces a
doctor's prescription.
"""

from __future__ import annotations

import re

from .providers import BuddyReply

INVOICE = re.compile(r"\b(invoices?|bills?|receipts?)\b")
GIFT = re.compile(r"\bgift ?cards?\b|\bgift (for|under)\b|\bbirthday gift\b")
SAFETY = re.compile(r"\b(unsafe|emergency|sos|safety|harass\w*|threat\w*)\b")
PHARMA = re.compile(r"\b(medicines?|tablets?|capsules?|syrup|pharmac(y|ies)|prescriptions?|chemists?)\b")
SYMPTOM = re.compile(r"\b(fever|headache|cold|cough|pain|sick|ill|infection|allergy|vomit\w*|diarrh\w*|rash|bp|sugar|what should i take|which medicine)\b")
DISCOVER = re.compile(r"\b(what'?s new|discover|something new|hidden gems?|trending near me|new (places|restaurants) near me)\b")


def wants(text: str) -> bool:
    return any(rx.search(text) for rx in (INVOICE, GIFT, SAFETY, PHARMA, DISCOVER))


def reply(text: str, customer) -> BuddyReply | None:
    if SAFETY.search(text):
        from django.conf import settings

        return BuddyReply(f"If you’re in danger, call {settings.CLICK_EMERGENCY_NUMBER} now. In Safety Center you can report a ride, parcel, "
                          "professional or payment problem as an urgent case, and share an active trip from the ride screen.",
                          actions=[{"label": f"Call {settings.CLICK_EMERGENCY_NUMBER}", "path": f"tel:{settings.CLICK_EMERGENCY_NUMBER}"},
                                   {"label": "Safety Center", "path": "/safety"}])
    if PHARMA.search(text):
        return _pharma(text)
    if INVOICE.search(text):
        return _invoices(customer)
    if GIFT.search(text):
        return _gift(text, customer)
    if DISCOVER.search(text):
        return BuddyReply("Discover shows what’s trending, new and highly rated around you, with a few clearly marked sponsored picks.",
                          actions=[{"label": "Open Discover", "path": "/discover"}])
    return None


def _pharma(text: str) -> BuddyReply:
    if SYMPTOM.search(text) and not re.search(r"\b\d+\s?mg\b", text):
        return BuddyReply("I can’t suggest medicines for symptoms. Please speak to a doctor or the pharmacist. If you already have a prescription, "
                          "upload it in Pharma and the pharmacy will review it; you can also search a medicine by its name or salt.",
                          actions=[{"label": "Upload prescription", "path": "/pharma/prescriptions"}, {"label": "Open Pharma", "path": "/pharma"}])
    from apps.pharma.views import _products

    words = [w for w in re.sub(r"\b(find|buy|order|need|search|for|me|a|the|medicines?|tablets?|pharmacy|near|from|some|get)\b", " ", text).split() if len(w) > 2][:3]
    qs = _products()
    for w in words:
        from django.db.models import Q

        qs = qs.filter(Q(name__icontains=w) | Q(composition__icontains=w))
    rows = list(qs[:3]) if words else []
    if not rows:
        return BuddyReply("Search medicines and health products by name or salt in Pharma. Prescription-only medicines need a prescription the pharmacy verifies.",
                          actions=[{"label": "Open Pharma", "path": "/pharma"}])
    lines = "; ".join(f"{p.name} ({p.pack_size}) ₹{p.price:.0f} at {p.store.name}" + (" — prescription required" if p.requires_prescription else "") for p in rows)
    return BuddyReply(f"I found: {lines}. Follow your doctor’s advice on what to take.", actions=[{"label": "See in Pharma", "path": f"/pharma/p/{rows[0].id}"}])


def _invoices(customer) -> BuddyReply:
    if customer is None:
        return BuddyReply("Sign in to see your invoices.", actions=[{"label": "Sign in", "path": "/login"}])
    from apps.invoices.builder import cards

    rows = [r for r in cards(customer) if r["id"]][:3]
    if not rows:
        return BuddyReply("You don’t have any invoices yet — they appear once an order or booking is paid.", actions=[{"label": "Invoices", "path": "/account/invoices"}])
    lines = "; ".join(f"{r['label']} {r['reference']} ₹{float(r['amount']):,.0f} ({r['number']})" for r in rows)
    return BuddyReply(f"Your latest invoices: {lines}.", actions=[{"label": "Open invoices", "path": "/account/invoices"}, {"label": "Latest invoice", "path": f"/account/invoices/{rows[0]['id']}"}])


def _gift(text: str, customer) -> BuddyReply:
    from apps.giftcards.models import GiftCard, GiftCardDesign
    from apps.giftcards.services import balance

    held = list(GiftCard.objects.filter(holder=customer, status="active")) if customer else []
    m = re.search(r"under\s*₹?\s*(\d{3,5})", text)
    designs = GiftCardDesign.objects.filter(is_active=True)
    if m:
        designs = designs.filter(min_amount__lte=int(m.group(1)))
    names = ", ".join(d.title for d in designs[:4])
    msg = f"You have {len(held)} gift card{'s' if len(held) != 1 else ''} worth ₹{sum(balance(c) for c in held):,.0f} to spend. " if held else ""
    msg += f"Gift cards you can send: {names}. You choose the amount" + (f" (up to ₹{m.group(1)})" if m else "") + ", and I won’t buy one for you."
    return BuddyReply(msg, actions=[{"label": "Gift Cards", "path": "/gift-cards"}] + ([{"label": "My gift cards", "path": "/gift-cards/mine"}] if held else []))
