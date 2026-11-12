"""Buddy's conversation and action layer: persistence and ownership, follow-up context, typed actions with server-side
validation and permission tiers (safe runs, confirm waits, high-risk refused), redaction, no silent payments."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai.models import ActionExecution, BuddyEvent, Conversation, ConversationMessage
from apps.carts.models import CartItem
from apps.orders.models import Order

pytestmark = pytest.mark.django_db
A = "/api/v1/customer/assistant"


def say(api, conv_id, text, **extra):
    return api.post(f"{A}/conversations/{conv_id}/messages", {"content": text, **extra}, format="json")


@pytest.fixture
def conv(auth_api):
    return auth_api.post(f"{A}/conversations", {"mode": "man"}, format="json").json()["id"]


def test_conversations_are_private_titled_renamable_and_restored_without_rerunning(auth_api, conv, other_customer):
    r = say(auth_api, conv, "Find a birthday planner for 30 people")
    assert r.status_code == 200 and r.json()["conversation"]["title"] == "Birthday Planning"
    lst = auth_api.get(f"{A}/conversations").json()["results"]
    assert lst[0]["id"] == conv and lst[0]["preview"]
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"{A}/conversations/{conv}").status_code == 404
    assert say(other, conv, "hi").status_code == 404
    assert other.get(f"{A}/conversations").json()["results"] == []
    n = ConversationMessage.objects.count()
    full = auth_api.get(f"{A}/conversations/{conv}").json()
    assert len(full["messages"]) == 2 and ConversationMessage.objects.count() == n  # reopening doesn't re-run anything
    assert auth_api.patch(f"{A}/conversations/{conv}", {"title": "Aarav’s party"}, format="json").json()["title"] == "Aarav’s party"
    say(auth_api, conv, "and a cake")
    assert Conversation.objects.get(pk=conv).title == "Aarav’s party"  # a custom title is kept
    auth_api.patch(f"{A}/conversations/{conv}", {"archived": True}, format="json")
    assert auth_api.get(f"{A}/conversations").json()["results"] == [] and auth_api.get(f"{A}/conversations?archived=true").json()["results"]
    assert auth_api.delete(f"{A}/conversations/{conv}").status_code == 204 and not Conversation.objects.filter(pk=conv).exists()


def test_followups_refine_the_last_search_and_secrets_are_redacted(auth_api, conv, store, products):
    r = say(auth_api, conv, "Find restaurants nearby").json()
    assert any(c["type"] == "store" for c in r["message"]["cards"])
    r2 = say(auth_api, conv, "only vegetarian").json()
    assert r2["understoodAs"] == "Find restaurants nearby only vegetarian" and "pure-veg" in r2["message"]["content"].lower()
    r3 = say(auth_api, conv, "the cheapest one").json()
    assert "lowest prices first" in r3["message"]["content"]
    say(auth_api, conv, "my card is 4111 1111 1111 1111 and otp 123456")
    stored = ConversationMessage.objects.filter(role="user").last().content
    assert "4111" not in stored and "123456" not in stored


def test_navigation_and_cart_are_safe_actions_run_through_the_action_layer(auth_api, conv, customer, products):
    r = say(auth_api, conv, "Open my wishlist").json()
    nav = next(c["result"] for c in r["message"]["cards"] if c["type"] == "action_result")
    assert nav["action"] == "open_page" and nav["status"] == "done" and nav["result"]["navigate"] == "/wishlist"  # ran via the action layer
    ok = auth_api.post(f"{A}/actions", {"action": "open_page", "args": {"path": "/wishlist"}}, format="json").json()
    assert ok["status"] == "done" and ok["result"]["navigate"] == "/wishlist"
    assert auth_api.post(f"{A}/actions", {"action": "open_page", "args": {"path": "https://evil.example"}}, format="json").status_code == 400
    assert auth_api.post(f"{A}/actions", {"action": "change_phone", "args": {}}, format="json").status_code == 403
    assert auth_api.post(f"{A}/actions", {"action": "drop_database", "args": {}}, format="json").status_code == 400
    name = products[0].name.split()[0].lower()
    r = say(auth_api, conv, f"Add 2 {name} to my cart").json()
    res = [c["result"] for c in r["message"]["cards"] if c["type"] == "action_result"]
    assert res and res[0]["status"] == "done" and CartItem.objects.filter(cart__customer=customer.customer_profile).exists()
    assert "Nothing is ordered" in r["message"]["content"]
    assert not Order.objects.exists()  # preparing a cart never orders or pays
    undo = res[0]["result"]["undo"]
    assert auth_api.post(f"{A}/actions", undo, format="json").json()["status"] == "done"
    assert not CartItem.objects.filter(cart__customer=customer.customer_profile).exists()
    assert set(BuddyEvent.objects.values_list("kind", flat=True)) >= {"action_requested", "action_completed", "message"}
    assert not BuddyEvent.objects.filter(detail__icontains=name).exclude(kind="message").exists()  # no message text in analytics


def test_confirmation_tier_waits_for_the_customer_and_expires(auth_api, customer, other_customer, store, products, address):
    from apps.orders.models import OrderStatus

    o = Order.objects.create(customer=customer.customer_profile, store=store, status=OrderStatus.PLACED, number="ORD-TEST1", idempotency_key=uuid.uuid4(), subtotal=D("100"),
                             delivery_fee=D("0"), tax=D("0"), total=D("100"), delivery_address={"line1": "x"})
    r = auth_api.post(f"{A}/actions", {"action": "cancel_order", "args": {"order_id": str(o.id)}}, format="json").json()
    assert r["status"] == "awaiting_confirmation" and "ORD-TEST1" in r["summary"]
    o.refresh_from_db()
    assert o.status == OrderStatus.PLACED  # nothing happened yet
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.post(f"{A}/actions/{r['id']}/confirm", {}, format="json").status_code == 404
    done = auth_api.post(f"{A}/actions/{r['id']}/confirm", {}, format="json").json()
    assert done["status"] == "confirmed"
    o.refresh_from_db()
    assert o.status == OrderStatus.CANCELLED
    assert auth_api.post(f"{A}/actions/{r['id']}/confirm", {}, format="json").status_code == 409  # one confirmation only
    o2 = Order.objects.create(customer=customer.customer_profile, store=store, status=OrderStatus.PLACED, number="ORD-TEST2", idempotency_key=uuid.uuid4(), subtotal=D("100"),
                              delivery_fee=D("0"), tax=D("0"), total=D("100"), delivery_address={"line1": "x"})
    r2 = auth_api.post(f"{A}/actions", {"action": "cancel_order", "args": {"order_id": str(o2.id)}}, format="json").json()
    ActionExecution.objects.filter(pk=r2["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert auth_api.post(f"{A}/actions/{r2['id']}/confirm", {}, format="json").json()["error"]["code"] == "action_expired"
    assert auth_api.post(f"{A}/actions", {"action": "cancel_order", "args": {"order_id": str(uuid.uuid4())}}, format="json").status_code == 404


def test_intents_route_to_the_right_feature_and_titles_match(auth_api, conv):
    from apps.ai.conversation import make_title
    from apps.ai.event_buddy import wants_event

    assert wants_event("find a birthday planner for 30 people") and wants_event("i need a wedding decorator")
    r = say(auth_api, conv, "Show my recent orders").json()
    assert "showtime" not in str(r["message"]["actions"]).lower()  # "show" is not a movie request
    assert make_title("Show me my rewards") != "Movies & shows" and make_title("Show my recent orders") == "Your orders"
