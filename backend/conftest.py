from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import MenuCategory, Product
from apps.customers.models import Address, CustomerProfile
from apps.stores.models import Store, StoreType
from apps.users.models import User


@pytest.fixture
def api():
    return APIClient()


def make_customer(email="asha@example.com"):
    user = User.objects.create_user(email, "S3cure-pass-123", full_name="Asha")
    CustomerProfile.objects.create(user=user)
    return user


@pytest.fixture
def customer(db):
    return make_customer()


@pytest.fixture
def other_customer(db):
    return make_customer("ravi@example.com")


@pytest.fixture
def auth_api(api, customer):
    api.force_authenticate(customer)
    return api


def make_store(name="Test Kitchen", **kw):
    defaults = dict(
        store_type=StoreType.RESTAURANT, status=Store.Status.ACTIVE, city="Bengaluru",
        delivery_fee=Decimal("30.00"), min_order_amount=Decimal("100.00"),
    )
    defaults.update(kw)
    return Store.objects.create(name=name, slug=name.lower().replace(" ", "-"), **defaults)


@pytest.fixture
def store(db):
    return make_store()


@pytest.fixture
def products(store):
    cat = MenuCategory.objects.create(store=store, name="Mains")
    return [
        Product.objects.create(store=store, category=cat, name="Dal", price=Decimal("120.00")),
        Product.objects.create(store=store, category=cat, name="Naan", price=Decimal("40.00")),
        Product.objects.create(store=store, category=cat, name="Sold out", price=Decimal("90.00"), is_available=False),
    ]


@pytest.fixture
def address(customer):
    return Address.objects.create(
        customer=customer.customer_profile, recipient_name="Asha", phone="+91 98765 43210",
        line1="12 MG Road", city="Bengaluru", postal_code="560001", is_default=True,
    )
