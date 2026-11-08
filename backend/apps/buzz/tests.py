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
