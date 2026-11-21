import uuid
from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.orders.models import OrderStatus
from apps.stores.models import Store, StoreType
from conftest import make_store

pytestmark = pytest.mark.django_db


def place(api, address):
    return api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())})


def test_product_detail_with_store_discount_and_related(api, store, products):
    products[0].compare_at_price = Decimal("150.00")
    products[0].save()
    r = api.get(f"/api/v1/products/{products[0].id}")
    assert r.status_code == 200
    body = r.json()
    assert body["discountPercent"] == 20 and body["store"]["slug"] == store.slug
    assert {p["name"] for p in body["related"]} == {"Naan", "Sold out"}
    assert "stockQuantity" not in body  # exact stock is never exposed


def test_product_detail_hidden_for_inactive_store_or_product(api, store, products):
    products[1].is_active = False
    products[1].save()
    assert api.get(f"/api/v1/products/{products[1].id}").status_code == 404
    store.status = Store.Status.SUSPENDED
    store.save()
    assert api.get(f"/api/v1/products/{products[0].id}").status_code == 404


def test_search_across_stores_and_products_with_scopes(api, products):
    shop = make_store("Fresh Mart", store_type=StoreType.GROCERY)
    Product.objects.create(store=shop, name="Dal Masala", brand="MDH", price=Decimal("60"))
    r = api.get("/api/v1/search?q=dal").json()
    assert {p["name"] for p in r["products"]} == {"Dal", "Dal Masala"}
    grocery = api.get("/api/v1/search?q=dal&scope=grocery").json()
    assert [p["name"] for p in grocery["products"]] == ["Dal Masala"]
    assert api.get("/api/v1/search?q=fresh").json()["stores"][0]["name"] == "Fresh Mart"
    assert api.get("/api/v1/search?q=d").json() == {"query": "d", "stores": [], "products": [], "events": []}
    assert api.get("/api/v1/search?q=dal&scope=nope").status_code == 400


def test_inventory_enforced_in_cart_and_order_and_restocked_on_cancel(auth_api, products, address):
    p = products[0]
    p.stock_quantity = 2
    p.save()
    r = auth_api.post("/api/v1/customer/cart/items", {"productId": str(p.id), "quantity": 3})
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_stock"
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(p.id), "quantity": 2})
    order = place(auth_api, address).json()
    p.refresh_from_db()
    assert p.stock_quantity == 0
    assert auth_api.get(f"/api/v1/products/{p.id}").json()["isAvailable"] is False
    auth_api.post(f"/api/v1/customer/orders/{order['id']}/cancel")
    p.refresh_from_db()
    assert p.stock_quantity == 2


def test_stock_sold_out_between_cart_and_checkout(auth_api, products, address):
    p = products[0]
    p.stock_quantity = 5
    p.save()
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(p.id), "quantity": 3})
    Product.objects.filter(pk=p.pk).update(stock_quantity=1)  # another customer bought them
    r = place(auth_api, address)
    assert r.status_code == 409 and r.json()["error"]["code"] == "items_unavailable"


def test_offers_feed_lists_active_offers_with_store(api, store):
    from apps.stores.models import StoreOffer

    StoreOffer.objects.create(store=store, title="10% off")
    StoreOffer.objects.create(store=store, title="Old", is_active=False)
    body = api.get("/api/v1/offers").json()
    assert [o["title"] for o in body["results"]] == ["10% off"]
    assert body["results"][0]["store"]["slug"] == store.slug


def test_order_type_filter_and_reorder(auth_api, products, address):
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[1].id), "quantity": 1})
    order = place(auth_api, address).json()
    assert auth_api.get("/api/v1/customer/orders?type=restaurant").json()["count"] == 1
    assert auth_api.get("/api/v1/customer/orders?type=grocery").json()["count"] == 0
    summary = auth_api.get("/api/v1/customer/orders").json()["results"][0]
    assert summary["paymentStatus"] == "pending" and summary["itemNames"] == ["Dal", "Naan"]

    products[1].is_available = False
    products[1].save()
    r = auth_api.post(f"/api/v1/customer/orders/{order['id']}/reorder").json()
    assert r["skipped"] == ["Naan"] and r["cart"]["itemCount"] == 2


def test_delivered_order_earns_points_once_and_notifies(auth_api, products, address):
    from apps.orders.models import Order
    from apps.orders.services import transition_order

    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})  # subtotal 240
    order = Order.objects.get(pk=place(auth_api, address).json()["id"])
    for s in [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
        order = transition_order(order, s)
    rewards = auth_api.get("/api/v1/customer/rewards").json()
    assert rewards["balance"] == 24 and rewards["history"][0]["kind"] == "earn"
    assert order.payments.get().status == "captured"  # cash on delivery is collected when the order is delivered
    from apps.rewards.services import award_for_delivered_order

    assert award_for_delivered_order(order) is None  # idempotent
    titles = [n["title"] for n in auth_api.get("/api/v1/customer/notifications").json()["results"]]
    assert "You earned 24 Click. points" in titles and any("Delivered" in t for t in titles)
