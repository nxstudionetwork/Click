"""Pharma: OTC items use the normal cart and checkout; prescription-only items can't be ordered until the pharmacy's
own pharmacist verifies the customer's prescription (never automatically); a prescription is used once; files are
private; quantity limits hold."""

import uuid
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.catalog.models import MenuCategory, Product
from apps.pharma.models import Prescription
from apps.stores.models import Store
from conftest import make_customer

pytestmark = pytest.mark.django_db


@pytest.fixture
def pharmacy(db):
    s = Store.objects.create(store_type="pharmacy", status="active", name="Test Pharmacy", slug="test-pharmacy", city="Bengaluru", min_order_amount=D("0"))
    cat = MenuCategory.objects.create(store=s, name="Medicines")
    otc = Product.objects.create(store=s, category=cat, name="Paracetamol 500 mg", price=D("30"), health_category="otc", max_per_order=3)
    rx = Product.objects.create(store=s, category=cat, name="Amoxicillin 500 mg", price=D("90"), health_category="medicines", requires_prescription=True)
    return s, otc, rx


def pharmacist(store):
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerStore, PartnerType

    if not PartnerType.objects.exists():
        apply_catalog(PartnerType, PartnerCategory)
    cat = PartnerCategory.objects.first()
    p = Partner.objects.create(business_name="Test Pharmacy LLP", status="active", category=cat, partner_type=cat.partner_type)
    PartnerStore.objects.create(partner=p, store=store)
    u = make_customer("pharmacist@example.com")
    PartnerMembership.objects.create(partner=p, user=u)
    c = APIClient()
    c.force_authenticate(u)
    return c


def order(api, address):
    return api.post("/api/v1/customer/orders", {"addressId": str(address.id), "paymentMethod": "cash_on_delivery", "idempotencyKey": str(uuid.uuid4())})


def upload(api, store):
    f = SimpleUploadedFile("rx.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, content_type="image/png")
    return api.post("/api/v1/customer/pharma/prescriptions", {"file": f, "pharmacyId": str(store.id), "note": "As prescribed"}, format="multipart")


def test_prescription_items_need_a_pharmacist_verified_prescription(auth_api, customer, other_customer, address, pharmacy, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    store, otc, rx = pharmacy
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(rx.id), "quantity": 1})
    assert order(auth_api, address).json()["error"]["code"] == "prescription_required"
    r = upload(auth_api, store)
    assert r.status_code == 201 and r.json()["status"] == "under_review"  # never approved automatically
    rid = r.json()["id"]
    assert auth_api.post("/api/v1/customer/cart/prescription", {"prescriptionId": rid}).json()["error"]["code"] == "rx_not_verified"
    stranger = APIClient()
    stranger.force_authenticate(other_customer)
    assert stranger.post(f"/api/v1/partner/pharma/prescriptions/{rid}/review", {"outcome": "verified"}).status_code == 404
    assert stranger.get(f"/api/v1/pharma/prescriptions/{rid}/file").status_code == 404
    ph = pharmacist(store)
    assert ph.get(f"/api/v1/pharma/prescriptions/{rid}/file").status_code == 200
    assert ph.post(f"/api/v1/partner/pharma/prescriptions/{rid}/review", {"outcome": "verified", "note": "OK"}, format="json").json()["status"] == "verified"
    assert auth_api.get("/api/v1/customer/cart").json()["prescription"]["available"]["id"] == rid
    auth_api.post("/api/v1/customer/cart/prescription", {"prescriptionId": rid})
    placed = order(auth_api, address)
    assert placed.status_code == 201, placed.content
    assert Prescription.objects.get(pk=rid).status == "used"
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(rx.id), "quantity": 1})
    assert order(auth_api, address).json()["error"]["code"] == "prescription_required"  # used once


def test_otc_orders_normally_with_limits_and_bad_files_rejected(auth_api, address, pharmacy, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    store, otc, rx = pharmacy
    assert auth_api.post("/api/v1/customer/cart/items", {"productId": str(otc.id), "quantity": 4}).json()["error"]["code"] == "quantity_limit"
    auth_api.post("/api/v1/customer/cart/items", {"productId": str(otc.id), "quantity": 2})
    assert order(auth_api, address).status_code == 201
    bad = SimpleUploadedFile("rx.png", b"<html>not an image</html>", content_type="image/png")
    r = auth_api.post("/api/v1/customer/pharma/prescriptions", {"file": bad, "pharmacyId": str(store.id)}, format="multipart")
    assert r.json()["error"]["code"] == "file_type"
    home = APIClient().get("/api/v1/pharma/home").json()
    assert home["pharmacies"][0]["name"] == "Test Pharmacy" and "doesn’t give medical advice" in home["disclaimer"]
