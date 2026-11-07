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
