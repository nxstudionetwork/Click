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


def test_seed_dev_data_catalog_is_idempotent(api):
    call_command("seed_dev_data", "--catalog-only")
    call_command("seed_dev_data", "--catalog-only")
    assert api.get("/api/v1/stores?type=restaurant").json()["count"] == 20
    assert api.get("/api/v1/stores?type=grocery").json()["count"] == 5
    assert api.get("/api/v1/stores?type=retail").json()["count"] == 12  # Shopping sellers (devseed.shop)
    assert api.get("/api/v1/offers?page_size=50").json()["count"] == 23  # incl. 3 redeemable Shopping seller offers
    assert api.get("/api/v1/events?kind=movie&page_size=50").json()["count"] == 20
    assert api.get("/api/v1/events?kind=event&page_size=50").json()["count"] == 20


def test_near_query_returns_only_located_stores_within_radius_nearest_first(api):
    from decimal import Decimal as D

    make_store("Far Away", latitude=D("13.100000"), longitude=D("77.600000"))  # ~15 km
    make_store("Close", latitude=D("12.972500"), longitude=D("77.641500"))
    make_store("Closest", latitude=D("12.971950"), longitude=D("77.641250"))
    make_store("Unknown Place")  # no coordinates: never claimed as near
    r = api.get("/api/v1/stores?lat=12.9719&lng=77.6412&radius=5")
    assert r.status_code == 200
    rows = r.json()["results"]
    assert [s["name"] for s in rows] == ["Closest", "Close"]
    assert rows[0]["distanceKm"] == 0.0 and rows[1]["distanceKm"] < 1
    # Without a location there is no distance at all.
    assert all(s["distanceKm"] is None for s in api.get("/api/v1/stores").json()["results"])


def test_near_query_validates_coordinates(api):
    r = api.get("/api/v1/stores?lat=120&lng=77")
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"
    assert api.get("/api/v1/stores?lat=12.9").status_code == 400  # lng required with lat


def test_store_sorting(api):
    make_store("Quiet", rating_count=3)
    make_store("Busy", rating_count=900)
    names = [s["name"] for s in api.get("/api/v1/stores?sort=popular").json()["results"]]
    assert names.index("Busy") < names.index("Quiet")
