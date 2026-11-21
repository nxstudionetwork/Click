"""Safety Center: reports are support requests flagged as safety cases (urgent or important, never normal), listed only
for their owner; signing out other devices revokes every other sign-in."""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_safety_report_is_a_prioritised_support_request(auth_api, customer, other_customer):
    body = {"category": "ride", "issueType": "Lost item", "subject": "Left my bag", "message": "Left my bag in the cab.", "isSafety": True,
            "contactPreference": "call"}
    r = auth_api.post("/api/v1/customer/support/tickets", body, format="json")
    assert r.status_code == 201 and r.json()["isSafety"] and r.json()["priority"] == "important"
    r2 = auth_api.post("/api/v1/customer/support/tickets", {**body, "subject": "Driver was rude", "issueType": "Inappropriate behaviour"}, format="json")
    assert r2.json()["priority"] == "urgent"
    s = auth_api.get("/api/v1/customer/safety").json()
    assert s["emergencyNumber"] == "112" and len(s["reports"]) == 2 and s["sessions"]["active"] >= 0
    other = APIClient()
    other.force_authenticate(other_customer)
    assert other.get("/api/v1/customer/safety").json()["reports"] == []
    assert len(auth_api.get("/api/v1/customer/support/tickets", {"safety": "1"}).json()["results"]) == 2


def test_sign_out_other_devices(customer):
    from rest_framework_simplejwt.tokens import RefreshToken

    tokens = [RefreshToken.for_user(customer) for _ in range(3)]
    api = APIClient()
    api.force_authenticate(customer)
    api.cookies["click_refresh"] = str(tokens[0])
    r = api.post("/api/v1/customer/safety/sign-out-others").json()
    assert r["signedOut"] == 2 and r["active"] == 1
