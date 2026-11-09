import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import AttributeDefinition, Brand, Product, ProductAttributeValue, ProductDeal, ProductVariant, ShopCategory
from apps.orders import services as order_services
from apps.orders.models import Order, OrderStatus, ReturnRequest
from apps.orders.returns import resolve
from apps.shop.models import ProductReview, ShopCampaign
from apps.wallet.models import WalletTransaction
from conftest import make_customer, make_store
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def shop(db):
    """Two retail sellers, a small taxonomy with attributes, brands, listings (one with size/colour variants)."""
    electronics = ShopCategory.objects.create(name="Electronics", slug="electronics", icon="device")
    audio = ShopCategory.objects.create(name="Audio", slug="audio", parent=electronics, synonyms="headphones,earbuds,speaker")
    fashion = ShopCategory.objects.create(name="Fashion", slug="fashion", icon="shirt")
    mens = ShopCategory.objects.create(name="Men's Clothing", slug="mens-clothing", parent=fashion, synonyms="shirt,shirts,t-shirt")
    colour = AttributeDefinition.objects.create(category=electronics, code="color", name="Colour")
    battery = AttributeDefinition.objects.create(category=audio, code="battery", name="Battery life", kind="number", unit="hours")
    anc = AttributeDefinition.objects.create(category=audio, code="anc", name="Noise cancellation", kind="boolean")
    fabric = AttributeDefinition.objects.create(category=fashion, code="fabric", name="Fabric")
    volt = make_store("Volt", store_type="retail", delivery_fee=D("49"), free_delivery_above=D("1000"), min_order_amount=D("0"),
                      verified_at=timezone.now(), latitude=D("12.97"), longitude=D("77.64"), dispatch_days=1)
    loom = make_store("Loom", store_type="retail", delivery_fee=D("39"), min_order_amount=D("0"), cod_enabled=False, dispatch_days=2)
    sonique = Brand.objects.create(name="Sonique", slug="sonique")
    drift = Brand.objects.create(name="Drift", slug="drift")

    def listing(store, cat, name, price, brand, mrp=None, stock=20, **kw):
        return Product.objects.create(store=store, shop_category=cat, brand_ref=brand, name=name, price=D(price),
                                      compare_at_price=D(mrp) if mrp else None, stock_quantity=stock, return_days=7, **kw)

    buds = listing(volt, audio, "Pulse Wireless Earbuds", "1999", sonique, mrp="2999")
    phones = listing(volt, audio, "Studio Headphones", "4999", sonique, stock=2)
    speaker = listing(volt, audio, "Go Speaker", "1499", sonique)
    for p, (b, a, c) in {buds: ("30", "Yes", "Black"), phones: ("45", "Yes", "Black"), speaker: ("12", "No", "Teal")}.items():
        ProductAttributeValue.objects.create(product=p, definition=battery, value=b, number=D(b))
        ProductAttributeValue.objects.create(product=p, definition=anc, value=a)
        ProductAttributeValue.objects.create(product=p, definition=colour, value=c)
    shirt = listing(loom, mens, "Oxford Shirt", "899", drift, mrp="1299", stock=None)
    ProductAttributeValue.objects.create(product=shirt, definition=fabric, value="Cotton")
    variants = {}
    for size in ["M", "L"]:
        for col in ["Black", "White"]:
            variants[(col, size)] = ProductVariant.objects.create(product=shirt, options={"Color": col, "Size": size}, price=D("899"),
                                                                  compare_at_price=D("1299"), stock_quantity=0 if (col, size) == ("White", "L") else 5)
    jogger = listing(loom, mens, "Cargo Joggers", "999", drift)
    return {"volt": volt, "loom": loom, "audio": audio, "mens": mens, "electronics": electronics, "buds": buds, "phones": phones,
            "speaker": speaker, "shirt": shirt, "jogger": jogger, "variants": variants}


@pytest.fixture
def buyer(db):
    user = make_customer("buyer@example.com")
    from apps.customers.models import Address

    profile = user.customer_profile
    address = Address.objects.create(customer=profile, recipient_name="B", phone="+91 90000 00000", line1="1 Road", city="Bengaluru",
                                     postal_code="560001", is_default=True, latitude=D("12.95"), longitude=D("77.62"))
    WalletTransaction.objects.create(customer=profile, kind="promo", amount=D("10000"), description="test credit")
    api = APIClient()
    api.force_authenticate(user)
    return {"user": user, "profile": profile, "address": address, "api": api}


def add(api, product, variant=None, qty=1):
    body = {"productId": str(product.id), "quantity": qty}
    if variant:
        body["variantId"] = str(variant.id)
    return api.post("/api/v1/customer/cart/items", body, format="json")


def checkout(b, method="wallet", key=None):
    return b["api"].post("/api/v1/customer/checkout", {"addressId": str(b["address"].id), "paymentMethod": method,
                                                       "idempotencyKey": key or str(uuid.uuid4())}, format="json")


def deliver(order):
    for s in [OrderStatus.CONFIRMED, OrderStatus.PACKED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
        order = order_services.transition_order(order, s)
    return order


# --- cart, pricing, checkout -------------------------------------------------------------------------------

def test_marketplace_cart_spans_sellers_with_per_seller_delivery_and_splits_into_orders(shop, buyer):
    api = buyer["api"]
    assert add(api, shop["buds"]).status_code == 201
    r = add(api, shop["shirt"], shop["variants"][("Black", "M")], qty=2)
    cart = r.json()
    assert cart["mode"] == "marketplace" and len(cart["groups"]) == 2
    volt = next(g for g in cart["groups"] if g["store"]["slug"] == "volt")
    assert volt["deliveryFee"] == "0.00"  # 1999 is above Volt's free-delivery threshold
    loom = next(g for g in cart["groups"] if g["store"]["slug"] == "loom")
    assert loom["deliveryFee"] == "39.00" and loom["codAvailable"] is False
    assert cart["totals"]["subtotal"] == "3797.00"
    # Delivery estimates per seller for the customer's own address.
    est = api.get(f"/api/v1/customer/cart?address={buyer['address'].id}").json()["groups"][0]["deliveryEstimate"]
    assert est["isEstimate"] and est["basis"] == "distance"

    key = str(uuid.uuid4())
    r = checkout(buyer, key=key)
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["checkout"]["number"].startswith("CLK-C-") and len(body["orders"]) == 2
    assert Decimal(body["checkout"]["total"]) == sum(Decimal(o["total"]) for o in body["orders"])
    # Idempotent: the same key returns the same orders, nothing new is charged.
    again = checkout(buyer, key=key)
    assert again.status_code == 200 and {o["id"] for o in again.json()["orders"]} == {o["id"] for o in body["orders"]}
    assert Order.objects.filter(customer=buyer["profile"]).count() == 2
    shop["variants"][("Black", "M")].refresh_from_db()
    assert shop["variants"][("Black", "M")].stock_quantity == 3  # reserved per variant
    shop["buds"].refresh_from_db()
    assert shop["buds"].units_sold == 1
    order = Order.objects.get(store=shop["volt"], customer=buyer["profile"])
    assert order.estimated_delivery_from and order.estimated_delivery_at > order.estimated_delivery_from


def test_variants_are_required_and_unavailable_variants_cannot_be_bought(shop, buyer):
    api = buyer["api"]
    r = add(api, shop["shirt"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "variant_required"
    r = add(api, shop["shirt"], shop["variants"][("White", "L")])
    assert r.status_code == 400 and r.json()["error"]["code"] == "variant_unavailable"
    r = add(api, shop["shirt"], shop["variants"][("Black", "L")], qty=6)
    assert r.json()["error"]["code"] == "insufficient_stock"


def test_shopping_and_food_carts_never_mix_silently(shop, buyer, products):
    api = buyer["api"]
    add(api, shop["buds"])
    r = add(api, products[0])
    assert r.status_code == 409 and r.json()["error"]["code"] == "cart_store_conflict"


def test_cash_on_delivery_respects_seller_and_wallet_failure_creates_nothing(shop, buyer):
    api = buyer["api"]
    add(api, shop["buds"])
    add(api, shop["shirt"], shop["variants"][("Black", "M")])
    r = checkout(buyer, method="cash_on_delivery")
    assert r.status_code == 400 and r.json()["error"]["code"] == "cod_unavailable"
    WalletTransaction.objects.create(customer=buyer["profile"], kind="adjustment", amount=D("-9000"), description="drain")
    r = checkout(buyer, method="wallet")
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_wallet_balance"
    assert not Order.objects.filter(customer=buyer["profile"]).exists()
    shop["buds"].refresh_from_db()
    assert shop["buds"].stock_quantity == 20  # stock reservation rolled back with the failed checkout


def test_deal_price_is_the_same_on_cards_cart_and_order_and_limited_deals_sell_out(shop, buyer):
    now = timezone.now()
    ProductDeal.objects.create(product=shop["buds"], kind="flash", percent_off=20, starts_at=now - timedelta(hours=1),
                               ends_at=now + timedelta(hours=5), quantity_limit=1)
    card = next(c for c in APIClient().get("/api/v1/shop/search", {"category": "audio"}).json()["results"] if c["id"] == str(shop["buds"].id))
    assert card["price"] == "1599.20" and card["referencePrice"] == "2999.00" and card["deal"]["remaining"] == 1
    assert "limited_deal" in card["badges"]
    cart = add(buyer["api"], shop["buds"], qty=2).json()
    assert cart["items"][0]["unitPrice"] == "1599.20"
    r = checkout(buyer)
    assert r.status_code == 409 and r.json()["error"]["code"] == "deal_ended"
    buyer["api"].patch(f"/api/v1/customer/cart/items/{cart['items'][0]['id']}", {"quantity": 1}, format="json")
    assert checkout(buyer).status_code == 201
    assert Order.objects.get(customer=buyer["profile"]).items.get().unit_price == D("1599.20")
    # The deal is used up: the price goes back to the seller's list price.
    assert APIClient().get(f"/api/v1/shop/products/{shop['buds'].id}").json()["price"] == "1999.00"


def test_retail_orders_follow_the_shopping_status_flow_and_cancel_restocks_variants(shop, buyer):
    add(buyer["api"], shop["shirt"], shop["variants"][("Black", "M")], qty=2)
    checkout(buyer)
    order = Order.objects.get(customer=buyer["profile"])
    order = order_services.transition_order(order, OrderStatus.CONFIRMED)
    with pytest.raises(Exception):
        order_services.transition_order(order, OrderStatus.PREPARING)
    order_services.cancel_by_customer(order, user=buyer["user"])
    v = shop["variants"][("Black", "M")]
    v.refresh_from_db()
    assert v.stock_quantity == 5


# --- discovery ----------------------------------------------------------------------------------------------

def test_search_interprets_price_category_colour_and_suggests_corrections(shop):
    api = APIClient()
    d = api.get("/api/v1/shop/search", {"q": "black headphones under 3000"}).json()
    labels = [u["label"] for u in d["interpretation"]["understood"]]
    assert "Under ₹3,000" in labels and "Black" in labels and "Audio" in labels
    assert [r["name"] for r in d["results"]] == []  # the only black headphones cost 4999
    d = api.get("/api/v1/shop/search", {"q": "earbuds under 2500"}).json()
    assert [r["name"] for r in d["results"]] == ["Pulse Wireless Earbuds"]
    d = api.get("/api/v1/shop/search", {"q": "black shirt"}).json()
    assert [r["name"] for r in d["results"]] == ["Oxford Shirt"]  # "shirt" narrows Men's Clothing to shirts
    assert api.get("/api/v1/shop/search", {"q": "hedphones"}).json()["correction"] == "headphones"
    d = api.get("/api/v1/shop/search", {"category": "audio", "sort": "price_asc"}).json()
    assert [r["price"] for r in d["results"]] == ["1499.00", "1999.00", "4999.00"]
    assert {a["name"] for a in d["facets"]["attributes"]} == {"Noise cancellation", "Colour"}
    d = api.get("/api/v1/shop/search", {"category": "audio", "attr_anc": "No"}).json()
    assert [r["name"] for r in d["results"]] == ["Go Speaker"]
    d = api.get("/api/v1/shop/search", {"category": "mens-clothing", "opt_color": "White"}).json()
    assert [r["name"] for r in d["results"]] == ["Oxford Shirt"]
    assert {o["name"] for o in d["facets"]["options"]} == {"Color", "Size"}
    assert api.get("/api/v1/shop/search", {"sort": "nonsense"}).status_code == 400


def test_home_shows_only_sections_with_real_content_and_only_live_campaigns(shop):
    now = timezone.now()
    ShopCampaign.objects.create(title="Live", cta_path="/shopping", starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1))
    ShopCampaign.objects.create(title="Ended", cta_path="/shopping", starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=1))
    ShopCampaign.objects.create(title="Future", cta_path="/shopping", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=3))
    d = APIClient().get("/api/v1/shop/home").json()
    assert [c["title"] for c in d["campaigns"]] == ["Live"]
    ids = [s["id"] for s in d["sections"]]
    assert "best_sellers" not in ids and "trending" not in ids and "deals" not in ids  # nothing sold, viewed or discounted yet
    assert "new_arrivals" in ids
    assert {c["slug"] for c in d["categories"]} == {"electronics", "fashion"}
    assert d["personalized"] is False


def test_feed_cursor_pages_without_duplicates(shop):
    api = APIClient()
    first = api.get("/api/v1/shop/feed").json()
    assert len(first["results"]) == 5 and first["nextCursor"] is None
    assert api.get("/api/v1/shop/feed", {"cursor": "garbage"}).status_code == 400


def test_product_page_has_specs_variants_policies_and_location_based_delivery(shop):
    api = APIClient()
    d = api.get(f"/api/v1/shop/products/{shop['shirt'].id}", {"lat": "12.95", "lng": "77.62"}).json()
    assert d["axes"] == [{"name": "Color", "values": ["Black", "White"]}, {"name": "Size", "values": ["M", "L"]}]
    assert {v["label"]: v["inStock"] for v in d["variants"]}["White · L"] is False
    assert d["policies"]["codAvailable"] is False and d["policies"]["returnDays"] == 7
    assert d["seller"]["isVerified"] is False
    assert d["delivery"]["isEstimate"] and d["specs"] == [{"name": "Fabric", "value": "Cotton", "code": "fabric"}]
    assert api.get(f"/api/v1/shop/products/{shop['shirt'].id}").json()["delivery"] is None  # no location, no estimate


def test_compare_uses_real_attributes_and_refuses_unrelated_products(shop):
    api = APIClient()
    d = api.get("/api/v1/shop/compare", {"ids": f"{shop['buds'].id},{shop['phones'].id}"}).json()
    rows = {r["label"]: r for r in d["rows"]}
    assert rows["Battery life"]["values"] == ["30 hours", "45 hours"] and rows["Battery life"]["differs"]
    assert rows["Noise cancellation"]["differs"] is False
    r = api.get("/api/v1/shop/compare", {"ids": f"{shop['buds'].id},{shop['shirt'].id}"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "compare_incompatible"


def test_visual_search_is_honest_when_no_provider_is_configured(shop):
    from django.core.files.uploadedfile import SimpleUploadedFile

    r = APIClient().post("/api/v1/shop/visual-search", {"image": SimpleUploadedFile("a.jpg", b"x", content_type="image/jpeg")}, format="multipart")
    assert r.status_code == 503 and r.json()["error"]["code"] == "visual_search_unavailable"


def test_trending_and_best_sellers_come_from_real_orders(shop, buyer):
    for _ in range(3):
        add(buyer["api"], shop["speaker"])
        checkout(buyer)
    d = APIClient().get("/api/v1/shop/search", {"category": "audio", "sort": "popular"}).json()
    top = d["results"][0]
    assert top["name"] == "Go Speaker" and "best_seller" in top["badges"] and "trending" in top["badges"]


# --- reviews, returns -----------------------------------------------------------------------------------------

def test_only_verified_buyers_review_once_and_ratings_follow_published_reviews(shop, buyer):
    api = buyer["api"]
    url = f"/api/v1/customer/shop/products/{shop['buds'].id}/review"
    assert api.post(url, {"rating": 5}, format="json").status_code == 403
    add(api, shop["buds"])
    checkout(buyer)
    deliver(Order.objects.get(customer=buyer["profile"]))
    assert APIClient().get(f"/api/v1/shop/products/{shop['buds'].id}").json()["canReview"] is False  # anonymous
    assert api.get(f"/api/v1/shop/products/{shop['buds'].id}").json()["canReview"] is True
    r = api.post(url, {"rating": 4, "title": "Good", "body": "Nice sound"}, format="json")
    assert r.status_code == 201 and r.json()["verifiedPurchase"] is True
    assert api.post(url, {"rating": 5}, format="json").status_code == 409
    shop["buds"].refresh_from_db()
    assert (shop["buds"].rating_average, shop["buds"].rating_count) == (D("4.0"), 1)
    api.patch(url, {"rating": 2}, format="json")
    shop["buds"].refresh_from_db()
    assert shop["buds"].rating_average == D("2.0")
    from apps.shop.reviews import recompute

    ProductReview.objects.update(status="hidden")
    recompute(shop["buds"].id)
    shop["buds"].refresh_from_db()
    assert shop["buds"].rating_count == 0
    assert APIClient().get(f"/api/v1/shop/products/{shop['buds'].id}/reviews").json()["count"] == 0
    assert api.delete(url).status_code == 204


def test_returns_within_window_refund_the_paid_share_once(shop, buyer):
    api = buyer["api"]
    add(api, shop["shirt"], shop["variants"][("Black", "M")], qty=2)
    checkout(buyer)
    order = Order.objects.get(customer=buyer["profile"])
    item = order.items.get()
    url = f"/api/v1/customer/orders/{order.id}/items/{item.id}/return"
    body = {"kind": "return", "reason": "size_fit", "quantity": 1}
    assert api.post(url, body, format="json").json()["error"]["code"] == "return_not_allowed"  # not delivered yet
    deliver(order)
    other = APIClient()
    other.force_authenticate(make_customer("other@example.com"))
    assert other.post(url, body, format="json").status_code == 404
    r = api.post(url, body, format="json")
    assert r.status_code == 201
    line = next(i for i in r.json()["items"] if i["id"] == str(item.id))
    assert line["returns"][0]["status"] == "requested" and line["canReturn"] is False
    assert api.post(url, body, format="json").status_code == 409  # one request per item
    before = sum(t.amount for t in WalletTransaction.objects.filter(customer=buyer["profile"]))
    ret = resolve(ReturnRequest.objects.get(), approve=True)
    assert ret.status == "refunded" and ret.refund_amount == D("943.95")  # 899 + 5% tax share
    after = sum(t.amount for t in WalletTransaction.objects.filter(customer=buyer["profile"]))
    assert after - before == D("943.95")
    with pytest.raises(Exception):
        resolve(ret, approve=True)
    order.delivered_at = timezone.now() - timedelta(days=8)
    order.save(update_fields=["delivered_at"])
    ReturnRequest.objects.all().delete()
    assert api.post(url, body, format="json").json()["error"]["code"] == "return_not_allowed"  # window closed


def test_buddy_shops_with_the_shopping_search(shop, buyer):
    r = buyer["api"].post("/api/v1/customer/assistant/messages", {"messages": [{"role": "user", "content": "earbuds under 2500"}]}, format="json")
    data = r.json()
    assert r.status_code == 200
    assert [c["product"]["name"] for c in data["cards"]] == ["Pulse Wireless Earbuds"]
    assert data["actions"][0]["path"].startswith("/shopping/search?q=")
