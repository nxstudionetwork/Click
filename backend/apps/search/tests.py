import uuid

import pytest

from apps.search.models import SearchHistory

pytestmark = pytest.mark.django_db


def place(api, address, products):
    api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    return api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())}).json()


def test_search_groups_suggests_and_finds_only_your_own_ids(auth_api, api, customer, other_customer, address, products):
    r = auth_api.get("/api/v1/search/global", {"q": products[0].name[:5]}).json()
    assert r["count"] >= 1 and r["groups"] and all({"title", "link", "group"} <= set(h) for g in r["groups"] for h in g["results"])
    order = place(auth_api, address, products)
    mine = auth_api.get("/api/v1/search/global", {"q": order["number"]}).json()["mine"]
    assert mine and mine[0]["link"] == f"/orders/{order['id']}"
    from rest_framework.test import APIClient

    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get("/api/v1/search/global", {"q": order["number"]}).json()["mine"] == []  # never another customer's records
    assert APIClient().get("/api/v1/search/global", {"q": order["number"]}).json()["mine"] == []
    s = auth_api.get("/api/v1/search/suggest", {"q": products[0].name[:4]}).json()
    assert s["suggestions"]


def test_recent_searches_are_private_and_clearable(auth_api, customer, other_customer):
    for q in ["paneer", "paneer", "headphones"]:
        auth_api.get("/api/v1/search/global", {"q": q})
    recent = auth_api.get("/api/v1/customer/search/recent").json()["results"]
    assert [x["query"] for x in recent] == ["headphones", "paneer"]  # newest first, repeats collapsed
    assert SearchHistory.objects.filter(customer=other_customer.customer_profile).count() == 0
    auth_api.delete(f"/api/v1/customer/search/recent/{recent[1]['id']}")
    assert [x["query"] for x in auth_api.get("/api/v1/customer/search/recent").json()["results"]] == ["headphones"]
    auth_api.delete("/api/v1/customer/search/recent")
    assert auth_api.get("/api/v1/customer/search/recent").json()["results"] == []


def test_cart_price_change_must_be_acknowledged(auth_api, products):
    from apps.catalog.models import Product

    cart = auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1}).json()
    item = cart["items"][0]
    Product.objects.filter(pk=products[0].pk).update(price=products[0].price + 10)
    cart = auth_api.get("/api/v1/customer/cart").json()
    assert cart["items"][0]["priceChange"]["to"] == f"{products[0].price + 10:.2f}"
    cart = auth_api.patch(f"/api/v1/customer/cart/items/{item['id']}", {"acknowledgePrice": True}, format="json").json()
    assert cart["items"][0]["priceChange"] is None and cart["items"][0]["quantity"] == 1
