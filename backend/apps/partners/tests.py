import threading
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.db import connection
from django.test import override_settings

from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerStatusEvent, PartnerVerification
from apps.partners import services
from apps.users import firebase
from apps.users.models import AuthIdentity, User

pytestmark = pytest.mark.django_db
PROJECT = "click-partner-test"
CLIENT = {"HTTP_X_CLICK_CLIENT": "partner-web"}

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def partner_catalog(db):
    """Catalogue rows come from a data migration; transactional tests flush them, so restore if needed."""
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    if not PartnerType.objects.exists():
        apply_catalog(PartnerType, PartnerCategory)


@pytest.fixture(autouse=True)
def firebase_keys(monkeypatch, settings):
    """Real RS256 verification against a test key instead of Google's live JWKS."""
    settings.FIREBASE_PROJECT_ID = PROJECT
    settings.FIREBASE_AUTH_EMULATOR_HOST = ""
    fake = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=_KEY.public_key()))
    monkeypatch.setattr(firebase, "_jwks_client", lambda: fake)


def id_token(uid="fb-uid-1", phone="+919876543210", *, key=_KEY, provider="phone", aud=PROJECT, iss=None, exp_in=3600, **extra):
    now = int(time.time())
    claims = {
        "iss": iss or f"https://securetoken.google.com/{aud}", "aud": aud, "sub": uid, "user_id": uid,
        "iat": now, "auth_time": now, "exp": now + exp_in, "firebase": {"sign_in_provider": provider},
        **({"phone_number": phone} if phone else {}), **extra,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})


def sign_in(api, **kw):
    return api.post("/api/v1/auth/firebase", {"idToken": id_token(**kw)}, **CLIENT)


def authed(api, **kw):
    r = sign_in(api, **kw)
    assert r.status_code in (200, 201), r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    return r


# --- Firebase session exchange ------------------------------------------------

def test_first_sign_in_creates_one_user_linked_to_firebase_uid(api):
    r = sign_in(api)
    assert r.status_code == 201
    assert r.data["user"]["phone"] == "+919876543210"
    assert r.data["user"]["email"] is None
    assert r.data["user"]["roles"] == []
    assert r.cookies["click_refresh"]["httponly"]
    identity = AuthIdentity.objects.get()
    assert identity.subject == "fb-uid-1" and identity.provider == "firebase"
    assert not identity.user.has_usable_password()


def test_returning_sign_in_reuses_user_and_tracks_phone_change(api):
    first = sign_in(api).data["user"]["id"]
    r = sign_in(api, phone="+919000000001")
    assert r.status_code == 200 and r.data["user"]["id"] == first
    assert User.objects.count() == 1 and AuthIdentity.objects.count() == 1
    assert User.objects.get().phone == "+919000000001"


@pytest.mark.parametrize("kwargs", [
    {"key": _OTHER_KEY},                                   # forged signature
    {"aud": "someone-elses-project"},                     # wrong project
    {"iss": "https://securetoken.google.com/evil"},       # wrong issuer
    {"provider": "password"},                             # not phone sign-in
    {"phone": None},                                      # no verified phone
    {"uid": ""},                                          # no UID
])
def test_rejects_tokens_that_fail_verification(api, kwargs):
    r = sign_in(api, **kwargs)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "phone_verification_failed"
    assert User.objects.count() == 0


def test_expired_token_has_friendly_message(api):
    r = sign_in(api, exp_in=-120)
    assert r.status_code == 401
    assert "expired" in r.json()["error"]["message"]


def test_garbage_token_and_missing_token(api):
    assert api.post("/api/v1/auth/firebase", {"idToken": "not-a-jwt"}, **CLIENT).status_code == 401
    assert api.post("/api/v1/auth/firebase", {}, **CLIENT).status_code == 400


def test_unconfigured_firebase_is_unavailable_not_bypassed(api, settings):
    settings.FIREBASE_PROJECT_ID = ""
    r = sign_in(api)
    assert r.status_code == 503 and r.json()["error"]["code"] == "phone_auth_unavailable"


def test_google_keys_unreachable_is_unavailable(api, monkeypatch):
    def boom(token):
        raise jwt.PyJWKClientConnectionError("down")
    monkeypatch.setattr(firebase, "_jwks_client", lambda: SimpleNamespace(get_signing_key_from_jwt=boom))
    r = sign_in(api)
    assert r.status_code == 503


def test_disabled_user_cannot_sign_in(api):
    sign_in(api)
    User.objects.update(is_active=False)
    r = sign_in(api)
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_disabled"


def test_emulator_tokens_only_accepted_when_emulator_configured(api, settings):
    now = int(time.time())
    claims = {"iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "sub": "emu-1", "iat": now,
              "auth_time": now, "exp": now + 600, "phone_number": "+15555550100", "firebase": {"sign_in_provider": "phone"}}
    unsigned = jwt.encode(claims, None, algorithm="none")
    assert api.post("/api/v1/auth/firebase", {"idToken": unsigned}, **CLIENT).status_code == 401
    settings.FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:9099"
    assert api.post("/api/v1/auth/firebase", {"idToken": unsigned}, **CLIENT).status_code == 201


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
    r = api.post("/api/v1/auth/firebase", {"idToken": id_token(key=_OTHER_KEY)}, **CLIENT)
    body = r.json()["error"]
    assert "Signature" not in body["message"] and "Traceback" not in str(body)
