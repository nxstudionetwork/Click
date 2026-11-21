import pytest

from apps.notifications.services import notify

pytestmark = pytest.mark.django_db


def test_notifications_list_read_and_isolation(api, customer, other_customer):
    a = notify(customer.customer_profile, "orders", "One", link_path="/orders")
    notify(customer.customer_profile, "offers", "Two")
    notify(other_customer.customer_profile, "orders", "Not yours")
    api.force_authenticate(customer)
    assert api.get("/api/v1/customer/notifications/summary").json()["unread"] == 2
    assert [n["title"] for n in api.get("/api/v1/customer/notifications?category=orders").json()["results"]] == ["One"]
    assert api.post(f"/api/v1/customer/notifications/{a.id}/read").json()["isRead"] is True
    assert api.get("/api/v1/customer/notifications?unread=true").json()["count"] == 1
    assert api.post("/api/v1/customer/notifications/read-all").json() == {"updated": 1}

    api.force_authenticate(other_customer)
    assert api.post(f"/api/v1/customer/notifications/{a.id}/read").status_code == 404
    assert api.get("/api/v1/customer/notifications/summary").json()["unread"] == 1


def test_order_placement_creates_notification(auth_api, products, address):
    import uuid

    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1})
    order = auth_api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())}).json()
    n = auth_api.get("/api/v1/customer/notifications").json()["results"][0]
    assert n["linkPath"] == f"/orders/{order['id']}" and n["category"] == "orders"
