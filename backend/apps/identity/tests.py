import pytest
from django.test import override_settings
from django.utils import timezone

from apps.customers.models import CustomerProfile
from apps.identity.models import ExternalIdentity, OtpChallenge
from apps.users.models import User
from conftest import SMS_OUTBOX, otp_credential

pytestmark = pytest.mark.django_db
ADDR = {"label": "home", "recipientName": "Meera", "phone": "+91 90000 11111", "line1": "1 Lake View", "city": "Bengaluru", "postalCode": "560001"}
PHONE = "+919000011111"


# --- Click phone OTP ----------------------------------------------------------------------------------------------

def test_code_is_sent_hashed_single_use_and_expires(api, settings):
    r = api.post("/api/v1/auth/otp/request", {"phone": PHONE})
    assert r.status_code == 201 and r.json()["expiresIn"] == settings.CLICK_OTP_TTL_SECONDS
    phone, text = SMS_OUTBOX[-1]
    code = text[:6]
    ch = OtpChallenge.objects.get()
    assert phone == PHONE and code.isdigit() and code not in ch.code_hash  # only a hash is stored
    cred = f"{r.json()['challengeId']}.{code}"
    assert exchange(api, cred).json()["status"] == "profile_required"
    assert exchange(api, cred).json()["error"]["code"] == "code_expired"  # used once
    late = otp_credential(api, "+919000022222")
    OtpChallenge.objects.filter(phone="+919000022222").update(expires_at=timezone.now())
    assert exchange(api, late).json()["error"]["code"] == "code_expired"


def test_wrong_codes_are_limited_and_requests_rate_limited(api, settings):
    settings.CLICK_OTP_MAX_ATTEMPTS, settings.CLICK_OTP_RESEND_SECONDS = 3, 30
    cred = otp_credential(api, PHONE, wrong=True)
    assert exchange(api, cred).json()["error"]["code"] == "invalid_code"
    assert exchange(api, cred).json()["error"]["code"] == "invalid_code"
    assert exchange(api, cred).json()["error"]["code"] == "too_many_attempts"
    right = cred.split(".")[0] + "." + SMS_OUTBOX[-1][1][:6]
    assert exchange(api, right).json()["error"]["code"] == "code_expired"  # burnt after the limit
    again = api.post("/api/v1/auth/otp/request", {"phone": PHONE})
    assert again.status_code == 429 and again.json()["error"]["code"] == "otp_cooldown"
    settings.CLICK_OTP_RESEND_SECONDS = 0
    settings.CLICK_OTP_MAX_PER_HOUR = 2
    assert api.post("/api/v1/auth/otp/request", {"phone": PHONE}).status_code == 201
    assert api.post("/api/v1/auth/otp/request", {"phone": PHONE}).json()["error"]["code"] == "too_many_requests"
    assert api.post("/api/v1/auth/otp/request", {"phone": "12345"}).json()["error"]["code"] == "invalid_phone"


def test_newest_code_replaces_older_ones_and_no_sender_means_unavailable(api, settings):
    settings.CLICK_OTP_RESEND_SECONDS = 0
    first = otp_credential(api, PHONE)
    second = otp_credential(api, PHONE)
    assert exchange(api, first).json()["error"]["code"] == "code_expired"
    assert exchange(api, second).json()["status"] == "profile_required"
    settings.CLICK_SMS_PROVIDER = ""
    r = api.post("/api/v1/auth/otp/request", {"phone": "+919000033333"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "otp_unavailable"


# --- exchange + signup -------------------------------------------------------------

def exchange(api, t):
    return api.post("/api/v1/auth/identity/exchange", {"provider": "phone_otp", "token": t})


def token(api, phone=PHONE):
    return otp_credential(api, phone)


def signup(api, signup_token, email="meera@example.com", addresses=None, name="Meera Rao"):
    return api.post("/api/v1/auth/identity/signup", {"signupToken": signup_token, "fullName": name, "email": email, "addresses": [ADDR] if addresses is None else addresses})


def test_new_customer_flow_creates_one_customer_with_click_id_and_identity(api):
    r = exchange(api, token(api))
    assert r.status_code == 200 and r.json()["status"] == "profile_required"
    st = r.json()["signupToken"]
    assert r.json()["phoneNumber"] == "+919000011111" and "access" not in r.json()

    r = signup(api, st, addresses=[ADDR, {**ADDR, "label": "college", "line1": "Hostel B"}])
    assert r.status_code == 201, r.json()
    user = r.json()["user"]
    assert user["customerCode"].startswith("CLK-CS-") and user["phoneVerified"] is True and user["phone"] == "+919000011111"
    assert r.cookies["click_refresh"]["httponly"]
    u = User.objects.get(email="meera@example.com")
    link = ExternalIdentity.objects.get(user=u)
    assert (link.provider, link.subject) == ("phone_otp", "+919000011111")
    assert u.customer_profile.addresses.count() == 2 and u.customer_profile.addresses.filter(is_default=True).count() == 1
    assert u.customer_profile.activities.filter(verb="account.signup").exists()

    # Returning customer: same verified phone -> same Click customer, straight to a session.
    r2 = exchange(api, token(api))
    assert r2.json()["status"] == "authenticated" and r2.json()["user"]["customerCode"] == user["customerCode"]
    assert CustomerProfile.objects.count() == 1


def test_signup_is_idempotent_no_duplicates(api):
    st = exchange(api, token(api)).json()["signupToken"]
    a = signup(api, st)
    b = signup(api, st)
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["user"]["id"] == b.json()["user"]["id"] and User.objects.count() == 1


def test_verified_phone_on_existing_account_links_instead_of_duplicating(api):
    u = User.objects.create_user("old@example.com", None, phone="+919000011111", phone_verified=True)
    CustomerProfile.objects.create(user=u)
    r = exchange(api, token(api))
    assert r.json()["status"] == "authenticated" and r.json()["user"]["id"] == str(u.id)
    assert ExternalIdentity.objects.get(provider="phone_otp").user == u


def test_unverified_phone_match_does_not_hijack_account(api):
    u = User.objects.create_user("someone@example.com", None, phone="+919000011111", phone_verified=False)
    CustomerProfile.objects.create(user=u)
    assert exchange(api, token(api)).json()["status"] == "profile_required"


def test_signup_validation(api):
    st = exchange(api, token(api)).json()["signupToken"]
    User.objects.create_user("taken@example.com", None)
    assert signup(api, st, email="taken@example.com").json()["error"]["code"] == "email_taken"
    assert signup(api, st, addresses=[ADDR] * 6).status_code == 400
    assert signup(api, st, addresses=[]).status_code == 400
    assert signup(api, st, name=" ").status_code == 400
    assert signup(api, st, addresses=[{**ADDR, "phone": "abc"}]).status_code == 400
    assert signup(api, "forged-token").json()["error"]["code"] == "signup_invalid"


def test_invalid_credential_and_unknown_provider(api):
    assert exchange(api, "not-a-challenge.123456").json()["error"]["code"] == "code_expired"
    r = api.post("/api/v1/auth/identity/exchange", {"provider": "firebase", "token": token(api)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "identity_invalid"  # Firebase is no longer accepted


def test_address_limit_of_five(auth_api):
    for i in range(5):
        assert auth_api.post("/api/v1/customer/addresses", {**ADDR, "line1": f"{i} Road"}).status_code == 201
    r = auth_api.post("/api/v1/customer/addresses", {**ADDR, "line1": "6 Road"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "address_limit"


@override_settings(CLICK_PASSWORD_AUTH_ENABLED=False)
def test_password_auth_disabled_in_production(api, customer):
    assert api.post("/api/v1/auth/login", {"email": "asha@example.com", "password": "S3cure-pass-123"}).status_code == 404
    assert api.post("/api/v1/auth/register", {"email": "x@example.com", "password": "S3cure-pass-123"}).status_code == 404


def test_avatar_upload_reencodes_and_strips_metadata(auth_api, tmp_path, settings):
    from io import BytesIO

    from PIL import Image

    settings.MEDIA_ROOT = tmp_path
    buf = BytesIO()
    img = Image.new("RGB", (900, 600), "orange")
    exif = Image.Exif()
    exif[0x8825] = {2: (12, 58, 0)}  # GPS info
    img.save(buf, "JPEG", exif=exif)
    buf.seek(0)
    buf.name = "me.jpg"
    r = auth_api.post("/api/v1/me/avatar", {"image": buf}, format="multipart")
    assert r.status_code == 201 and r.json()["avatarUrl"].endswith(".webp")
    stored = Image.open(tmp_path / r.json()["avatarUrl"].removeprefix("/media/"))
    assert stored.size == (512, 512) and not stored.getexif()
    bad = BytesIO(b"not an image")
    bad.name = "x.png"
    assert auth_api.post("/api/v1/me/avatar", {"image": bad}, format="multipart").json()["error"]["code"] == "image_invalid"
