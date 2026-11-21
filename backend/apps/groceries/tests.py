"""Click. Groceries: multi-store baskets, delivery modes and slots, price/stock changes, reorder, lists, vendor ownership."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.customers.models import Address
from apps.groceries.models import GroceryCategory, GroceryItem, GroceryStoreSettings, StockAlert, StoreHours
from apps.notifications.models import Notification
from apps.orders.models import CheckoutGroup, Order, OrderItem, OrderStatus
from apps.stores.models import StoreType
from conftest import make_customer, make_store

pytestmark = pytest.mark.django_db
HOME = (D("12.971900"), D("77.641200"))  # customer
NEAR = (D("12.975000"), D("77.640000"))  # ~0.4 km
MID = (D("12.950000"), D("77.640000"))   # ~2.4 km


@pytest.fixture
def cats(db):
    return {
        "dairy": GroceryCategory.objects.create(name="Dairy", slug="dairy", section="dairy", synonyms="milk, curd", position=10),
        "rice": GroceryCategory.objects.create(name="Rice & Atta", slug="rice-atta", section="essentials", synonyms="rice, atta", position=20),
    }


@pytest.fixture
def items(cats):
    mk = lambda name, brand, size, unit, c: GroceryItem.objects.create(name=name, brand=brand, size_value=D(size), size_unit=unit, category=cats[c])  # noqa: E731
    return {"milk": mk("Toned Milk", "Meadowfresh", "1", "l", "dairy"), "rice": mk("Basmati Rice", "Golden Harvest", "5", "kg", "rice"),
            "rice_1kg": mk("Basmati Rice", "Golden Harvest", "1", "kg", "rice"), "curd": mk("Fresh Curd", "Meadowfresh", "400", "g", "dairy")}


def grocery_store(name, point, hours=True, **kw):
    s = make_store(name, store_type=StoreType.GROCERY, latitude=point[0], longitude=point[1], delivery_fee=D("10"),
                   min_order_amount=D("0"), **kw)
    GroceryStoreSettings.objects.create(store=s, delivery_radius_km=D("5"), fast_radius_km=D("3"), fast_surcharge=D("15"),
                                        base_km=D("2"), per_km_fee=D("6"), slot_lead_minutes=0, slot_days=2)
    if hours:
        StoreHours.objects.bulk_create([StoreHours(store=s, weekday=d, opens_at=time(0, 0), closes_at=time(23, 59)) for d in range(7)])
    return s


def listing(store, item, price, stock=20, mrp=None):
    return Product.objects.create(store=store, grocery_item=item, name=item.name, brand=item.brand, unit_label=item.size_label,
                                  price=D(price), compare_at_price=D(mrp) if mrp else None, stock_quantity=stock)


@pytest.fixture
def shops(items):
    a, b = grocery_store("Near Mart", NEAR), grocery_store("Mid Kirana", MID)
    return {"a": a, "b": b,
            "a_milk": listing(a, items["milk"], "54"), "a_rice": listing(a, items["rice"], "650", mrp="799"),
            "b_milk": listing(b, items["milk"], "52"), "b_rice": listing(b, items["rice"], "620"),
            "b_rice_1kg": listing(b, items["rice_1kg"], "140"), "b_curd": listing(b, items["curd"], "45")}


@pytest.fixture
def home(customer):
    return Address.objects.create(customer=customer.customer_profile, recipient_name="Asha", phone="+91 98765 43210",
                                  line1="1 Test Road", city="Bengaluru", postal_code="560038", is_default=True,
                                  latitude=HOME[0], longitude=HOME[1])


def add(api, product, qty=1):
    r = api.post("/api/v1/customer/cart/items", {"productId": str(product.id), "quantity": qty}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def checkout(api, home, delivery, key=None, payment="cash_on_delivery"):
    return api.post("/api/v1/customer/groceries/checkout", {
        "addressId": str(home.id), "paymentMethod": payment, "idempotencyKey": str(key or uuid.uuid4()),
        "substitution": "similar", "delivery": delivery}, format="json")


def test_multi_store_basket_becomes_one_order_per_store_with_its_own_delivery(auth_api, shops, home):
    add(auth_api, shops["a_milk"], 2)
    cart = add(auth_api, shops["b_rice"], 1)
    assert cart["mode"] == "basket" and len(cart["groups"]) == 2

    basket = auth_api.get(f"/api/v1/customer/groceries/basket?address={home.id}").json()["grocery"]
    by_store = {s["storeId"]: s for s in basket["stores"]}
    near, mid = by_store[str(shops["a"].id)], by_store[str(shops["b"].id)]
    assert near["choice"]["mode"] == "fast" and near["distanceKm"] < 1
    fast_mid = next(o for o in mid["options"] if o["mode"] == "fast")
    import math

    extra = math.ceil((mid["distanceKm"] - 2) * 6)  # per-km fee beyond the 2 km base, rounded up to the rupee
    assert fast_mid["available"] and D(fast_mid["fee"]) == D("10") + extra + D("15")
    slot = next(o for o in mid["options"] if o["mode"] == "scheduled")["slots"][0]

    r = checkout(auth_api, home, {str(shops["a"].id): {"mode": "fast"}, str(shops["b"].id): {"mode": "scheduled", "slotStart": slot["start"]}})
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["checkout"] and len(body["orders"]) == 2
    orders = {o.store_id: o for o in Order.objects.filter(customer__user__email="asha@example.com")}
    a_order, b_order = orders[shops["a"].id], orders[shops["b"].id]
    assert a_order.grocery.delivery_mode == "fast" and a_order.delivery_fee == D("25.00")  # base 10 + fast 15, within 2 km
    assert b_order.grocery.delivery_mode == "scheduled" and b_order.grocery.slot_start == datetime.fromisoformat(slot["start"])
    assert b_order.grocery.substitution == "similar" and b_order.estimated_delivery_at == b_order.grocery.slot_end
    assert CheckoutGroup.objects.get().total == a_order.total + b_order.total
    shops["a_milk"].refresh_from_db()
    assert shops["a_milk"].stock_quantity == 18  # inventory belongs to the store that sold it
    detail = auth_api.get(f"/api/v1/customer/orders/{b_order.id}").json()
    assert detail["grocery"]["deliveryModeLabel"] == "Scheduled delivery" and detail["grocery"]["tracking"] == "status_only"
    # A retry with the same key returns the same orders.
    assert auth_api.get("/api/v1/customer/cart").json()["items"] == []


def test_delivery_choice_and_slot_are_validated_server_side(auth_api, shops, home):
    add(auth_api, shops["b_rice"])
    r = checkout(auth_api, home, {})
    assert r.status_code == 409 and r.json()["error"]["code"] == "delivery_unavailable"
    r = checkout(auth_api, home, {str(shops["b"].id): {"mode": "scheduled", "slotStart": "2030-01-01T09:00:00+05:30"}})
    assert r.status_code == 409 and "slot" in r.json()["error"]["message"]
    # The generic checkout can't place a grocery basket without delivery choices.
    r = auth_api.post("/api/v1/customer/checkout", {"addressId": str(home.id), "paymentMethod": "cash_on_delivery",
                                                     "idempotencyKey": str(uuid.uuid4())}, format="json")
    assert r.status_code == 409
    assert not Order.objects.exists()


def test_full_slot_is_not_offered(auth_api, shops, home):
    cfg = shops["b"].grocery
    cfg.slot_capacity = 1
    cfg.save()
    add(auth_api, shops["b_rice"])
    mid = auth_api.get(f"/api/v1/customer/groceries/basket?address={home.id}").json()["grocery"]["stores"][0]
    first = next(o for o in mid["options"] if o["mode"] == "scheduled")["slots"][0]
    assert checkout(auth_api, home, {str(shops["b"].id): {"mode": "scheduled", "slotStart": first["start"]}}).status_code == 201
    add(auth_api, shops["b_rice"])
    mid = auth_api.get(f"/api/v1/customer/groceries/basket?address={home.id}").json()["grocery"]["stores"][0]
    assert first["start"] not in [s["start"] for s in next(o for o in mid["options"] if o["mode"] == "scheduled")["slots"]]


def test_price_change_must_be_acknowledged_before_checkout(auth_api, shops, home):
    add(auth_api, shops["a_milk"])
    Product.objects.filter(pk=shops["a_milk"].pk).update(price=D("58.00"))
    basket = auth_api.get(f"/api/v1/customer/groceries/basket?address={home.id}").json()
    assert basket["cart"]["items"][0]["priceChange"] == {"from": "54.00", "to": "58.00"}
    assert basket["grocery"]["ready"] is False
    r = checkout(auth_api, home, {str(shops["a"].id): {"mode": "fast"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "price_changed"
    assert r.json()["error"]["details"]["items"][0]["to"] == "58.00"
    auth_api.post("/api/v1/customer/groceries/basket/acknowledge-prices", {}, format="json")
    r = checkout(auth_api, home, {str(shops["a"].id): {"mode": "fast"}})
    assert r.status_code == 201
    assert OrderItem.objects.get().unit_price == D("58.00")


def test_stock_change_blocks_checkout_and_offers_same_item_elsewhere(auth_api, shops, home):
    add(auth_api, shops["a_milk"])
    Product.objects.filter(pk=shops["a_milk"].pk).update(stock_quantity=0)
    g = auth_api.get(f"/api/v1/customer/groceries/basket?address={home.id}").json()["grocery"]
    gone = g["unavailable"][0]
    assert gone["reason"] == "Out of stock" and [a["store"]["name"] for a in gone["alternatives"]] == ["Mid Kirana"]
    r = checkout(auth_api, home, {str(shops["a"].id): {"mode": "fast"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "items_unavailable"
    assert not Order.objects.exists()


def test_closed_store_offers_only_scheduled_and_unavailable_store_blocks(auth_api, shops, home):
    StoreHours.objects.filter(store=shops["a"]).delete()
    today = timezone.localtime(timezone.now()).date()
    later = (timezone.localtime(timezone.now()) + timedelta(days=1)).date()
    StoreHours.objects.create(store=shops["a"], weekday=later.weekday(), opens_at=time(9), closes_at=time(10))
    if today.weekday() != later.weekday():
        page = auth_api.get(f"/api/v1/groceries/stores/{shops['a'].slug}?address={home.id}").json()
        assert page["status"]["state"] == "closed" and page["status"]["detail"].startswith("Opens")
        modes = {o["mode"]: o for o in page["deliveryOptions"]}
        assert not modes["fast"]["available"] and "closed" in modes["fast"]["reason"].lower()
    shops["b"].is_accepting_orders = False
    shops["b"].save()
    page = auth_api.get(f"/api/v1/groceries/stores/{shops['b'].slug}?address={home.id}").json()
    assert page["status"]["label"] == "Temporarily unavailable"
    r = auth_api.post("/api/v1/customer/cart/items", {"productId": str(shops["b_rice"].id)}, format="json")
    assert r.status_code == 400


def test_outside_delivery_area_is_not_claimed(auth_api, shops, home, items):
    far = grocery_store("Far Mart", (D("13.100000"), D("77.590000")))
    listing(far, items["milk"], "50")
    home_page = auth_api.get(f"/api/v1/groceries/home?address={home.id}").json()
    assert "Far Mart" not in [s["name"] for s in home_page["stores"]]
    page = auth_api.get(f"/api/v1/groceries/stores/{far.slug}?address={home.id}").json()
    assert page["deliverable"] is False and "delivery area" in page["reason"]


def test_minimum_order_is_shown_and_enforced(auth_api, shops, home):
    shops["b"].min_order_amount = D("100")
    shops["b"].save()
    add(auth_api, shops["b_curd"])
    g = auth_api.get(f"/api/v1/customer/groceries/basket?address={home.id}").json()["grocery"]
    assert g["stores"][0]["minimumRemaining"] == "55.00" and g["ready"] is False
    r = checkout(auth_api, home, {str(shops["b"].id): {"mode": "fast"}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "below_minimum_order"


def _delivered(customer, store, lines, days_ago):
    o = Order.objects.create(customer=customer.customer_profile, store=store, status=OrderStatus.DELIVERED, delivery_address={},
                             subtotal=D("100"), delivery_fee=D("0"), tax=D("0"), total=D("100"), idempotency_key=uuid.uuid4(),
                             delivered_at=timezone.now() - timedelta(days=days_ago))
    for p, price in lines:
        OrderItem.objects.create(order=o, product=p, product_name=p.name, unit_price=D(price), quantity=1, line_total=D(price))
    return o


def test_buy_again_running_low_and_reorder_revalidate(auth_api, customer, shops, home):
    for d in (16, 11, 6):
        last = _delivered(customer, shops["a"], [(shops["a_milk"], "50"), (shops["a_rice"], "650")], d)
    data = auth_api.get(f"/api/v1/customer/groceries/buy-again?address={home.id}").json()
    milk = next(r for r in data["results"] if r["listing"]["name"] == "Toned Milk")
    assert milk["times"] == 3 and milk["lastPrice"] == "50.00" and milk["listing"]["price"] == "54.00"
    low = data["runningLow"]
    assert low and low[0]["usualDays"] == 5 and low[0]["daysSince"] >= 5
    Product.objects.filter(pk=shops["a_rice"].pk).update(stock_quantity=0)
    r = auth_api.post(f"/api/v1/customer/groceries/orders/{last.id}/reorder", {}, format="json").json()
    assert r["added"] == ["Toned Milk"] and r["skipped"] == ["Basmati Rice"]
    assert r["priceChanges"] == [{"name": "Toned Milk", "from": "50.00", "to": "54.00"}]


def test_search_groups_by_item_and_compare_uses_same_pack_only(api, shops, home):
    s = api.get(f"/api/v1/groceries/search?q=basmati&lat={HOME[0]}&lng={HOME[1]}&sort=price_low").json()
    names = [(r["name"], r["size"]) for r in s["results"]]
    assert names == [("Basmati Rice", "1 kg"), ("Basmati Rice", "5 kg")]
    five = next(r for r in s["results"] if r["size"] == "5 kg")
    assert five["otherStores"] == 1 and five["price"] == "620.00" and five["perUnit"] == "₹124/kg"
    d = api.get(f"/api/v1/groceries/products/{shops['a_rice'].id}?lat={HOME[0]}&lng={HOME[1]}").json()
    assert sorted((c["store"]["name"], c["size"]) for c in d["compare"]) == [("Mid Kirana", "5 kg"), ("Near Mart", "5 kg")]
    assert d["mrp"] == "799.00" and d["discountPercent"] == 19
    filtered = api.get(f"/api/v1/groceries/search?q=rice&lat={HOME[0]}&lng={HOME[1]}&max_price=200").json()
    assert [r["size"] for r in filtered["results"]] == ["1 kg"]
    no_location = api.get("/api/v1/groceries/search?q=rice").json()
    assert no_location["hasLocation"] is False and all(r["store"]["etaLabel"] == "" for r in no_location["results"])


def test_shopping_list_find_everything(auth_api, shops, home, other_customer):
    sl = auth_api.post("/api/v1/customer/groceries/lists", {"name": "Weekly", "items": ["milk", "basmati rice", "curd", "saffron"]},
                       format="json").json()
    r = auth_api.post(f"/api/v1/customer/groceries/lists/{sl['id']}/find?address={home.id}", {}, format="json").json()
    assert r["best"]["store"]["name"] == "Mid Kirana" and r["best"]["found"] == 3
    assert [m["text"] for m in r["missing"]] == ["saffron"] and r["complete"] is False
    from rest_framework.test import APIClient

    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get(f"/api/v1/customer/groceries/lists/{sl['id']}").status_code == 404


def test_vendor_ownership_and_restock_alert(api, shops, customer, django_capture_on_commit_callbacks):
    from apps.partners.models import PartnerStore

    owner = make_customer("vendor@example.com")
    p = _make_partner(owner)
    PartnerStore.objects.create(partner=p, store=shops["a"])
    api.force_authenticate(owner)
    assert api.patch(f"/api/v1/partner/grocery/listings/{shops['b_milk'].id}", {"price": "1.00"}, format="json").status_code == 404
    r = api.patch(f"/api/v1/partner/grocery/listings/{shops['a_milk'].id}", {"price": "60.00", "mrp": "55.00"}, format="json")
    assert r.status_code == 400

    Product.objects.filter(pk=shops["a_milk"].pk).update(stock_quantity=0)
    shopper = APIClientFor(customer)
    assert shopper.post("/api/v1/customer/groceries/alerts", {"productId": str(shops["a_milk"].id)}, format="json").status_code == 201
    with django_capture_on_commit_callbacks(execute=True):
        r = api.patch(f"/api/v1/partner/grocery/listings/{shops['a_milk'].id}", {"stock": 12, "receivedOn": str(date.today())}, format="json")
    assert r.status_code == 200 and r.json()["stock"] == 12
    assert Notification.objects.filter(customer=customer.customer_profile, title__startswith="Back in stock").count() == 1
    assert StockAlert.objects.get().notified_at is not None
    assert [x["id"] for x in api.get("/api/v1/partner/grocery/listings").json()["results"]] == sorted(
        [str(shops["a_milk"].id), str(shops["a_rice"].id)], key=lambda i: 0 if i == str(shops["a_milk"].id) else 1)


def APIClientFor(user):  # noqa: N802
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user)
    return c


def _make_partner(user):
    from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerType

    ptype, _ = PartnerType.objects.get_or_create(slug="retail", defaults={"name": "Retail"})
    pcat, _ = PartnerCategory.objects.get_or_create(slug="grocery-store", defaults={"name": "Grocery Store", "partner_type": ptype})
    partner = Partner.objects.create(partner_type=ptype, category=pcat, status=Partner.Status.ACTIVE, business_name="Near Mart",
                                     partner_code="CLK-PT-TEST01")
    PartnerMembership.objects.create(partner=partner, user=user, role=PartnerMembership.Role.OWNER)
    return partner


def test_home_hides_empty_sections_and_needs_location_for_promises(api, shops):
    signed_out = api.get("/api/v1/groceries/home").json()
    assert signed_out["hasLocation"] is False and all(s["etaLabel"] == "" or s["deliverable"] is False for s in signed_out["stores"])
    near = api.get(f"/api/v1/groceries/home?lat={HOME[0]}&lng={HOME[1]}").json()
    assert {s["code"] for s in near["sections"]} == {"dairy", "essentials"}
    assert [c["slug"] for c in near["categories"]] == ["dairy", "rice-atta"]
    assert near["buyAgain"] == []
