"""
Buddy's parcel help, from real Click. Parcel data only. Buddy prepares the booking (mode, saved recipient) and reports
real status; it never quotes a price or time itself, never picks a partner and never books or pays — the customer
reviews the backend quote and confirms in the Parcel page.
"""

from __future__ import annotations

import re
from .providers import BuddyReply

WORDS = re.compile(r"\b(parcel|parcels|package|packages|courier|send (this|a|my|the)|deliver (this|a|my|the)|pick ?up from|"
                   r"collect from|document|documents)\b")


def wants_parcel(text: str) -> bool:
    return bool(WORDS.search(text))


def reply(text: str, customer) -> BuddyReply | None:
    from apps.parcels.models import ACTIVE_STATUSES, ParcelOrder, ParcelStatus, SavedRecipient

    if customer is None:
        return BuddyReply("Sign in and I'll help you send or track a parcel.", actions=[{"label": "Open Parcel", "path": "/parcels"}])

    if re.search(r"\b(where|track|status|arrived|arriving|delivered)\b", text):
        live = list(ParcelOrder.objects.filter(customer=customer, status__in=[*ACTIVE_STATUSES, ParcelStatus.SCHEDULED])
                    .select_related("service")[:3])
        if not live:
            last = ParcelOrder.objects.filter(customer=customer).first()
            if last is None:
                return BuddyReply("You haven't sent any parcels yet.", actions=[{"label": "Send a parcel", "path": "/parcels"}])
            return BuddyReply(f"No parcel is on the way right now. Your last one, {last.number}, is {last.get_status_display().lower()}.",
                              actions=[{"label": "View it", "path": f"/parcels/{last.id}"}])
        lines = "; ".join(f"{p.number} to {p.drop_label}: {p.get_status_display().lower()}" for p in live)
        return BuddyReply(f"Here's where your parcels are: {lines}. Status comes from the delivery partner's confirmed steps.",
                          actions=[{"label": f"Track {p.number}", "path": f"/parcels/{p.id}"} for p in live])

    store = re.search(r"\b(from (the|a|my) (store|shop|kirana)|store pickup)\b", text)
    receive = re.search(r"\breceive\b|\b(collect|pick ?up|get)\b.*\bfrom (my|a|the|his|her)\b", text)
    mode = "store_pickup" if store else "receive" if receive else "send"
    params = [f"mode={mode}"]
    who = ""
    m = re.search(r"\bto (?:my )?([a-z][a-z .']{1,30}?)(?:\b(?:at|in|by|tomorrow|today|now|please)\b|[.?!,]|$)", text)
    if m and mode == "send":
        name = m.group(1).strip()
        r = (SavedRecipient.objects.filter(customer=customer).filter(label__icontains=name).first()
             or SavedRecipient.objects.filter(customer=customer, name__icontains=name).first())
        if r:
            params.append(f"recipient={r.id}")
            who = f" I've filled in {r.name} from your saved recipients."
        else:
            who = f" I couldn't find “{name}” in your saved recipients, so add their name, number and address."
    lead = {
        "send": "Let's send it. Choose the pickup and drop, tell me what's inside and its size, then pick the delivery type and vehicle.",
        "receive": "Let's get it picked up for you. Add the sender's location and contact, then the package details.",
        "store_pickup": "Pick the store and your order reference, and Click. will collect it and bring it to you.",
    }[mode]
    return BuddyReply(lead + who + " You'll see the backend's estimated price and time before you confirm and pay; I don't book or pay for you.",
                      actions=[{"label": "Start the booking", "path": "/parcels?" + "&".join(params)}])

