import pytest

from apps.users.models import User

pytestmark = pytest.mark.django_db
CLIENT = {"HTTP_X_CLICK_CLIENT": "customer-web"}


def test_register_creates_customer_and_sets_refresh_cookie(api):
    r = api.post("/api/v1/auth/register", {"email": "New@Example.com", "password": "S3cure-pass-123", "fullName": "New"})
    assert r.status_code == 201
    assert r.data["user"]["email"] == "new@example.com"
    assert r.data["user"]["roles"] == ["customer"]
    assert r.data["access"]
    cookie = r.cookies["click_refresh"]
    assert cookie["httponly"] and cookie["path"] == "/api/v1/auth/"
    assert "refresh" not in r.json()


def test_register_rejects_duplicate_email_case_insensitive(api, customer):
    r = api.post("/api/v1/auth/register", {"email": "ASHA@example.com", "password": "S3cure-pass-123"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"
    assert "email" in r.json()["error"]["details"]


def test_register_rejects_weak_password(api):
    r = api.post("/api/v1/auth/register", {"email": "x@example.com", "password": "12345678"})
    assert r.status_code == 400


def test_login_success_and_failure(api, customer):
    assert api.post("/api/v1/auth/login", {"email": "asha@example.com", "password": "wrong"}).status_code == 401
    r = api.post("/api/v1/auth/login", {"email": "ASHA@example.com", "password": "S3cure-pass-123"})
    assert r.status_code == 200 and r.data["access"]


def test_refresh_rotates_and_old_token_is_rejected(api, customer):
    api.post("/api/v1/auth/login", {"email": "asha@example.com", "password": "S3cure-pass-123"})
    old = api.cookies["click_refresh"].value
    r = api.post("/api/v1/auth/refresh", **CLIENT)
    assert r.status_code == 200 and r.data["access"]
    assert api.cookies["click_refresh"].value != old
    api.cookies["click_refresh"] = old
    assert api.post("/api/v1/auth/refresh", **CLIENT).status_code == 401


def test_refresh_requires_client_header(api, customer):
    api.post("/api/v1/auth/login", {"email": "asha@example.com", "password": "S3cure-pass-123"})
    assert api.post("/api/v1/auth/refresh").status_code == 403


def test_logout_blacklists_refresh(api, customer):
    api.post("/api/v1/auth/login", {"email": "asha@example.com", "password": "S3cure-pass-123"})
    token = api.cookies["click_refresh"].value
    assert api.post("/api/v1/auth/logout", **CLIENT).status_code == 204
    api.cookies["click_refresh"] = token
    assert api.post("/api/v1/auth/refresh", **CLIENT).status_code == 401


def test_me_requires_auth_and_returns_user(api, customer):
    assert api.get("/api/v1/me").status_code == 401
    token = api.post("/api/v1/auth/login", {"email": "asha@example.com", "password": "S3cure-pass-123"}).data["access"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    r = api.get("/api/v1/me")
    assert r.status_code == 200 and r.json()["fullName"] == "Asha"


def test_email_is_case_insensitively_unique_at_db_level(customer):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        User.objects.create(email="Asha@Example.com")


def test_session_refresh_has_its_own_throttle_scope():
    """Refresh runs on every page load; it must not share the strict login limit."""
    from apps.users.views import LoginView, RefreshView, RegisterView

    assert LoginView.throttle_scope == RegisterView.throttle_scope == "auth"
    assert RefreshView.throttle_scope == "auth_session"


def test_name_update_requires_letters(auth_api):
    assert auth_api.patch("/api/v1/me", {"fullName": "12345"}, format="json").status_code == 400
    r = auth_api.patch("/api/v1/me", {"fullName": "  Asha   Rao "}, format="json")
    assert r.status_code == 200 and r.json()["fullName"] == "Asha Rao"
