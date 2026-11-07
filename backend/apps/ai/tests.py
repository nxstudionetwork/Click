import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db
MSG = {"messages": [{"role": "user", "content": "Where is my order?"}]}


class EchoProvider:
    def reply(self, messages, context):
        return f"{context.surface}:{len(context.facts['recent_orders'])}:{messages[-1].content}"


@override_settings(CLICK_AI_PROVIDER="")
def test_ai_unavailable_when_disabled(auth_api):
    r = auth_api.post("/api/v1/customer/assistant/messages", MSG)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_unavailable"


@override_settings(CLICK_AI_PROVIDER="apps.ai.tests.EchoProvider")
def test_ai_uses_configured_provider_with_customer_scoped_context(auth_api):
    r = auth_api.post("/api/v1/customer/assistant/messages", MSG)
    assert r.json()["message"] == {"role": "assistant", "content": "customer:0:Where is my order?"}


def test_ai_validates_input(auth_api):
    assert auth_api.post("/api/v1/customer/assistant/messages", {"messages": []}).status_code == 400


def test_ai_requires_customer(api):
    assert api.post("/api/v1/customer/assistant/messages", MSG).status_code == 401


# --- Buddy basic mode (default provider): answers only from real data ---------

def ask(api, text):
    r = api.post("/api/v1/customer/assistant/messages", {"messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200, r.json()
    return r.json()


def test_buddy_search_returns_real_products(auth_api, products):
    body = ask(auth_api, "find me some dal")
    assert body["mode"] == "basic"
    assert [c["product"]["name"] for c in body["cards"] if c["type"] == "product"] == ["Dal"]


def test_buddy_is_honest_when_nothing_matches(auth_api, products):
    body = ask(auth_api, "find sushi")
    assert body["cards"] == [] and "couldn’t find" in body["message"]["content"]


def test_buddy_order_status_uses_customers_own_orders(api, customer, other_customer, products, address):
    import uuid

    api.force_authenticate(customer)
    api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    order = api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())}).json()
    body = ask(api, "where is my order?")
    assert order["number"] in body["message"]["content"] and body["cards"][0]["order"]["id"] == order["id"]

    api.force_authenticate(other_customer)
    assert "don’t have any orders" in ask(api, "where is my order?")["message"]["content"]


def test_buddy_never_claims_unlaunched_services(auth_api):
    assert "isn’t live" in ask(auth_api, "book me a cab to the airport")["message"]["content"]
