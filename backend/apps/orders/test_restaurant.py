"""Click Partner — Restaurant mode: menu, kitchen operations, kitchen board, order search, offers, insights, isolation."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.orders.restaurant import release_due
from apps.partners.models import Partner, PartnerStore
from apps.partners.test_home import make_partner, order_food, partner_catalog, restaurant  # noqa: F401 (fixtures)
from apps.stores.models import Store, StoreOffer
from conftest import make_store

pytestmark = pytest.mark.django_db
R = "/api/v1/partner/restaurant"


def test_only_restaurant_partners_reach_restaurant_tools(api, restaurant):
    assert api.get(f"{R}/menu").status_code == 401
    _, driver = make_partner("cab-driver", "driver@click.test")
    assert driver.get(f"{R}/menu").json()["error"]["code"] == "not_restaurant"
    _, unlinked = make_partner("restaurant", "nolisting@click.test")
    r = unlinked.get(f"{R}/menu")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_connected"


def test_menu_changes_reach_the_customer_menu(restaurant, store, products, api):
    _, client = restaurant
    menu = client.get(f"{R}/menu").json()
    assert menu["store"]["id"] == str(store.id) and menu["counts"] == {"items": 3, "available": 2, "unavailable": 1, "hidden": 0}

    cat = client.post(f"{R}/menu/categories", {"name": "Desserts"}, format="json").json()
    assert client.post(f"{R}/menu/categories", {"name": "desserts"}, format="json").status_code == 409  # double submit / duplicate

    bad = client.post(f"{R}/menu/items", {"name": "Kulfi", "categoryId": cat["id"], "price": "-5"}, format="json")
    assert bad.status_code == 400 and "price" in bad.json()["error"]["details"]
    item = client.post(f"{R}/menu/items", {
        "name": "Kulfi", "categoryId": cat["id"], "price": "90", "dietary": "veg", "description": "Malai kulfi",
        "optionGroups": [{"name": "Size", "minSelect": 1, "maxSelect": 1,
                          "options": [{"name": "Single", "priceDelta": "0"}, {"name": "Double", "priceDelta": "60"}]}],
    }, format="json")
    assert item.status_code == 201, item.content
    item = item.json()
    assert item["price"] == "90.00" and item["optionGroups"][0]["options"][1]["priceDelta"] == "60.00"
    assert client.post(f"{R}/menu/items", {"name": "KULFI", "categoryId": cat["id"], "price": "90"}, format="json").status_code == 409

    public = api.get(f"/api/v1/stores/{store.slug}/menu").json()["categories"]
    assert "Kulfi" in [p["name"] for c in public for p in c["products"]]

    # Marking unavailable stops customers adding it; hiding the category removes it from the menu.
    assert client.patch(f"{R}/menu/items/{item['id']}", {"isAvailable": False}, format="json").json()["isAvailable"] is False
    customer_api = api
    from apps.users.models import User

    customer_api.force_authenticate(User.objects.create_user("eater@click.test", "S3cure-pass-123", full_name="Asha"))
    assert customer_api.post("/api/v1/customer/cart/items", {"productId": item["id"], "quantity": 1}).status_code >= 400
    client.patch(f"{R}/menu/categories/{cat['id']}", {"isActive": False}, format="json")
    public = api.get(f"/api/v1/stores/{store.slug}/menu").json()["categories"]
    assert "Kulfi" not in [p["name"] for c in public for p in c["products"]]

    # Reorder needs the complete current list (a stale device can't scramble the menu).
    ids = [c["id"] for c in client.get(f"{R}/menu").json()["categories"]]
    assert client.post(f"{R}/menu/categories/order", {"ids": ids[:1]}, format="json").status_code == 409
    assert client.post(f"{R}/menu/categories/order", {"ids": list(reversed(ids))}, format="json").status_code == 200
    assert [c["id"] for c in client.get(f"{R}/menu").json()["categories"]] == list(reversed(ids))
    assert client.delete(f"{R}/menu/categories/{cat['id']}").json()["error"]["code"] == "category_not_empty"


def test_restaurants_never_touch_another_restaurants_menu(restaurant, products):
    other, other_client = make_partner("restaurant", "other@click.test", available=True)
    PartnerStore.objects.create(partner=other, store=make_store("Other Kitchen"))
    assert other_client.patch(f"{R}/menu/items/{products[0].id}", {"price": "1"}, format="json").status_code == 404
    assert Product.objects.get(pk=products[0].pk).price == products[0].price
    assert other_client.get(f"{R}/menu", {"store": str(products[0].store_id)}).status_code == 404


def test_busy_and_temporary_closure_reach_customers_and_end_on_time(restaurant, store, auth_api, products, address):
    partner, client = restaurant
    base = (store.delivery_time_min, store.delivery_time_max)
    ops = client.post(f"{R}/operations", {"action": "busy", "minutes": 20, "forMinutes": 60}, format="json").json()
    assert ops["state"] == "busy" and ops["busyExtraMinutes"] == 20
    store.refresh_from_db()
    assert (store.delivery_time_min, store.delivery_time_max) == (base[0] + 20, base[1] + 20)
    # Choosing busy again replaces it; it never stacks.
    client.post(f"{R}/operations", {"action": "busy", "minutes": 10, "forMinutes": 30}, format="json")
    store.refresh_from_db()
    assert store.delivery_time_min == base[0] + 10

    ops = client.post(f"{R}/operations", {"action": "pause", "forMinutes": 30, "reason": "staff"}, format="json").json()
    assert ops["state"] == "paused" and ops["pauseReason"] == "Short on staff"
    partner.refresh_from_db()
    assert partner.is_available is False
    assert auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1}).status_code >= 400

    # Time passes: both expire; the restaurant reopens on its own and the delivery window is restored.
    Store.objects.filter(pk=store.pk).update(paused_until=timezone.now() - timedelta(seconds=1), busy_until=timezone.now() - timedelta(seconds=1))
    assert auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 1}).status_code == 201
    store.refresh_from_db()
    partner.refresh_from_db()
    assert store.is_accepting_orders and partner.is_available and store.paused_until is None
    assert release_due() == 0  # already released for this store at add-to-cart; the job is harmless to repeat
    store.refresh_from_db()
    assert (store.delivery_time_min, store.delivery_time_max) == base

    assert client.post(f"{R}/operations", {"action": "prep_time", "minutes": 200}, format="json").status_code == 400
    assert client.post(f"{R}/operations", {"action": "prep_time", "minutes": 25}, format="json").json()["prepTimeMinutes"] == 25


def test_kitchen_board_and_order_search(restaurant, auth_api, products, address):
    _, client = restaurant
    first = order_food(auth_api, products, address)
    second = order_food(auth_api, products, address)
    client.post(f"/api/v1/partner/work/order/{first['id']}/accept")
    client.post(f"/api/v1/partner/work/order/{first['id']}/preparing")

    board = {c["key"]: c["items"] for c in client.get(f"{R}/kitchen").json()["columns"]}
    assert [i["ref"] for i in board["new"]] == [second["number"]]
    [prep] = board["preparing"]
    assert prep["ref"] == first["number"] and prep["kitchen"]["readyBy"] and prep["kitchen"]["lines"][0]["quantity"] == 2
    assert [a["key"] for a in prep["actions"]] == ["ready"]

    found = client.get(f"{R}/orders", {"q": first["number"][-6:].lower()}).json()
    assert [i["ref"] for i in found["items"]] == [first["number"]]
    assert client.get(f"{R}/orders", {"status": "new"}).json()["total"] == 1
    assert client.get(f"{R}/orders", {"date": "not-a-date"}).status_code == 400
    _, other = make_partner("restaurant", "other@click.test")
    PartnerStore.objects.create(partner=Partner.objects.get(memberships__user__email="other@click.test"), store=make_store("Other"))
    assert other.get(f"{R}/orders", {"q": first["number"]}).json()["total"] == 0


def test_partner_offers_need_click_approval_before_customers_see_them(restaurant, store, auth_api, products):
    _, client = restaurant
    ends = (timezone.now() + timedelta(days=7)).isoformat()
    assert client.post(f"{R}/offers", {"title": "Too good", "discountType": "percent", "discountValue": 95, "endsAt": ends},
                       format="json").status_code == 400
    assert client.post(f"{R}/offers", {"title": "Flat 100", "discountType": "flat", "discountValue": 100, "minOrderAmount": 150,
                                       "endsAt": ends}, format="json").status_code == 400
    r = client.post(f"{R}/offers", {"title": "20% off lunch", "discountType": "percent", "discountValue": 20, "maxDiscount": 100,
                                    "endsAt": ends}, format="json")
    assert r.status_code == 201 and r.json()["state"] == "pending"
    assert client.post(f"{R}/offers", {"title": "20% OFF LUNCH", "discountType": "percent", "discountValue": 20, "endsAt": ends},
                       format="json").status_code == 409
    offer = StoreOffer.objects.get(pk=r.json()["id"])

    auth_api.post("/api/v1/customer/cart/items", {"productId": str(products[0].id), "quantity": 2})
    assert "20% off lunch" not in [o["title"] for o in auth_api.get("/api/v1/customer/cart").json()["offers"]]
    assert client.post(f"{R}/offers/{offer.id}/pause").status_code == 409  # not approved yet

    from apps.orders.restaurant import review_offer

    review_offer(offer, True)
    assert "20% off lunch" in [o["title"] for o in auth_api.get("/api/v1/customer/cart").json()["offers"]]
    assert client.post(f"{R}/offers/{offer.id}/pause").json()["state"] == "paused"
    assert "20% off lunch" not in [o["title"] for o in auth_api.get("/api/v1/customer/cart").json()["offers"]]


def test_insights_count_only_real_orders(restaurant, auth_api, products, address):
    _, client = restaurant
    empty = client.get(f"{R}/insights").json()
    assert empty["orders"]["total"] == 0 and empty["orders"]["averageValue"] is None and empty["operations"]["averagePrepMinutes"] is None
    order = order_food(auth_api, products, address)
    for action in ("accept", "preparing", "ready"):
        client.post(f"/api/v1/partner/work/order/{order['id']}/{action}")
    rejected = order_food(auth_api, products, address)
    client.post(f"/api/v1/partner/work/order/{rejected['id']}/reject", {"reason": "Out of dal"})
    data = client.get(f"{R}/insights", {"days": "7"}).json()
    assert data["orders"]["total"] == 2 and data["orders"]["cancelled"] == 1 and data["orders"]["rejected"] == 1
    assert data["menu"]["bestSellers"][0] == {"name": "Dal", "quantity": 2, "revenue": "240.00"}
    assert data["operations"]["averagePrepMinutes"] == 0 and data["operations"]["acceptanceRate"] == 50
    assert data["sales"]["today"] == Order.objects.get(pk=order["id"]).total.to_eng_string()
