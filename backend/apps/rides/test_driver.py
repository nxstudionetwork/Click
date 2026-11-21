"""Click Partner — Driver mode: request expiry, cancellation, no-show, rating riders, safety, documents, profile, earnings."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.partners.documents import review
from apps.partners.models import PartnerDocument
from apps.partners.test_home import book, cab, make_driver, make_partner, partner_catalog  # noqa: F401 (fixtures)
from apps.rides.driver import expire_stale_offers
from apps.rides.models import Ride, RideDriverOffer, RideRiderRating, RideSafetyEvent, RideStatusEvent

pytestmark = pytest.mark.django_db
D = "/api/v1/partner/driver"
W = "/api/v1/partner/work/ride"


def test_driver_tools_are_only_for_ride_partners(api):
    assert api.get(f"{D}/profile").status_code == 401
    _, shop = make_partner("restaurant", "chef@click.test")
    assert shop.get(f"{D}/profile").json()["error"]["code"] == "not_driver"


def test_unanswered_request_expires_and_passes_on(cab, auth_api):
    first, first_client = make_driver("d1@click.test")
    second, _ = make_driver("d2@click.test", lat=12.9800)
    ride = book(auth_api)
    RideDriverOffer.objects.filter(ride_id=ride["id"], driver=second).delete()  # only the first driver was offered it
    req = first_client.get("/api/v1/partner/home").json()["actionRequired"]["data"][0]
    assert req["deadline"]  # the app counts down to this

    RideDriverOffer.objects.filter(ride_id=ride["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
    r = first_client.post(f"{W}/{ride['id']}/accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_expired"
    assert expire_stale_offers() == 1
    assert RideDriverOffer.objects.get(ride_id=ride["id"], driver=first).response == "expired"
    assert RideDriverOffer.objects.filter(ride_id=ride["id"], driver=second, response="pending").exists()  # passed on
    assert first_client.get("/api/v1/partner/home").json()["actionRequired"]["data"] == []


def test_driver_cancel_finds_the_rider_another_driver(cab, auth_api):
    first, client = make_driver("d1@click.test")
    second, second_client = make_driver("d2@click.test", lat=12.9800)
    ride = book(auth_api)
    assert client.post(f"{W}/{ride['id']}/accept").status_code == 200
    assert client.post(f"{W}/{ride['id']}/cancel", {"reason": ""}, format="json").status_code == 400
    assert client.post(f"{W}/{ride['id']}/cancel", {"reason": "Vehicle problem"}, format="json").status_code == 200
    r = Ride.objects.get(pk=ride["id"])
    assert r.status == "searching" and r.driver_id is None
    assert auth_api.get(f"/api/v1/customer/rides/{ride['id']}").json()["status"] == "searching"
    # The cancelling driver isn't offered it again; the other driver is.
    assert RideDriverOffer.objects.filter(ride_id=ride["id"], driver=second, response="pending").exists()
    assert not RideDriverOffer.objects.filter(ride_id=ride["id"], driver=first, response="pending").exists()
    assert client.get(f"{D}/profile").json()["stats"]["cancelledByYou"] == 1


def test_rider_no_show_only_after_waiting(cab, auth_api):
    _, client = make_driver("d1@click.test")
    ride = book(auth_api)
    client.post(f"{W}/{ride['id']}/accept")
    assert client.post(f"{W}/{ride['id']}/no_show").json()["error"]["code"] == "invalid_transition"
    arrived = client.post(f"{W}/{ride['id']}/arrived").json()["item"]
    assert "no_show" not in [a["key"] for a in arrived["actions"]]  # not offered while it would be refused
    assert client.post(f"{W}/{ride['id']}/no_show").json()["error"]["code"] == "too_early"
    RideStatusEvent.objects.filter(ride_id=ride["id"], to_status="driver_arrived").update(created_at=timezone.now() - timedelta(minutes=6))
    active = client.get("/api/v1/partner/home").json()["active"]["data"]
    assert "no_show" in [a["key"] for a in active[0]["actions"]]
    assert client.post(f"{W}/{ride['id']}/no_show").status_code == 200
    assert auth_api.get(f"/api/v1/customer/rides/{ride['id']}").json()["status"] == "cancelled"


def test_rating_the_rider_safety_and_history(cab, auth_api):
    driver, client = make_driver("d1@click.test")
    _, other = make_driver("d2@click.test", lat=12.99)
    ride = book(auth_api)
    for a in ("accept", "arrived", "start"):
        client.post(f"{W}/{ride['id']}/{a}")
    sos = client.post(f"{D}/trips/{ride['id']}/safety", {"kind": "sos"}, format="json")
    assert sos.status_code == 201 and sos.json()["emergencyNumber"] == "112"
    assert RideSafetyEvent.objects.get(ride_id=ride["id"]).reported_by == "driver"
    assert other.post(f"{D}/trips/{ride['id']}/safety", {"kind": "sos"}, format="json").status_code == 404  # not their ride

    assert client.post(f"{D}/trips/{ride['id']}/rate-rider", {"stars": 5}, format="json").status_code == 409  # not finished
    client.post(f"{W}/{ride['id']}/complete")
    assert client.post(f"{D}/trips/{ride['id']}/rate-rider", {"stars": 9}, format="json").status_code == 400
    assert client.post(f"{D}/trips/{ride['id']}/rate-rider", {"stars": 4}, format="json").status_code == 201
    assert client.post(f"{D}/trips/{ride['id']}/rate-rider", {"stars": 4}, format="json").status_code == 409
    assert RideRiderRating.objects.get(ride_id=ride["id"]).stars == 4

    [trip] = client.get(f"{D}/trips").json()["results"]
    assert trip["number"] == ride["number"] and trip["riderRated"] == 4 and trip["canRateRider"] is False
    assert other.get(f"{D}/trips").json()["total"] == 0

    earn = {p["key"]: p for p in client.get(f"{D}/earnings").json()["periods"]}
    assert earn["today"]["trips"] == 1 and earn["today"]["cashCollected"] == earn["today"]["total"]
    assert earn["week"]["trips"] == 1


def test_expired_licence_blocks_going_online_and_matching(cab, auth_api):
    driver, client = make_driver("d1@click.test")
    docs = {d["key"]: d for d in client.get("/api/v1/partner/documents").json()["documents"]}
    assert docs["driving_licence"]["state"] == "missing" and docs["driving_licence"]["expires"] is True
    assert client.post("/api/v1/partner/documents", {"key": "driving_licence", "number": "KA01 2019 0012345",
                                                     "expiresOn": "2020-01-01"}, format="json").status_code == 400
    soon = (timezone.localdate() + timedelta(days=400)).isoformat()
    r = client.post("/api/v1/partner/documents", {"key": "driving_licence", "number": "KA01 2019 0012345", "expiresOn": soon}, format="json")
    assert r.status_code == 201
    lic = next(d for d in r.json()["documents"] if d["key"] == "driving_licence")
    assert lic["state"] == "pending" and lic["number"] == "•••• 2345"  # never shown back in full

    doc = PartnerDocument.objects.get(partner=driver, key="driving_licence")
    review(doc, True)
    PartnerDocument.objects.filter(pk=doc.pk).update(expires_on=timezone.localdate() - timedelta(days=1))
    home = client.get("/api/v1/partner/home").json()
    assert home["availability"]["canChange"] is False and "expired" in home["availability"]["blockedReason"]
    assert client.post("/api/v1/partner/availability", {"available": True}).status_code == 409
    ride = book(auth_api)
    assert not RideDriverOffer.objects.filter(ride_id=ride["id"], driver=driver).exists()  # kept out of matching


def test_profile_shows_exactly_what_riders_see(cab, auth_api):
    driver, client = make_driver("d1@click.test")
    p = client.get(f"{D}/profile").json()
    assert p["vehicle"]["typeLabel"] == "Car / Cab" and "Cab" in p["vehicle"]["rideTypes"]
    ride = book(auth_api)
    client.post(f"{W}/{ride['id']}/accept")
    seen = auth_api.get(f"/api/v1/customer/rides/{ride['id']}").json()["driver"]
    assert {k: seen[k] for k in p["public"]} == p["public"]
