import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.customers.models import CustomerProfile
from apps.orders.models import Order
from devseed.customer import TEST_CUSTOMER

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(db):
    call_command("seed_dev_data")
    return CustomerProfile.objects.get(customer_code="CLK-CS-TEST001")


def test_test_customer_has_real_related_history(seeded):
    assert seeded.user.email == "test.customer@click.local" and seeded.addresses.count() == 4
    assert seeded.orders.count() == 20 and seeded.bookings.count() == 20 and seeded.support_tickets.count() == 20
    assert seeded.wishlist_items.count() == 20 and seeded.cart.items.count() == 2
    statuses = set(seeded.orders.values_list("status", flat=True))
    assert {"delivered", "cancelled", "placed", "out_for_delivery"} <= statuses
    assert seeded.reward_transactions.count() == seeded.orders.filter(status="delivered").count()  # earned via the real rule
    # Every order went through the real checkout: items, payment and a status trail exist.
    for order in Order.objects.filter(customer=seeded):
        assert order.items.exists() and order.payments.exists() and order.events.exists()


def test_seed_is_repeatable_without_duplicates(seeded):
    before = (seeded.orders.count(), seeded.bookings.count(), seeded.wallet_transactions.count(), seeded.notifications.count())
    call_command("seed_dev_data")
    seeded.refresh_from_db()
    assert (seeded.orders.count(), seeded.bookings.count(), seeded.wallet_transactions.count(), seeded.notifications.count()) == before
    assert CustomerProfile.objects.filter(customer_code="CLK-CS-TEST001").count() == 1


def test_seed_refuses_outside_development():
    from django.core.management.base import CommandError

    with override_settings(DEBUG=False, TESTING=False), pytest.raises(CommandError):
        call_command("seed_dev_data")


def test_dev_login_does_not_exist_in_production(api, seeded):
    with override_settings(DEBUG=False, CLICK_DEV_LOGIN_ENABLED=True):
        assert api.get("/api/v1/auth/dev-login").status_code == 404
        assert api.post("/api/v1/auth/dev-login").status_code == 404
    with override_settings(DEBUG=True, CLICK_DEV_LOGIN_ENABLED=False):
        assert api.post("/api/v1/auth/dev-login").status_code == 404


@override_settings(DEBUG=True, CLICK_DEV_LOGIN_ENABLED=True)
def test_dev_login_signs_in_test_customer_in_development(api, seeded):
    info = api.get("/api/v1/auth/dev-login").json()
    assert info["customer"]["customerCode"] == "CLK-CS-TEST001"
    r = api.post("/api/v1/auth/dev-login")
    assert r.status_code == 200 and r.json()["user"]["customerCode"] == "CLK-CS-TEST001"
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert api.get("/api/v1/customer/orders").json()["count"] == 20


def test_test_customer_can_use_normal_login_and_data_stays_isolated(api, seeded, other_customer):
    r = api.post("/api/v1/auth/login", {"email": TEST_CUSTOMER["email"], "password": TEST_CUSTOMER["password"]})
    assert r.status_code == 200
    api.force_authenticate(other_customer)
    assert api.get("/api/v1/customer/orders").json()["count"] == 0
    assert api.get("/api/v1/customer/bookings").json()["count"] == 0
    assert api.get("/api/v1/customer/wallet").json()["balance"] == "0.00"
