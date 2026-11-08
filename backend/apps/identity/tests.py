import time
from unittest import mock

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.test import override_settings

from apps.customers.models import CustomerProfile
from apps.identity.firebase import FirebaseIdTokenVerifier
from apps.identity.models import ExternalIdentity
from apps.identity.providers import IdentityError
from apps.users.models import User

pytestmark = pytest.mark.django_db
PROJECT = "clickstartup26"
ADDR = {"label": "home", "recipientName": "Meera", "phone": "+91 90000 11111", "line1": "1 Lake View", "city": "Bengaluru", "postalCode": "560001"}


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    import datetime

    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(datetime.datetime(2020, 1, 1)).not_valid_after(datetime.datetime(2040, 1, 1))
            .sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


KEY, CERT = _keypair()
OTHER_KEY, _ = _keypair()


def token(uid="uid-1", phone="+919000011111", provider="phone", key=KEY, kid="k1", **over):
    now = int(time.time())
    claims = {"iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "sub": uid, "iat": now, "exp": now + 3600,
              "auth_time": now, "phone_number": phone, "firebase": {"sign_in_provider": provider}}
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(autouse=True)
def certs():
    with mock.patch("apps.identity.firebase.fetch_certificates", return_value={"k1": CERT}):
        yield


def verify(t):
    return FirebaseIdTokenVerifier().verify(t)


# --- verifier: Firebase's documented checks ---------------------------------------

def test_valid_firebase_phone_token():
    v = verify(token())
    assert (v.provider, v.subject, v.phone_number) == ("firebase", "uid-1", "+919000011111")


@pytest.mark.parametrize("bad", [
    dict(key=OTHER_KEY),                                   # wrong signature
    dict(kid="unknown"),                                   # unknown key id
    dict(aud="someone-else"),                              # wrong project
    dict(iss="https://securetoken.google.com/other"),      # wrong issuer
    dict(exp=int(time.time()) - 3600),                     # expired
    dict(auth_time=int(time.time()) + 3600),               # auth in the future
    dict(provider="password"),                             # not a phone sign-in
    dict(phone=""),                                        # no verified phone
    dict(uid=""),                                          # empty subject
])
def test_invalid_tokens_are_rejected(bad):
    with pytest.raises(IdentityError):
        verify(token(**bad))


def test_unsigned_tokens_rejected_outside_emulator():
    t = jwt.encode({"sub": "x"}, None, algorithm="none")
    with pytest.raises(IdentityError):
        verify(t)


@override_settings(DEBUG=True, FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099")
def test_emulator_tokens_only_in_debug_with_emulator_host():
    now = int(time.time())
    t = jwt.encode({"iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "sub": "emu", "iat": now, "exp": now + 60,
                    "auth_time": now, "phone_number": "+16505550199", "firebase": {"sign_in_provider": "phone"}}, None, algorithm="none")
    assert verify(t).subject == "emu"


# --- exchange + signup -------------------------------------------------------------

def exchange(api, t):
    return api.post("/api/v1/auth/identity/exchange", {"provider": "firebase", "token": t})


def signup(api, signup_token, email="meera@example.com", addresses=None, name="Meera Rao"):
    return api.post("/api/v1/auth/identity/signup", {"signupToken": signup_token, "fullName": name, "email": email, "addresses": [ADDR] if addresses is None else addresses})


def test_new_customer_flow_creates_one_customer_with_click_id_and_identity(api):
    r = exchange(api, token())
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
    assert (link.provider, link.subject) == ("firebase", "uid-1")
    assert u.customer_profile.addresses.count() == 2 and u.customer_profile.addresses.filter(is_default=True).count() == 1
    assert u.customer_profile.activities.filter(verb="account.signup").exists()

    # Returning customer: same Firebase UID -> same Click customer, straight to a session.
    r2 = exchange(api, token())
    assert r2.json()["status"] == "authenticated" and r2.json()["user"]["customerCode"] == user["customerCode"]
    assert CustomerProfile.objects.count() == 1


def test_signup_is_idempotent_no_duplicates(api):
    st = exchange(api, token()).json()["signupToken"]
    a = signup(api, st)
    b = signup(api, st)
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["user"]["id"] == b.json()["user"]["id"] and User.objects.count() == 1


def test_verified_phone_on_existing_account_links_instead_of_duplicating(api):
    u = User.objects.create_user("old@example.com", None, phone="+919000011111", phone_verified=True)
    CustomerProfile.objects.create(user=u)
    r = exchange(api, token(uid="new-uid"))
    assert r.json()["status"] == "authenticated" and r.json()["user"]["id"] == str(u.id)
    assert ExternalIdentity.objects.get(subject="new-uid").user == u


def test_unverified_phone_match_does_not_hijack_account(api):
    u = User.objects.create_user("someone@example.com", None, phone="+919000011111", phone_verified=False)
    CustomerProfile.objects.create(user=u)
    assert exchange(api, token()).json()["status"] == "profile_required"


def test_signup_validation(api):
    st = exchange(api, token()).json()["signupToken"]
    User.objects.create_user("taken@example.com", None)
    assert signup(api, st, email="taken@example.com").json()["error"]["code"] == "email_taken"
    assert signup(api, st, addresses=[ADDR] * 6).status_code == 400
    assert signup(api, st, addresses=[]).status_code == 400
    assert signup(api, st, name=" ").status_code == 400
    assert signup(api, st, addresses=[{**ADDR, "phone": "abc"}]).status_code == 400
    assert signup(api, "forged-token").json()["error"]["code"] == "signup_invalid"


def test_invalid_provider_token_and_unknown_provider(api):
    assert exchange(api, token(key=OTHER_KEY)).json()["error"]["code"] == "identity_invalid"
    r = api.post("/api/v1/auth/identity/exchange", {"provider": "magic", "token": token()})
    assert r.status_code == 401


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
