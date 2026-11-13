"""Food flow: customisation pricing, offers at checkout, order snapshots, reviews, discovery filters, recommendations."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import MenuCategory, Product, ProductOption, ProductOptionGroup
from apps.orders.models import Order, OrderStatus
from apps.orders.services import transition_order
from apps.stores.models import StoreCategory, StoreOffer, StoreType
from conftest import make_store

pytestmark = pytest.mark.django_db


@pytest.fixture
def pizza(store):
    cat = MenuCategory.objects.create(store=store, name="Pizza")
    p = Product.objects.create(store=store, category=cat, name="Margherita", price=Decimal("200.00"))
    size = ProductOptionGroup.objects.create(product=p, name="Size", min_select=1, max_select=1)
    extras = ProductOptionGroup.objects.create(product=p, name="Extras", min_select=0, max_select=2)
    opts = {
        "regular": ProductOption.objects.create(group=size, name="Regular", price_delta=Decimal("0")),
        "large": ProductOption.objects.create(group=size, name="Large", price_delta=Decimal("150")),
        "cheese": ProductOption.objects.create(group=extras, name="Cheese", price_delta=Decimal("50")),
        "olives": ProductOption.objects.create(group=extras, name="Olives", price_delta=Decimal("30")),
        "soldout": ProductOption.objects.create(group=extras, name="Truffle", price_delta=Decimal("90"), is_available=False),
    }
    return p, opts


def add(api, product, *option_keys, opts=None, qty=1):
    ids = [str(opts[k].id) for k in option_keys]
    return api.post("/api/v1/customer/cart/items", {"productId": str(product.id), "quantity": qty, "optionIds": ids}, format="json")


def place(api, address, key=None):
    return api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery",
                                                "idempotencyKey": str(key or uuid.uuid4())}, format="json")


def test_options_are_validated_and_priced_server_side(auth_api, pizza):
    p, o = pizza
    assert add(auth_api, p, opts=o).json()["error"]["code"] == "option_required"  # size is required
    assert add(auth_api, p, "regular", "large", opts=o).json()["error"]["code"] == "option_limit"
    assert add(auth_api, p, "regular", "soldout", opts=o).json()["error"]["code"] == "option_unavailable"
    r = add(auth_api, p, "large", "cheese", opts=o, qty=2)
    assert r.status_code == 201
    line = r.json()["items"][0]
    assert line["unitPrice"] == "400.00" and line["lineTotal"] == "800.00"
    assert {x["name"] for x in line["options"]} == {"Large", "Cheese"}
    # A different combination is a separate line; the same one merges.
    add(auth_api, p, "regular", opts=o)
    cart = add(auth_api, p, "cheese", "large", opts=o).json()
    assert len(cart["items"]) == 2 and cart["items"][0]["quantity"] == 3
    assert cart["totals"]["subtotal"] == "1400.00"


def test_offers_apply_only_when_they_really_apply(auth_api, store, pizza):
    p, o = pizza
    pct = StoreOffer.objects.create(store=store, title="20% off up to ₹100", discount_type="percent", discount_value=20, max_discount=100)
    big = StoreOffer.objects.create(store=store, title="₹200 off over ₹1,499", discount_type="flat", discount_value=200, min_order_amount=1499)
    shown = StoreOffer.objects.create(store=store, title="Buy 1 get 1", discount_type="")
    ended = StoreOffer.objects.create(store=store, title="Ended", discount_type="flat", discount_value=10, ends_at=timezone.now() - timedelta(days=1))
    other = StoreOffer.objects.create(store=make_store("Elsewhere"), title="Other", discount_type="flat", discount_value=10)
    add(auth_api, p, "regular", opts=o)  # subtotal 200

    cart = auth_api.get("/api/v1/customer/cart").json()
    listed = {x["title"]: x for x in cart["offers"]}
    assert set(listed) == {"20% off up to ₹100", "₹200 off over ₹1,499"}  # display-only, ended and other-store offers aren't offered
    assert listed["20% off up to ₹100"]["problem"] is None and listed["20% off up to ₹100"]["saving"] == "40.00"
    assert "more to use this offer" in listed["₹200 off over ₹1,499"]["problem"]

    for bad in (big, shown, ended, other):
        r = auth_api.post("/api/v1/customer/cart/offer", {"offerId": str(bad.id)}, format="json")
        assert r.status_code == 400 and r.json()["error"]["code"] == "offer_not_applicable"
    r = auth_api.post("/api/v1/customer/cart/offer", {"offerId": str(pct.id)}, format="json")
    assert r.status_code == 200
    t = r.json()["totals"]
    assert (t["subtotal"], t["discount"]) == ("200.00", "40.00")
    assert Decimal(t["total"]) == Decimal(t["subtotal"]) + Decimal(t["deliveryFee"]) + Decimal(t["tax"]) - Decimal("40.00")
    assert auth_api.delete("/api/v1/customer/cart/offer").json()["totals"]["discount"] == "0.00"


def test_order_snapshots_options_and_offer_and_rejects_a_lapsed_offer(auth_api, store, pizza, address):
    p, o = pizza
    offer = StoreOffer.objects.create(store=store, title="20% off up to ₹100", discount_type="percent", discount_value=20, max_discount=100)
    add(auth_api, p, "large", "olives", opts=o)  # 380
    auth_api.post("/api/v1/customer/cart/offer", {"offerId": str(offer.id)}, format="json")

    offer.ends_at = timezone.now() - timedelta(minutes=1)
    offer.save()
    assert place(auth_api, address).json()["error"]["code"] == "offer_not_applicable"  # never silently dropped

    offer.ends_at = None
    offer.save()
    r = place(auth_api, address)
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["discount"] == "76.00" and body["offerTitle"] == "20% off up to ₹100"
    item = body["items"][0]
    assert item["optionsSummary"] == "Large · Olives" and item["unitPrice"] == "380.00"
    assert Decimal(body["total"]) == Decimal(body["subtotal"]) + Decimal(body["deliveryFee"]) + Decimal(body["tax"]) - Decimal("76.00")
    # Reorder restores the same choices at today's prices.
    reorder = auth_api.post(f"/api/v1/customer/orders/{body['id']}/reorder").json()
    assert {x["name"] for x in reorder["cart"]["items"][0]["options"]} == {"Large", "Olives"}


def test_reviews_only_for_delivered_orders_once_and_update_store_rating(auth_api, store, products, address, customer):
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1}, format="json")
    order_id = place(auth_api, address).json()["id"]
    url = f"/api/v1/customer/orders/{order_id}/review"
    assert auth_api.post(url, {"rating": 5}, format="json").json()["error"]["code"] == "review_not_allowed"
    order = Order.objects.get(pk=order_id)
    for s in (OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED):
        transition_order(order, s)
    store.rating_average, store.rating_count = Decimal("4.0"), 3
    store.save()
    assert auth_api.post(url, {"rating": 6}, format="json").status_code == 400
    r = auth_api.post(url, {"rating": 5, "comment": "Hot and on time"}, format="json")
    assert r.status_code == 201 and r.json()["review"]["rating"] == 5 and r.json()["canReview"] is False
    store.refresh_from_db()
    assert (store.rating_average, store.rating_count) == (Decimal("4.3"), 4)
    assert auth_api.post(url, {"rating": 4}, format="json").json()["error"]["code"] == "review_exists"


def test_discovery_filters_and_sorts(api):
    veg = make_store("Green Leaf", rating_average=Decimal("4.6"), price_level=1, delivery_time_min=15)
    mixed = make_store("Grill House", rating_average=Decimal("3.9"), price_level=3, delivery_time_min=35)
    cat = MenuCategory.objects.create(store=mixed, name="Mains")
    Product.objects.create(store=mixed, category=cat, name="Kebab", price=Decimal("200"), dietary="non_veg")
    StoreOffer.objects.create(store=mixed, title="10% off", discount_type="percent", discount_value=10)
    names = lambda q: [s["name"] for s in api.get(f"/api/v1/stores?type=restaurant&{q}").json()["results"]]  # noqa: E731
    assert names("veg=true") == ["Green Leaf"]
    assert names("min_rating=4") == ["Green Leaf"]
    assert names("offers=true") == ["Grill House"]
    assert names("max_price=2") == ["Green Leaf"]
    assert names("sort=eta")[:2] == ["Green Leaf", "Grill House"]
    assert names("sort=price_high")[0] == "Grill House"
    assert set(names("min_rating=abc")) >= {"Green Leaf", "Grill House"}  # invalid filters are ignored, not guessed


def test_recommendations_follow_order_history_and_say_why(auth_api, store, products, address):
    biryani = StoreCategory.objects.create(store_type=StoreType.RESTAURANT, name="Biryani", slug="biryani")
    store.categories.add(biryani)
    other = make_store("Biryani Bros", rating_average=Decimal("4.8"), rating_count=10)
    other.categories.add(biryani)
    make_store("Top Rated Cafe", rating_average=Decimal("4.9"), rating_count=50)
    assert auth_api.get("/api/v1/customer/recommendations/stores?type=restaurant").json()["results"][0]["reason"] == "Highly rated on Click."
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2}, format="json")
    place(auth_api, address)
    recs = auth_api.get("/api/v1/customer/recommendations/stores?type=restaurant").json()["results"]
    assert recs[0]["store"]["name"] == "Biryani Bros" and recs[0]["reason"] == "Because you ordered Biryani"
    assert any(r["reason"] == "Because you ordered Biryani here before" for r in recs)


def test_recommendations_require_sign_in(api):
    assert api.get("/api/v1/customer/recommendations/stores").status_code == 401
