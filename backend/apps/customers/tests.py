import pytest

pytestmark = pytest.mark.django_db

ADDR = {"recipientName": "Asha", "phone": "+91 98765 43210", "line1": "1 Main St", "city": "Bengaluru", "postalCode": "560001"}


def test_first_address_becomes_default_and_default_is_unique(auth_api):
    a = auth_api.post("/api/v1/customer/addresses", ADDR).json()
    assert a["isDefault"] is True
    b = auth_api.post("/api/v1/customer/addresses", {**ADDR, "label": "work", "isDefault": True}).json()
    listed = {x["id"]: x["isDefault"] for x in auth_api.get("/api/v1/customer/addresses").json()}
    assert listed == {a["id"]: False, b["id"]: True}


def test_address_validation(auth_api):
    r = auth_api.post("/api/v1/customer/addresses", {**ADDR, "phone": "call me"})
    assert r.status_code == 400 and "phone" in r.json()["error"]["details"]


def test_addresses_are_isolated_between_customers(api, customer, other_customer, address):
    api.force_authenticate(other_customer)
    assert api.get("/api/v1/customer/addresses").json() == []
    assert api.get(f"/api/v1/customer/addresses/{address.id}").status_code == 404
    assert api.delete(f"/api/v1/customer/addresses/{address.id}").status_code == 404


def test_addresses_require_auth(api):
    assert api.get("/api/v1/customer/addresses").status_code == 401


def test_profile_summary_counts_only_the_signed_in_customer(auth_api, customer, other_customer, store):
    from apps.customers.models import Address
    from apps.wishlists.models import WishlistItem

    mine, theirs = customer.customer_profile, other_customer.customer_profile
    Address.objects.create(customer=mine, recipient_name="A", phone="1", line1="x", city="Bengaluru", postal_code="560001")
    WishlistItem.objects.create(customer=mine, store=store)
    WishlistItem.objects.create(customer=theirs, store=store)
    r = auth_api.get("/api/v1/customer/profile/summary")
    assert r.status_code == 200
    assert r.json() == {"activity": {"orders": 0, "bookings": 0, "rides": 0, "total": 0}, "wishlist": 1, "addresses": 1,
                        "unreadNotifications": 0, "rewardsBalance": 0}


def test_profile_summary_requires_sign_in(api):
    assert api.get("/api/v1/customer/profile/summary").status_code == 401
