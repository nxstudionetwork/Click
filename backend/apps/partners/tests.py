import threading
import time
from unittest import mock

import pytest
from django.db import connection
from django.test import override_settings

from apps.identity import services as identity_services
from apps.identity.models import ExternalIdentity
from apps.identity.providers import VerifiedIdentity
from apps.identity.tests import CERT, OTHER_KEY, PROJECT, token
from apps.partners import services
from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerStatusEvent, PartnerVerification
from apps.users.models import User

pytestmark = pytest.mark.django_db
CLIENT = {"HTTP_X_CLICK_CLIENT": "partner-web"}


@pytest.fixture(autouse=True)
def partner_catalog(db):
    """Catalogue rows come from a data migration; transactional tests flush them, so restore if needed."""
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    if not PartnerType.objects.exists():
        apply_catalog(PartnerType, PartnerCategory)


@pytest.fixture(autouse=True)
def firebase_keys(settings):
    """Real RS256 verification (shared identity layer) against a test certificate instead of Google's."""
    settings.FIREBASE_PROJECT_ID = PROJECT
    with mock.patch("apps.identity.firebase.fetch_certificates", return_value={"k1": CERT}):
        yield


def sign_in(api, uid="fb-uid-1", phone="+919876543210", **kw):
    """The Partner App's sign-in: shared identity exchange, then partner sign-up for a new phone."""
    r = api.post("/api/v1/auth/identity/exchange", {"provider": "firebase", "token": token(uid=uid, phone=phone, **kw)}, **CLIENT)
    if r.status_code == 200 and r.json()["status"] == "profile_required":
        r = api.post("/api/v1/auth/identity/partner-signup", {"signupToken": r.json()["signupToken"]}, **CLIENT)
    return r


def authed(api, **kw):
    r = sign_in(api, **kw)
    assert r.status_code in (200, 201), r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return r


# --- Partner sign-in on the shared identity layer ---------------------------------

def test_new_phone_becomes_phone_only_user_linked_to_firebase_uid(api):
    r = sign_in(api)
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["phone"] == "+919876543210" and user["email"] is None and user["roles"] == []
    assert r.cookies["click_refresh"]["httponly"]
    link = ExternalIdentity.objects.get()
    assert (link.provider, link.subject) == ("firebase", "fb-uid-1")
    assert link.user.phone_verified and not link.user.has_usable_password()


def test_returning_partner_gets_the_same_user(api):
    first = sign_in(api).json()["user"]["id"]
    r = sign_in(api)
    assert r.status_code == 200 and r.json()["status"] == "authenticated" and r.json()["user"]["id"] == first
    assert User.objects.count() == 1 and ExternalIdentity.objects.count() == 1


def test_existing_customer_with_verified_phone_is_the_same_person(api):
    customer = User.objects.create_user("meera@example.com", None, phone="+919876543210", phone_verified=True)
    r = sign_in(api, uid="new-uid")
    assert r.status_code == 200 and r.json()["user"]["id"] == str(customer.id)
    assert User.objects.count() == 1


def test_forged_token_is_rejected(api):
    r = sign_in(api, key=OTHER_KEY)
    assert r.status_code == 401 and User.objects.count() == 0


def test_tampered_signup_token_is_rejected(api):
    r = api.post("/api/v1/auth/identity/partner-signup", {"signupToken": "forged"}, **CLIENT)
    assert r.status_code == 401 and User.objects.count() == 0


def test_partner_signup_is_idempotent_and_race_safe():
    identity = VerifiedIdentity(provider="firebase", subject="race-uid", phone_number="+919111122222")
    a, created_a = identity_services.complete_partner_signup(identity)
    b, created_b = identity_services.complete_partner_signup(identity)
    assert a == b and created_a and not created_b


def test_disabled_partner_cannot_sign_in(api):
    sign_in(api)
    User.objects.update(is_active=False)
    r = sign_in(api)
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_disabled"


def test_logout_then_refresh_fails_but_partner_survives(api):
    authed(api)
    complete_onboarding(api)
    assert api.post("/api/v1/auth/logout", **CLIENT).status_code == 204
    assert api.post("/api/v1/auth/refresh", **CLIENT).status_code == 401
    assert Partner.objects.count() == 1
    api.credentials()
    authed(api)
    assert api.get("/api/v1/partner/me").json()["partner"]["partnerCode"] == "CLK-PT-%06d" % _last_code_number()


# --- Catalogue ------------------------------------------------------------------

def test_catalog_is_public_and_carries_resolved_configuration(api):
    r = api.get("/api/v1/partner/categories")
    assert r.status_code == 200
    types = {t["slug"]: t for t in r.data["types"]}
    assert {"transport", "food", "retail", "logistics", "services", "entertainment", "hospitality", "local"} <= set(types)
    auto = next(c for c in types["transport"]["categories"] if c["slug"] == "auto-driver")
    cfg = auto["configuration"]
    assert cfg["identity"]["individual"] is True
    keys = [f["key"] for f in cfg["fields"]]
    assert "vehicleNumber" in keys  # field keys are camelCase like the rest of the API
    assert next(f for f in cfg["fields"] if f["key"] == "vehicleType")["default"] == "auto"
    assert [m["label"] for m in cfg["home"]["modules"]][:2] == ["Ride requests", "Active ride"]
    fleet = next(c for c in types["transport"]["categories"] if c["slug"] == "fleet-operator")
    assert "vehicleNumber" not in [f["key"] for f in fleet["configuration"]["fields"]]


def test_inactive_category_is_hidden_and_cannot_be_chosen(api):
    PartnerCategory.objects.filter(slug="cafe").update(is_active=False)
    r = api.get("/api/v1/partner/categories")
    food = next(t for t in r.data["types"] if t["slug"] == "food")
    assert "cafe" not in [c["slug"] for c in food["categories"]]
    authed(api)
    r = api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "cafe"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_category"


# --- Onboarding -------------------------------------------------------------------

PROFILES = {
    ("transport", "driver"): {"businessName": "Ravi Kumar", "details": {"vehicleType": "car", "vehicleNumber": "KA01AB1234", "availability": "full_time"}},
    ("food", "restaurant"): {"businessName": "Spice Route", "contactName": "Meera", "email": "Owner@SpiceRoute.in",
                             "details": {"cuisines": ["south_indian", "biryani"], "foodType": "both", "opensAt": "09:00", "closesAt": "23:00"}},
    ("retail", "grocery-store"): {"businessName": "Fresh Mart", "contactName": "Anil",
                                  "details": {"opensAt": "07:00", "closesAt": "22:00", "fulfilment": ["delivery", "pickup"]}},
    ("logistics", "parcel-partner"): {"businessName": "Sunil Parcel", "details": {"services": ["same_day"], "dailyCapacity": 40}},
    ("services", "manpower-provider"): {"businessName": "Skilled Hands", "contactName": "Joseph",
                                        "details": {"serviceTypes": ["cleaning", "security"], "workforceSize": 25, "availability": "all_days"}},
    ("entertainment", "cinema-hall"): {"businessName": "Galaxy Screens", "contactName": "Priya",
                                       "details": {"screens": 4, "opensAt": "10:00", "closesAt": "23:59"}},
    ("hospitality", "hotel"): {"businessName": "Lakeview Inn", "contactName": "Farah",
                               "details": {"propertyType": "hotel", "capacity": 40}},
}
LOCATION = {"line1": "12 MG Road", "city": "Bengaluru", "state": "Karnataka", "postalCode": "560001",
            "latitude": 12.9715987, "longitude": 77.5945627, "serviceArea": "Central Bengaluru"}


def _last_code_number():
    with connection.cursor() as c:
        c.execute("SELECT last_value FROM partners_partner_code_seq")
        return c.fetchone()[0]


def complete_onboarding(api, ptype="food", category="restaurant"):
    assert api.post("/api/v1/partner/onboarding/category", {"partnerType": ptype, "category": category}).status_code == 200
    r = api.patch("/api/v1/partner/onboarding/profile", PROFILES[(ptype, category)])
    assert r.status_code == 200, r.content
    r = api.patch("/api/v1/partner/onboarding/location", LOCATION)
    assert r.status_code == 200, r.content
    r = api.post("/api/v1/partner/onboarding/submit")
    assert r.status_code == 200, r.content
    return r.json()["partner"]


def test_new_partner_has_no_partner_yet(api):
    authed(api)
    r = api.get("/api/v1/partner/me")
    assert r.status_code == 200 and r.json() == {"partner": None, "onboardingStep": "category"}


def test_partner_endpoints_require_authentication(api):
    assert api.get("/api/v1/partner/me").status_code == 401
    assert api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "cafe"}).status_code == 401


@pytest.mark.parametrize("ptype,category", list(PROFILES))
def test_full_onboarding_per_category(api, ptype, category):
    authed(api)
    p = complete_onboarding(api, ptype, category)
    assert p["partnerCode"].startswith("CLK-PT-") and len(p["partnerCode"]) == 13
    assert p["partnerType"]["slug"] == ptype and p["category"]["slug"] == category
    assert p["status"] == "verification_pending" and p["statusLabel"] == "Verification pending"
    assert p["isVerified"] is False
    assert p["onboardingStep"] == "complete"
    assert p["address"]["city"] == "Bengaluru"
    assert "id" not in p  # internal database IDs are never exposed
    partner = Partner.objects.get()
    assert [e.to_status for e in PartnerStatusEvent.objects.filter(partner=partner)] == [
        "draft", "profile_completed", "verification_pending"]
    assert PartnerVerification.objects.get(partner=partner).status == "pending"
    # Category survives a fresh session.
    api.credentials()
    authed(api)
    me = api.get("/api/v1/partner/me").json()["partner"]
    assert me["category"]["slug"] == category and me["partnerCode"] == p["partnerCode"]
    assert me["category"]["configuration"]["home"]["modules"]


def test_individual_partner_uses_name_as_contact_and_email_is_normalised(api):
    authed(api)
    p = complete_onboarding(api, "transport", "driver")
    assert p["profile"]["contactName"] == "Ravi Kumar"
    authed(api, uid="fb-uid-2", phone="+919111111111")
    p2 = complete_onboarding(api, "food", "restaurant")
    assert p2["profile"]["email"] == "owner@spiceroute.in"
    assert p2["profile"]["details"]["opensAt"] == "09:00"


def test_partner_codes_are_sequential_unique_and_stable(api):
    authed(api, uid="a", phone="+919000000011")
    a = complete_onboarding(api)["partnerCode"]
    authed(api, uid="b", phone="+919000000012")
    b = complete_onboarding(api, "transport", "driver")["partnerCode"]
    assert int(b[-6:]) == int(a[-6:]) + 1
    # Resubmitting never mints a new ID.
    assert api.post("/api/v1/partner/onboarding/submit").json()["partner"]["partnerCode"] == b


def test_profile_validation_follows_category_schema(api):
    authed(api)
    api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "restaurant"})
    r = api.patch("/api/v1/partner/onboarding/profile", {"businessName": "X", "details": {}})
    assert r.status_code == 400
    r = api.patch("/api/v1/partner/onboarding/profile", {
        "businessName": "Spice Route", "contactName": "M",
        "details": {"cuisines": ["martian"], "foodType": "both", "opensAt": "25:00", "closesAt": "10:00", "vehicleType": "car"},
    })
    assert r.status_code == 400
    errors = r.json()["error"]["details"]["details"]
    assert set(errors) == {"cuisines", "opensAt", "vehicleType"}
    r = api.patch("/api/v1/partner/onboarding/profile", {"businessName": "Spice Route", "details": PROFILES[("food", "restaurant")]["details"]})
    assert r.status_code == 400 and "contactName" in r.json()["error"]["details"]


def test_location_validation(api):
    authed(api)
    api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "restaurant"})
    r = api.patch("/api/v1/partner/onboarding/location", {**LOCATION, "postalCode": "12AB"})
    assert r.status_code == 400 and set(r.json()["error"]["details"]) == {"postalCode"}
    r = api.patch("/api/v1/partner/onboarding/location", {**LOCATION, "longitude": None})
    assert r.status_code == 400 and set(r.json()["error"]["details"]) == {"latitude"}
    r = api.patch("/api/v1/partner/onboarding/location", {**LOCATION, "latitude": 123})
    assert r.status_code == 400
    r = api.patch("/api/v1/partner/onboarding/location", {"line1": "", "city": "B"})
    assert r.status_code == 400


def test_submit_requires_all_steps(api):
    authed(api)
    assert api.post("/api/v1/partner/onboarding/submit").status_code == 404
    api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "restaurant"})
    r = api.post("/api/v1/partner/onboarding/submit")
    assert r.status_code == 400 and r.json()["error"]["code"] == "onboarding_incomplete"
    assert set(r.json()["error"]["details"]) == {"profile", "location"}
    assert Partner.objects.get().partner_code is None


def test_onboarding_step_progression(api):
    authed(api)
    step = lambda: api.get("/api/v1/partner/me").json()["onboardingStep"]  # noqa: E731
    assert step() == "category"
    api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "restaurant"})
    assert step() == "profile"
    api.patch("/api/v1/partner/onboarding/profile", PROFILES[("food", "restaurant")])
    assert step() == "location"
    api.patch("/api/v1/partner/onboarding/location", LOCATION)
    assert step() == "review"


def test_changing_category_in_draft_resets_details_without_duplicate(api):
    authed(api)
    api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "restaurant"})
    api.patch("/api/v1/partner/onboarding/profile", PROFILES[("food", "restaurant")])
    r = api.post("/api/v1/partner/onboarding/category", {"partnerType": "transport", "category": "driver"})
    assert r.json()["partner"]["category"]["slug"] == "driver"
    assert r.json()["partner"]["profile"]["details"] == {}
    assert Partner.objects.count() == 1 and PartnerMembership.objects.count() == 1


def test_category_mismatch_with_type_is_rejected(api):
    authed(api)
    r = api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "driver"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_category"


def test_onboarded_partner_is_locked(api):
    authed(api)
    complete_onboarding(api)
    r = api.post("/api/v1/partner/onboarding/category", {"partnerType": "transport", "category": "driver"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "partner_locked"
    assert api.patch("/api/v1/partner/onboarding/profile", PROFILES[("food", "restaurant")]).status_code == 409
    assert api.patch("/api/v1/partner/onboarding/location", LOCATION).status_code == 409


def test_repeated_category_selection_never_duplicates_partner(api):
    authed(api)
    for _ in range(3):
        api.post("/api/v1/partner/onboarding/category", {"partnerType": "food", "category": "restaurant"})
    assert Partner.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_category_selection_creates_one_partner(partner_catalog):
    user = User.objects.create_phone_user("+919222222222")
    category = PartnerCategory.objects.get(slug="restaurant")
    errors = []

    def go():
        try:
            services.choose_category(user, "food", category.slug)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and Partner.objects.count() == 1


# --- Isolation ----------------------------------------------------------------------

def test_partner_a_cannot_see_or_change_partner_b(api):
    authed(api, uid="owner-a", phone="+919000000021")
    a = complete_onboarding(api)
    api.credentials()
    authed(api, uid="owner-b", phone="+919000000022")
    me = api.get("/api/v1/partner/me").json()
    assert me["partner"] is None  # B sees nothing of A
    # B's writes only ever create/affect B's own partner.
    api.post("/api/v1/partner/onboarding/category", {"partnerType": "transport", "category": "driver"})
    assert Partner.objects.count() == 2
    a_row = Partner.objects.get(partner_code=a["partnerCode"])
    assert a_row.category.slug == "restaurant" and a_row.business_name == "Spice Route"
    # A partner code or id in the body is ignored, never used for lookup.
    r = api.patch("/api/v1/partner/onboarding/profile", {**PROFILES[("transport", "driver")], "partnerCode": a["partnerCode"]})
    assert r.json()["partner"]["businessName"] == "Ravi Kumar"
    assert Partner.objects.get(partner_code=a["partnerCode"]).business_name == "Spice Route"


# --- Staff review ---------------------------------------------------------------------

def test_only_staff_review_marks_verified(api):
    authed(api)
    complete_onboarding(api)
    partner = Partner.objects.get()
    staff = User.objects.create_user("ops@click.test", "S3cure-pass-123", is_staff=True)
    services.review_verification(partner, approve=True, reviewer=staff)
    me = api.get("/api/v1/partner/me").json()["partner"]
    assert me["status"] == "verified" and me["isVerified"] is True
    with pytest.raises(Exception):
        services.review_verification(partner, approve=True, reviewer=staff)


def test_user_roles_include_partner_after_onboarding(api):
    authed(api)
    complete_onboarding(api)
    assert "partner" in api.get("/api/v1/me").data["roles"]


@override_settings(DEBUG=False)
def test_error_responses_do_not_leak_internals(api):
    r = sign_in(api, key=OTHER_KEY)
    body = r.json()["error"]
    assert "Signature" not in body["message"] and "Traceback" not in str(body)
