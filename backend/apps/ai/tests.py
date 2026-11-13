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
    # Services are live, but with no catalog or professionals Buddy must not invent anyone or offer a booking.
    plumber = ask(auth_api, "I need a plumber")
    assert plumber["cards"] == [] and not any(a.get("path", "").startswith("/services/pro/") for a in plumber["actions"])
    # Rides are live now: Buddy hands off to Ride (with the destination) but never books it.
    cab = ask(auth_api, "book me a cab to the airport")
    assert cab["actions"] == [{"label": "Plan this ride", "path": "/rides?to=airport"}]


def test_capabilities_report_voice_off_by_default(auth_api):
    r = auth_api.get("/api/v1/customer/assistant/capabilities")
    assert r.status_code == 200
    assert r.json() == {"mode": "basic", "voice": False, "visualSearch": False}


def test_capabilities_and_transcribe_require_a_customer(api):
    assert api.get("/api/v1/customer/assistant/capabilities").status_code == 401
    assert api.post("/api/v1/customer/assistant/transcribe").status_code == 401


def test_transcribe_is_unavailable_without_a_provider(auth_api):
    from django.core.files.uploadedfile import SimpleUploadedFile

    audio = SimpleUploadedFile("a.webm", b"\x1aE\xdf\xa3", content_type="audio/webm")
    r = auth_api.post("/api/v1/customer/assistant/transcribe", {"audio": audio}, format="multipart")
    assert r.status_code == 503 and r.json()["error"]["code"] == "speech_unavailable"


def test_transcribe_uses_configured_provider_and_validates_audio(auth_api, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.CLICK_SPEECH_PROVIDER = "apps.ai.tests.EchoSpeech"
    ok = SimpleUploadedFile("a.webm", b"audio", content_type="audio/webm")
    r = auth_api.post("/api/v1/customer/assistant/transcribe", {"audio": ok}, format="multipart")
    assert r.status_code == 200 and r.json() == {"text": "find biryani"}
    bad = SimpleUploadedFile("a.txt", b"nope", content_type="text/plain")
    assert auth_api.post("/api/v1/customer/assistant/transcribe", {"audio": bad}, format="multipart").status_code == 400
    assert auth_api.get("/api/v1/customer/assistant/capabilities").json()["voice"] is True


class EchoSpeech:
    def transcribe(self, audio, content_type, language):
        return " find biryani "


def test_buddy_hands_ride_requests_to_ride_without_booking(auth_api):
    r = auth_api.post("/api/v1/customer/assistant/messages", {"messages": [{"role": "user", "content": "Take me to the airport"}]}, format="json")
    body = r.json()
    assert r.status_code == 200 and "airport" in body["message"]["content"]
    assert body["actions"] == [{"label": "Plan this ride", "path": "/rides?to=airport"}]


def test_buddy_tells_watching_from_buying_a_watch(auth_api):
    tonight = ask(auth_api, "What should I watch tonight?")
    assert "Shopping" not in tonight["message"]["content"]
    assert any(a["path"].startswith("/showtime") for a in tonight["actions"])
    watch = ask(auth_api, "find me a watch under 3000")
    assert not any(a["path"].startswith("/showtime") for a in watch.get("actions", []))


def test_buddy_groceries_prepare_but_never_order(auth_api):
    body = ask(auth_api, "I need milk and bread")
    assert body["actions"][0]["path"] == "/groceries/lists?items=milk%2Cbread"
    assert "add items yourself" in body["message"]["content"]
    from apps.carts.models import CartItem
    from apps.orders.models import Order

    assert not CartItem.objects.exists() and not Order.objects.exists()


def test_buddy_parcels_prepare_but_never_book(auth_api):
    body = ask(auth_api, "Send this package to my brother")
    assert body["actions"][0]["path"].startswith("/parcels?mode=send")
    assert "don't book or pay" in body["message"]["content"]
    assert ask(auth_api, "Pick up a parcel from my friend")["actions"][0]["path"] == "/parcels?mode=receive"
    from apps.parcels.models import ParcelOrder

    assert not ParcelOrder.objects.exists()
