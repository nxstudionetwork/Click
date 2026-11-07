import uuid

import pytest

pytestmark = pytest.mark.django_db


def test_create_ticket_linked_to_own_order(auth_api, products, address):
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    order = auth_api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())}).json()
    r = auth_api.post("/api/v1/customer/support/tickets", {"category": "order", "subject": "Missing naan", "message": "One item missing", "orderId": order["id"]})
    assert r.status_code == 201
    t = r.json()
    assert t["reference"].startswith("SUP-") and t["status"] == "open" and t["orderNumber"] == order["number"]
    assert auth_api.get(f"/api/v1/customer/support/tickets/{t['id']}").status_code == 200


def test_ticket_cannot_reference_other_customers_order_and_is_isolated(api, customer, other_customer, products, address):
    api.force_authenticate(customer)
    api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    order = api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())}).json()
    ticket = api.post("/api/v1/customer/support/tickets", {"category": "other", "subject": "Hi", "message": "Hello"}).json()

    api.force_authenticate(other_customer)
    r = api.post("/api/v1/customer/support/tickets", {"category": "order", "subject": "x", "message": "y", "orderId": order["id"]})
    assert r.status_code == 400 and "orderId" in r.json()["error"]["details"]
    assert api.get(f"/api/v1/customer/support/tickets/{ticket['id']}").status_code == 404
    assert api.get("/api/v1/customer/support/tickets").json()["count"] == 0


def test_ticket_validation(auth_api):
    r = auth_api.post("/api/v1/customer/support/tickets", {"category": "bogus", "subject": "", "message": ""})
    assert r.status_code == 400 and {"category", "subject", "message"} <= set(r.json()["error"]["details"])
