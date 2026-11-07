import pytest
from django.core.management import call_command

from apps.stores.models import Store
from conftest import make_store

pytestmark = pytest.mark.django_db


def test_store_list_uses_camelcase_contract_and_hides_non_active(api, store):
    make_store("Hidden Draft", status=Store.Status.DRAFT)
    r = api.get("/api/v1/stores?type=restaurant")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    item = body["results"][0]
    for key in ["id", "slug", "name", "storeType", "imageUrl", "ratingAverage", "deliveryTimeMin", "isOpen", "offers"]:
        assert key in item


def test_store_search_matches_product_names(api, products):
    assert api.get("/api/v1/stores?search=naan").json()["count"] == 1
    assert api.get("/api/v1/stores?search=sushi").json()["count"] == 0


def test_store_detail_404_for_inactive(api):
    make_store("Gone", status=Store.Status.SUSPENDED)
    assert api.get("/api/v1/stores/gone").status_code == 404


def test_menu_groups_products_and_hides_inactive(api, store, products):
    products[1].is_active = False
    products[1].save()
    r = api.get(f"/api/v1/stores/{store.slug}/menu")
    assert r.status_code == 200
    names = [p["name"] for c in r.json()["categories"] for p in c["products"]]
    assert names == ["Dal", "Sold out"]  # unavailable is shown (greyed out), inactive is hidden


def test_seed_dev_data_is_idempotent(api):
    call_command("seed_dev_data")
    call_command("seed_dev_data")
    assert api.get("/api/v1/stores?type=restaurant").json()["count"] == 10
