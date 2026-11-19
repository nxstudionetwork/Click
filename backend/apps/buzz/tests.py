import pytest

from apps.stores.models import StoreOffer
from conftest import make_store

pytestmark = pytest.mark.django_db


def test_buzz_feed_is_built_from_real_actionable_records(api):
    s = make_store("Buzz Kitchen", rating_count=120)
    StoreOffer.objects.create(store=s, title="20% off biryani")
    make_store("Closed Kitchen", rating_count=50, is_accepting_orders=False)
    r = api.get("/api/v1/buzz")
    assert r.status_code == 200
    items = r.json()["results"]
    assert {i["kind"] for i in items} == {"offer", "store"}
    offer = next(i for i in items if i["kind"] == "offer")
    assert offer["title"] == "20% off biryani"
    assert offer["action"] == {"label": "Order now", "path": "/stores/buzz-kitchen"}
    assert offer["source"]["handle"] == "buzz-kitchen" and offer["theme"] == "food"
    assert offer["mediaUrl"] == "" and offer["mediaType"] == ""  # no image is ever invented
    assert all(i["source"]["handle"] != "closed-kitchen" for i in items)  # can't act on it right now


def test_buzz_feed_empty_and_limits(api):
    assert api.get("/api/v1/buzz").json() == {"results": []}
    assert api.get("/api/v1/buzz?limit=0").status_code == 400
    assert api.get("/api/v1/buzz?limit=31").status_code == 400


def test_every_store_type_has_a_theme_and_a_real_destination(api):
    from apps.stores.models import StoreType

    make_store("Care Pharmacy", store_type=StoreType.PHARMACY, rating_count=40)
    item = next(i for i in api.get("/api/v1/buzz").json()["results"] if i["title"] == "Care Pharmacy")
    assert item["action"] == {"label": "Shop pharmacy", "path": "/pharma"} and item["theme"] == "shopping"


def test_every_buzz_item_can_be_liked_and_saved(auth_api):
    import uuid

    from rest_framework.test import APIClient

    key = f"offer:{uuid.uuid4()}"
    r = auth_api.post(f"/api/v1/buzz/items/{key}/like")
    assert r.status_code == 200 and r.json() == {"on": True, "count": 1}
    assert auth_api.post(f"/api/v1/buzz/items/{key}/like").json() == {"on": False, "count": 0}
    assert auth_api.post(f"/api/v1/buzz/items/{key}/save").json()["on"] is True
    assert auth_api.post("/api/v1/buzz/items/nonsense:1/like").status_code == 404
    assert APIClient().post(f"/api/v1/buzz/items/{key}/like").status_code == 401


def test_feed_items_carry_real_engagement(auth_api):
    for item in auth_api.get("/api/v1/buzz", {"limit": 30}).json()["results"]:
        assert set(item["engage"]) == {"likes", "liked", "saved"}
