import uuid
from decimal import Decimal

import pytest

from apps.orders.models import Order, OrderStatus
from apps.orders.services import transition_order
from apps.payments.models import Payment
from conftest import make_store

pytestmark = pytest.mark.django_db


def add(api, product, qty=1):
    return api.post("/api/v1/customer/cart/items", {"productId": str(product.id), "quantity": qty})


def place(api, address, key=None):
    return api.post(
        "/api/v1/customer/orders",
        {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(key or uuid.uuid4())},
    )


# --- cart -------------------------------------------------------------------

def test_cart_add_merges_quantities_and_computes_totals(auth_api, products):
    add(auth_api, products[0], 1)
    r = add(auth_api, products[0], 2)
    assert r.status_code == 201
    cart = r.json()
    assert cart["itemCount"] == 3
    assert cart["totals"] == {"subtotal": "360.00", "deliveryFee": "30.00", "tax": "18.00", "discount": "0.00", "total": "408.00"}


def test_cart_rejects_unavailable_product_and_invalid_quantity(auth_api, products):
    assert add(auth_api, products[2]).json()["error"]["code"] == "product_unavailable"
    assert add(auth_api, products[0], 0).status_code == 400
    assert add(auth_api, products[0], 51).status_code == 400


def test_cart_single_store_conflict(auth_api, products):
    from apps.catalog.models import Product

    other = make_store("Other Place")
    foreign = Product.objects.create(store=other, name="Pho", price=Decimal("200"))
    add(auth_api, products[0])
    r = add(auth_api, foreign)
    assert r.status_code == 409 and r.json()["error"]["code"] == "cart_store_conflict"
    auth_api.delete("/api/v1/customer/cart")
    assert add(auth_api, foreign).status_code == 201


def test_cart_items_isolated_between_customers(api, customer, other_customer, products):
    api.force_authenticate(customer)
    item_id = add(api, products[0]).json()["items"][0]["id"]
    api.force_authenticate(other_customer)
    assert api.patch(f"/api/v1/customer/cart/items/{item_id}", {"quantity": 5}).status_code == 404
    assert api.delete(f"/api/v1/customer/cart/items/{item_id}").status_code == 404


def test_cart_requires_auth(api):
    assert api.get("/api/v1/customer/cart").status_code == 401


# --- order placement ---------------------------------------------------------

def test_place_order_happy_path(auth_api, products, address):
    add(auth_api, products[0], 1)
    add(auth_api, products[1], 2)
    r = place(auth_api, address)
    assert r.status_code == 201, r.json()
    order = r.json()
    assert order["status"] == "placed" and order["number"].startswith("CLK-")
    assert order["subtotal"] == "200.00" and order["total"] == "240.00"
    assert order["deliveryAddress"]["line1"] == "12 MG Road"
    assert [i["productName"] for i in order["items"]] == ["Dal", "Naan"]
    assert order["payments"][0]["method"] == "cash_on_delivery" and order["payments"][0]["status"] == "pending"
    assert order["canCancel"] is True
    assert auth_api.get("/api/v1/customer/cart").json()["items"] == []


def test_place_order_is_idempotent(auth_api, products, address):
    add(auth_api, products[0], 1)
    key = uuid.uuid4()
    first = place(auth_api, address, key)
    second = place(auth_api, address, key)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert Order.objects.count() == 1


def test_place_order_failures(auth_api, store, products, address, other_customer):
    assert place(auth_api, address).json()["error"]["code"] == "cart_empty"

    add(auth_api, products[1], 1)  # 40 < min order 100
    assert place(auth_api, address).json()["error"]["code"] == "below_minimum_order"

    add(auth_api, products[0], 1)
    from apps.customers.models import Address

    foreign = Address.objects.create(
        customer=other_customer.customer_profile, recipient_name="R", phone="9999999", line1="x", city="y", postal_code="1"
    )
    assert place(auth_api, foreign).json()["error"]["code"] == "invalid_address"

    products[0].is_available = False
    products[0].save()
    r = place(auth_api, address)
    assert r.status_code == 409 and r.json()["error"]["details"]["items"] == ["Dal"]
    products[0].is_available = True
    products[0].save()

    store.is_accepting_orders = False
    store.save()
    assert place(auth_api, address).json()["error"]["code"] == "store_closed"
    assert Order.objects.count() == 0


def test_place_order_recomputes_prices_server_side(auth_api, products, address):
    add(auth_api, products[0], 1)
    products[0].price = Decimal("150.00")
    products[0].save()
    assert place(auth_api, address).json()["subtotal"] == "150.00"


# --- history, detail, cancellation --------------------------------------------

def test_order_history_and_isolation(api, customer, other_customer, products, address):
    api.force_authenticate(customer)
    add(api, products[0])
    order_id = place(api, address).json()["id"]
    history = api.get("/api/v1/customer/orders").json()
    assert history["count"] == 1 and history["results"][0]["itemCount"] == 1

    api.force_authenticate(other_customer)
    assert api.get("/api/v1/customer/orders").json()["count"] == 0
    assert api.get(f"/api/v1/customer/orders/{order_id}").status_code == 404
    assert api.post(f"/api/v1/customer/orders/{order_id}/cancel").status_code == 404


def test_customer_cancel_rules(auth_api, products, address):
    add(auth_api, products[0])
    order_id = place(auth_api, address).json()["id"]
    r = auth_api.post(f"/api/v1/customer/orders/{order_id}/cancel", {"reason": "Changed my mind"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert Payment.objects.get().status == Payment.Status.CANCELLED
    again = auth_api.post(f"/api/v1/customer/orders/{order_id}/cancel")
    assert again.status_code == 409 and again.json()["error"]["code"] == "order_not_cancellable"


def test_status_machine_rejects_illegal_transitions(auth_api, products, address):
    add(auth_api, products[0])
    order = Order.objects.get(pk=place(auth_api, address).json()["id"])
    with pytest.raises(Exception):
        transition_order(order, OrderStatus.DELIVERED)
    for s in [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
        order = transition_order(order, s)
    assert order.delivered_at is not None
    assert [e["toStatus"] for e in auth_api.get(f"/api/v1/customer/orders/{order.id}").json()["events"]][-1] == "delivered"
