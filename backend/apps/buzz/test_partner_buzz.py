"""Click. Buzz for partners: posts link only to the partner's own live listings, Click reviews them, customers engage."""

from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.buzz import partner as pb
from apps.buzz.models import BuzzPost, BuzzReport
from apps.partners.models import Partner, PartnerStore
from apps.partners.test_home import cab, make_driver, make_partner, partner_catalog, restaurant  # noqa: F401 (fixtures)
from conftest import make_customer, make_store

pytestmark = pytest.mark.django_db
B = "/api/v1/partner/buzz"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def png(w=1600, h=900):
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (w, h), (200, 80, 40)).save(buf, "PNG")
    return SimpleUploadedFile("dish.png", buf.getvalue(), content_type="image/png")


def week():
    return (timezone.now() + timedelta(days=7)).isoformat()


def feed_posts(api):
    return [i for i in api.get("/api/v1/buzz?limit=30").json()["results"] if i["kind"] == "post"]


def new_post(client, store, **extra):
    body = {"headline": "New Special Chicken Biryani — ₹199 today", "caption": "Slow-cooked, only today.", "kind": "new_item",
            "targetType": "store", "targetId": str(store.id), "cta": "order", "expiresAt": week(), **extra}
    return client.post(B, body, format="json")


def test_post_is_reviewed_then_reaches_customers_with_a_real_action(restaurant, store, products, api):
    _, client = restaurant
    overview = client.get(B).json()
    assert overview["listings"][0] == {"type": "store", "id": str(store.id), "title": store.name, "link": f"/stores/{store.slug}",
                                       "ctas": ["order", "view_menu", "get_offer"], "handle": store.slug}
    assert [p["name"] for p in overview["products"]] == ["Dal", "Naan", "Sold out"]

    media = client.post(f"{B}/media", {"file": png()}, format="multipart")
    assert media.status_code == 201, media.content
    m = media.json()
    assert m["kind"] == "image" and m["url"].endswith("-1080.webp") and m["thumb"].endswith("-480.webp") and m["width"] == 1600

    r = new_post(client, store, productId=str(products[0].id), mediaIds=[m["id"]], submit=True)
    assert r.status_code == 201, r.content
    post = r.json()
    assert post["status"] == "in_review" and post["product"]["name"] == "Dal" and post["link"] == f"/stores/{store.slug}"
    assert feed_posts(api) == []  # nothing public before Click approves it

    pb.review(BuzzPost.objects.get(pk=post["id"]), True)
    item = feed_posts(api)[0]
    assert item["action"] == {"label": "Order now", "path": f"/stores/{store.slug}"}
    assert item["mediaType"] == "image" and item["mediaUrl"].endswith("-1080.webp")
    assert item["post"]["item"] == {"name": "Dal", "price": "120.00", "available": True} and item["theme"] == "food"
    assert client.get(B).json()["posts"][0]["status"] == "live"

    # Availability follows the menu; editing sends the post back to review (and off the feed).
    products[0].is_available = False
    products[0].save()
    assert feed_posts(api)[0]["post"]["item"]["available"] is False
    edited = client.patch(f"{B}/{post['id']}", {"caption": "Now with raita"}, format="json").json()
    assert edited["status"] == "in_review" and feed_posts(api) == []


def test_posts_only_link_to_own_listings_and_stay_private(restaurant, store, products, api):
    partner, client = restaurant
    other_store = make_store("Other Kitchen")
    other, other_client = make_partner("restaurant", "other@click.test")
    PartnerStore.objects.create(partner=other, store=other_store)

    bad = new_post(client, other_store)
    assert bad.status_code == 400 and "targetType" in bad.json()["error"]["details"]
    from apps.catalog.models import Product

    foreign = Product.objects.create(store=other_store, name="Theirs", price="10")
    assert "productId" in new_post(client, store, productId=str(foreign.id)).json()["error"]["details"]
    assert "offerId" in new_post(client, store, kind="offer").json()["error"]["details"]  # offer post needs a live offer
    assert "expiresAt" in new_post(client, store, expiresAt=(timezone.now() + timedelta(days=120)).isoformat()).json()["error"]["details"]

    post = new_post(client, store).json()
    assert post["status"] == "draft"
    for call in (other_client.patch(f"{B}/{post['id']}", {"caption": "x"}, format="json"), other_client.post(f"{B}/{post['id']}/submit"),
                 other_client.delete(f"{B}/{post['id']}")):
        assert call.status_code == 404
    assert other_client.get(B).json()["posts"] == []
    m = client.post(f"{B}/media", {"file": png()}, format="multipart").json()
    assert "mediaIds" in other_client.post(B, {"headline": "x", "targetType": "store", "targetId": str(other_store.id), "cta": "order",
                                                "expiresAt": week(), "mediaIds": [m["id"]]}, format="json").json()["error"]["details"]

    # Unverified partners can draft but not submit.
    Partner.objects.filter(pk=partner.pk).update(status=Partner.Status.VERIFICATION_PENDING)
    r = client.post(f"{B}/{post['id']}/submit")
    assert r.status_code == 409 and r.json()["error"]["code"] == "partner_not_verified"


def test_lifecycle_media_rules_and_scheduling(restaurant, store, products):
    _, client = restaurant
    assert client.post(f"{B}/media", {"file": SimpleUploadedFile("a.txt", b"hello there", content_type="text/plain")},
                       format="multipart").json()["error"]["code"] == "image_invalid"
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
    v1 = client.post(f"{B}/media", {"file": SimpleUploadedFile("a.mp4", mp4, content_type="video/mp4")}, format="multipart").json()
    v2 = client.post(f"{B}/media", {"file": SimpleUploadedFile("b.mp4", mp4, content_type="video/mp4")}, format="multipart").json()
    assert v1["kind"] == "video" and v1["url"].endswith(".mp4")
    assert "mediaIds" in new_post(client, store, mediaIds=[v1["id"], v2["id"]]).json()["error"]["details"]  # one video per post

    later = (timezone.now() + timedelta(days=2)).isoformat()
    post = new_post(client, store, mediaIds=[v1["id"]], publishAt=later, submit=True).json()
    pb.review(BuzzPost.objects.get(pk=post["id"]), True)
    assert client.get(B).json()["posts"][0]["status"] == "scheduled"
    assert client.post(f"{B}/{post['id']}/resume").status_code == 409  # not paused
    assert client.post(f"{B}/{post['id']}/pause").json()["status"] == "paused"
    assert client.post(f"{B}/{post['id']}/resume").json()["status"] == "scheduled"
    assert client.post(f"{B}/{post['id']}/archive").json()["status"] == "archived"
    assert client.post(f"{B}/{post['id']}/restore").json()["status"] == "draft"
    assert client.delete(f"{B}/{post['id']}").status_code == 204
    assert not BuzzPost.objects.exists()
    assert pb.cleanup_unused_media(older_than=timedelta(0)) == 1  # v2 was never attached


def test_engagement_counts_once_and_reports_go_to_moderation(restaurant, store, products, api):
    partner, client = restaurant
    post = new_post(client, store, submit=True).json()
    pb.review(BuzzPost.objects.get(pk=post["id"]), True)
    P = f"/api/v1/buzz/posts/{post['id']}"
    assert api.post(f"{P}/like").status_code == 401
    assert api.post(f"{P}/event", {"kind": "view"}, format="json").json() == {"counted": True}
    assert api.post(f"{P}/event", {"kind": "view"}, format="json").json() == {"counted": False}  # same viewer, same day
    api.post(f"{P}/event", {"kind": "click"}, format="json")

    api.force_authenticate(make_customer("fan@click.test"))
    assert api.post(f"{P}/like").json() == {"on": True, "count": 1}
    assert api.post(f"{P}/save").json() == {"on": True, "count": 1}
    assert feed_posts(api)[0]["post"]["liked"] is True
    assert api.post(f"{P}/report", {"reason": "misleading", "note": "Price is wrong"}, format="json").status_code == 201
    assert client.post(f"{P}/report", {"reason": "spam"}, format="json").json()["error"]["code"] == "own_post"

    stats = client.get(B).json()["posts"][0]["stats"]
    assert stats == {"views": 1, "ctaClicks": 1, "likes": 1, "saves": 1, "ctr": 100.0, "openReports": 1}
    pb.remove(BuzzPost.objects.get(pk=post["id"]), "Removed after a report.")
    BuzzReport.objects.update(status="upheld")
    assert feed_posts(api) == [] and api.post(f"{P}/like").status_code == 404
    assert client.get(B).json()["posts"][0]["actions"] == ["delete"]
    assert partner.notifications.filter(title="Buzz post removed").exists()


def test_drivers_promote_ride_booking(cab):
    driver, client = make_driver("ravi@click.test")
    listing = client.get(B).json()["listings"]
    assert listing == [{"type": "ride", "id": "", "title": "Click rides", "link": "/rides", "ctas": ["book_ride"], "handle": "partner-biz"}]
    post = client.post(B, {"headline": "Airport rides available today", "targetType": "ride", "targetId": "", "cta": "book_ride",
                           "expiresAt": week(), "submit": True}, format="json")
    assert post.status_code == 201 and post.json()["ctaLabel"] == "Book a ride"
