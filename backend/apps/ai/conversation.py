"""
Buddy conversations: one place that turns a customer message into a stored exchange.

  1. redact likely secrets (card numbers, CVV / OTP / PIN codes) before anything is stored or sent to a provider
  2. resolve follow-ups from the conversation's explicit context: "only vegetarian", "the cheapest one", "under 5000"
     refine the previous search instead of starting over (context = {"topic", "query"}, nothing else)
  3. ask the configured AI provider (apps.ai.providers — swappable; Buddy basic mode by default) with a short history
  4. run the *safe* actions the reply asked to run automatically ("add milk to my cart") through apps.ai.actions —
     validation and permissions there, never in the AI; confirmation-tier actions are only proposed
  5. store both messages (with the factual cards from Click APIs), update the title and context
"""

from __future__ import annotations

import re

from django.utils import timezone

from . import actions
from .models import ActionExecution, Conversation, ConversationMessage
from .providers import AIContext, AIMessage, BuddyReply

HISTORY = 10

_SECRETS = [
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card number removed]"),
    (re.compile(r"\b(cvv|cvc|otp|pin|upi pin|password|passcode)\b\s*(is|:)?\s*\S+", re.I), r"\1 [removed]"),
]


def redact(text: str) -> str:
    for rx, sub in _SECRETS:
        text = rx.sub(sub, text)
    return text


TOPICS = [
    ("travel", r"\b(bus|buses|trains?|flights?|fly)\b.{0,40}\b(from|to)\b|\bpnr\b", "Travel"),
    ("bookings", r"\b(temples?|darshan|seva|water ?park|zoo|museum|tourist|attractions?|things to do|my (upcoming )?bookings)\b", "Bookings"),
    ("hotels", r"\b(hotels?|resorts?|stay|homestay|hostel|villa)\b", "Hotel stay"),
    ("events", r"\b(birthday|wedding|party|event|planner|decorator|venue|anniversary)\b", "Event planning"),
    ("services", r"\b(plumber|electrician|carpenter|cleaner|cleaning|repair|leak|painter|pest|ac service)\b", "Home services"),
    ("parcel", r"\b(parcel|courier|package|deliver this)\b", "Parcel"),
    ("ride", r"\b(ride|cab|auto|taxi|drop me|airport)\b", "Ride"),
    ("groceries", r"\b(grocer(y|ies)|milk|bread|eggs|vegetables|fruits|atta|rice)\b", "Grocery shopping"),
    ("orders", r"\b(my (recent |last |latest |pending |active )?orders?|order status|where is my order|track( my)? order)\b", "Your orders"),
    ("showtime", r"\b(movies?|films?|showtime|shows tonight|concerts?|tickets?)\b", "Movies & shows"),
    ("shopping", r"\b(shoes?|phone|laptop|earbuds|headphones|shirt|dress|watch|gift)\b", "Shopping"),
    ("food", r"\b(restaurants?|food|biryani|pizza|dinner|lunch|breakfast|eat|dosa|burger|vegetarian|veg)\b", "Food"),
    ("wallet", r"\b(wallet|balance|refunds?|payments?|transactions?)\b", "Wallet & payments"),
]
REFINE = re.compile(r"^(only|just|and|but|now|what about|how about|cheaper|cheapest|nearest|closest|best|top|under|below|less than|within|with|without|"
                    r"veg|vegetarian|non[- ]veg|the (first|second|third|cheapest|nearest)|show me the|that one|any)\b")


def topic_of(text: str) -> tuple[str, str]:
    t = text.lower()
    for key, rx, title in TOPICS:
        if re.search(rx, t):
            return key, title
    return "", ""


def effective_text(conv: Conversation, text: str) -> str:
    """A short refinement applies to the previous search ("Find restaurants nearby" → "only vegetarian" → "the cheapest one");
    a message about something else starts fresh."""
    ctx = conv.context or {}
    t = text.strip().lower()
    if not ctx.get("query"):
        return text.strip()
    new_topic = topic_of(t)[0]
    if new_topic and new_topic != ctx.get("topic") and not REFINE.search(t):
        return text.strip()
    if REFINE.search(t) or len(t.split()) <= 3:
        return f"{ctx['query']} {text.strip()}"
    return text.strip()


def make_title(text: str) -> str:
    t = text.lower()
    named = [("Birthday Planning", r"\bbirthday\b"), ("Wedding Planning", r"\bwedding\b"), ("Find a Plumber", r"\bplumb"),
             ("Find an Electrician", r"\belectric"), ("Parcel Tracking", r"\btrack.{0,10}parcel|\bparcel.{0,10}track"),
             ("Ride to Airport", r"\bairport\b.*\b(ride|cab|drop)|\b(ride|cab|drop)\b.*\bairport\b"), ("Grocery Shopping", r"\bgrocer|\bmilk\b|\bbread\b"),
             ("Order Status", r"\b(my orders?|where is my order)\b"), ("Movies Tonight", r"\bmovies?\b.*\btonight\b")]
    for title, rx in named:
        if re.search(rx, t):
            return title
    m = re.search(r"\bhotels?\b.*\bin ([a-z]+)", t)
    if m:
        return f"Hotel in {m.group(1).title()}"
    topic, title = topic_of(t)
    if title:
        return title
    words = re.sub(r"[^\w\s]", "", text).split()
    return (" ".join(words[:5]).capitalize() or "New chat")[:60]


def _context(customer, language: str) -> AIContext:
    from .views import customer_context

    ctx = customer_context(customer)
    return AIContext(surface=ctx.surface, actor_id=ctx.actor_id, facts={**ctx.facts, "language": language}, customer=customer)


def message_out(m: ConversationMessage) -> dict:
    return {"id": str(m.id), "role": m.role, "content": m.content, "cards": m.cards, "actions": m.actions, "attachment": m.attachment,
            "via_voice": m.via_voice, "created_at": m.created_at.isoformat()}


def run(conv: Conversation, text: str, provider, *, via_voice: bool = False, attachment: dict | None = None, language: str = "en") -> dict:
    clean = redact(text)[:2000]
    asked = effective_text(conv, clean)
    if attachment:
        asked = f"{asked} (about {attachment.get('label', attachment.get('kind'))})"
    history = [AIMessage(role=m.role, content=m.content) for m in conv.messages.order_by("-created_at")[:HISTORY]][::-1]
    reply = provider.reply([*history, AIMessage(role="user", content=asked)], _context(conv.customer, language))
    if isinstance(reply, str):
        reply = BuddyReply(reply)
    ConversationMessage.objects.create(conversation=conv, role="user", content=clean, attachment=attachment or {}, via_voice=via_voice)
    # Safe actions the reply asked to run now (e.g. add to cart) go through the action layer; others stay proposals.
    results, proposals = [], []
    for a in reply.actions:
        if a.get("action") and a.get("auto") and actions.REGISTRY.get(a["action"]) and actions.REGISTRY[a["action"]].tier == "safe":
            r = actions.request(conv.customer, a["action"], a.get("args") or {}, conv)
            results.append(actions.out(r))
        else:
            proposals.append(a)
    content = reply.content
    if results:
        done = [r["result"].get("message", "") for r in results if r["status"] == ActionExecution.Status.DONE]
        failed = [r["result"].get("message", "") for r in results if r["status"] == ActionExecution.Status.FAILED]
        content = " ".join(x for x in [content, *done, *(f"Couldn’t do one step: {f}" for f in failed)] if x)
    cards = reply.cards + [{"type": "action_result", "result": r} for r in results]
    m = ConversationMessage.objects.create(conversation=conv, role="assistant", content=content, cards=cards, actions=proposals)
    topic, _ = topic_of(asked)
    if reply.cards and topic:
        conv.context = {"topic": topic, "query": asked[:300]}
    elif topic and topic != (conv.context or {}).get("topic"):
        conv.context = {}
    if not conv.title_custom and (not conv.title or conv.messages.count() <= 2):
        conv.title = make_title(clean)
    conv.last_message_at = timezone.now()
    conv.save(update_fields=["context", "title", "last_message_at", "updated_at"])
    return {"message": message_out(m), "conversation": conversation_out(conv), "understood_as": asked if asked != clean else None,
            "mode": getattr(provider, "mode", "provider")}


def conversation_out(c: Conversation, preview: bool = False) -> dict:
    out = {"id": str(c.id), "title": c.title or "New chat", "archived": c.archived, "mode": c.mode, "topic": (c.context or {}).get("topic", ""),
           "updated_at": (c.last_message_at or c.created_at).isoformat()}
    if preview:
        last = c.messages.order_by("-created_at").first()
        out["preview"] = (last.content[:120] if last else "")
    return out
