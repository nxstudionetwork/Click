"""Click. Travel: search validation, filters / sorts / highlights, bus seats (sold once, ladies seats), train berths →
RAC → waitlist and promotion on cancellation, flight fares that move with load (fare changed → confirm again), wallet
payment failure / retry / hold expiry, idempotency, tickets only after payment, policy-based cancellation and refunds,
operator changes, ownership, recent searches, saved routes, travellers, price alerts, the central bookings list."""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.travel import booking, engine
from apps.travel.models import FareClass, Journey, Operator, Passenger, Place, Service, Stop, TravelBooking
from apps.wallet.models import WalletTransaction
from apps.wallet.services import balance
from conftest import make_customer

pytestmark = pytest.mark.django_db
CUST = "/api/v1/customer/travel"


def place(kind, name, slug, city=None, code=""):
    return Place.objects.create(kind=kind, name=name, slug=slug, city=city, code=code)


@pytest.fixture
def net(db):
    hyd, dl, vij = place("city", "Hyderabad", "hyderabad"), place("city", "Delhi", "delhi"), place("city", "Vijayawada", "vijayawada")
    p = {"hyd": hyd, "dl": dl, "vij": vij, "HYD": place("airport", "Rajiv Gandhi International Airport", "hyd-air", hyd, "HYD"),
         "DEL": place("airport", "Indira Gandhi International Airport", "del-air", dl, "DEL"), "SC": place("station", "Secunderabad Junction", "sc", hyd, "SC"),
         "BZA": place("station", "Vijayawada Junction", "bza", vij, "BZA"), "miy": place("bus_stop", "Miyapur", "miyapur", hyd),
         "amp": place("bus_stop", "Ameerpet", "ameerpet", hyd), "benz": place("bus_stop", "Benz Circle", "benz", vij)}
    bus_op = Operator.objects.create(mode="bus", name="Ridgeway Coaches")
    rail = Operator.objects.create(mode="train", name="Rail Partner")
    air = Operator.objects.create(mode="flight", name="Skyline Air", code="SK")
    rules = [{"hours": 24, "fee_percent": 0}, {"hours": 6, "fee_percent": 50}]
    layout = {"decks": [{"name": "Seats", "rows": [["1", "2", None, "3", "4"]]}],
              "seats": {"1": {"class": "seater", "ladies": True}, "2": {"class": "seater"}, "3": {"class": "seater"}, "4": {"class": "sleeper"}}}

    def svc(op, mode, number, stops, classes, **kw):
        s = Service.objects.create(operator=op, mode=mode, number=number, name=number, running_days=list(range(7)), cancellation=rules, **kw)
        for i, (pl, arr, dep, day, km) in enumerate(stops):
            Stop.objects.create(service=s, place=pl, seq=i + 1, arrive=arr, depart=dep, day=day, km=km, boarding=dep is not None, dropping=arr is not None)
        for i, c in enumerate(classes):
            FareClass.objects.create(service=s, position=i, **c)
        return s

    bus = svc(bus_op, "bus", "RID-1", [(p["miy"], None, time(22, 0), 0, 0), (p["amp"], None, time(22, 20), 0, 6), (p["benz"], time(4, 0), None, 1, 275)],
              [{"code": "seater", "name": "Seat", "capacity": 3, "base_fare": D("500"), "tax_percent": D("5")},
               {"code": "sleeper", "name": "Sleeper", "capacity": 1, "base_fare": D("800"), "tax_percent": D("5")}],
              bus_type="seater_sleeper", ac=True, seat_layout=layout, amenities=["Charging point", "Blanket"])
    train = svc(rail, "train", "12711", [(p["SC"], None, time(7, 0), 0, 0), (p["BZA"], time(12, 30), None, 0, 351)],
                [{"code": "3A", "name": "AC 3 Tier", "capacity": 1, "rac_capacity": 1, "waitlist_limit": 1, "per_km": D("1.2"), "min_fare": D("300"),
                  "reservation_charge": D("40"), "tax_percent": D("5")}], vehicle="Superfast")
    flight = svc(air, "flight", "SK 512", [(p["HYD"], None, time(6, 20), 0, 0), (p["DEL"], time(8, 35), None, 0, 1255)],
                 [{"code": "economy", "name": "Economy", "fare_type": "Saver", "capacity": 4, "base_fare": D("4500"), "infant_fare": D("1500"), "tax_percent": D("5")}],
                 baggage={"cabin": "7 kg", "check_in": "15 kg"})
    return {"p": p, "bus": bus, "train": train, "flight": flight}


def day(n=10):
    return (engine.today() + timedelta(days=n)).isoformat()


def fund(user, amount="100000"):
    WalletTransaction.objects.create(customer=user.customer_profile, kind="topup", amount=D(amount), description="Test top-up")


def client(user):
    c = APIClient(SERVER_NAME="localhost")
    c.force_authenticate(user)
    return c


def search(api, mode, origin, dest, d=None, **extra):
    return api.get("/api/v1/travel/search", {"mode": mode, "origin": origin, "destination": dest, "date": d or day(), **extra})


def pax(n=1, gender="male", age=30):
    return [{"name": f"Traveller {chr(65 + i)}", "age": age, "gender": gender} for i in range(n)]


def body(o, cls, passengers, **extra):
    return {"journeyId": o["journeyId"], "fromStopId": o["fromStopId"], "toStopId": o["toStopId"], "classCode": cls, "passengers": passengers, **extra}


def book(api, o, cls, passengers, **extra):
    review = api.post(f"{CUST}/review", body(o, cls, passengers, **{k: v for k, v in extra.items() if k in ("seats", "infants", "coupon")}), format="json").json()
    return api.post(f"{CUST}/bookings", {**body(o, cls, passengers, **extra), "contactPhone": "+91 98765 43210", "expectedTotal": review.get("total"),
                                         "idempotencyKey": extra.pop("key", str(uuid.uuid4()))}, format="json")


def test_search_validation(api, net):
    assert search(api, "bus", "hyderabad", "hyderabad").status_code == 400  # same city
    assert search(api, "bus", "miyapur", "hyderabad").status_code == 400  # a point inside the same city
    assert search(api, "bus", "nowhere", "delhi").status_code == 400
    past = (engine.today() - timedelta(days=1)).isoformat()
    assert search(api, "bus", "hyderabad", "vijayawada", past).status_code == 400
    assert search(api, "flight", "hyderabad", "delhi", return_date=(engine.today() + timedelta(days=2)).isoformat()).status_code == 400
    assert search(api, "bus", "hyderabad", "vijayawada", infants=1).status_code == 400
    places = api.get("/api/v1/travel/places", {"q": "hyd", "mode": "flight"}).json()["results"]
    assert [p["label"] for p in places][:2] == ["Hyderabad — City", "Rajiv Gandhi International Airport — Airport (HYD)"]


def test_results_filters_sort_and_alternatives(api, net):
    r = search(api, "bus", "hyderabad", "vijayawada").json()
    assert r["count"] == 1
    o = r["results"][0]
    assert [b["name"] for b in o["boardingPoints"]] == ["Miyapur", "Ameerpet"] and o["droppingPoints"][0]["name"] == "Benz Circle"
    assert o["durationMinutes"] == 360 and o["daysLater"] == 1 and o["seatsLeft"] == 4
    assert o["classes"][0]["perPerson"] == "525.00"  # 500 + 5% GST
    assert "cheapest" in o["highlights"] and "fastest" in o["highlights"]
    assert search(api, "bus", "hyderabad", "vijayawada", bus_type="non_ac").json()["count"] == 0
    assert search(api, "bus", "hyderabad", "vijayawada", bus_type="sleeper", departure="night").json()["count"] == 1
    assert search(api, "bus", "hyderabad", "vijayawada", amenities="Wi-Fi").json()["count"] == 0
    assert search(api, "bus", "hyderabad", "vijayawada", boarding=str(net["p"]["amp"].id)).json()["count"] == 1
    none = search(api, "bus", "hyderabad", "delhi").json()
    assert none["count"] == 0 and [a["mode"] for a in none["alternatives"]] == ["flight"]  # only what really exists
    dates = api.get("/api/v1/travel/dates", {"mode": "flight", "origin": "hyderabad", "destination": "delhi", "date": day()}).json()["results"]
    assert len(dates) == 7 and all(d["lowest"] for d in dates)


def test_bus_seats_sold_once_ladies_rule_idempotent_ticket_and_ownership(net):
    a, b = make_customer("a@x.com"), make_customer("b@x.com")
    fund(a), fund(b)
    ca, cb = client(a), client(b)
    o = search(ca, "bus", "hyderabad", "vijayawada").json()["results"][0]
    seats = ca.get(f"/api/v1/travel/options/{o['journeyId']}/{o['fromStopId']}/{o['toStopId']}").json()["seatMap"]["seats"]
    assert seats["1"]["ladies"] and seats["4"]["kind"] == "sleeper" and seats["4"]["fare"] == "840.00"
    r = ca.post(f"{CUST}/review", body(o, "seater", pax(), seats=["1"]), format="json").json()
    assert not r["bookable"] and "women" in r["problem"]
    key = str(uuid.uuid4())
    first = book(ca, o, "seater", pax(2), seats=["2", "4"], key=key)
    assert first.status_code == 201 and first.json()["status"] == "confirmed" and first.json()["pnr"]
    assert first.json()["total"] == "1365.00"  # (500 + 800) × 1.05: each seat at its own class fare
    again = book(ca, o, "seater", pax(2), seats=["2", "4"], key=key)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]  # retry never books twice
    taken = book(cb, o, "seater", pax(), seats=["2"])
    assert taken.status_code == 409
    seats = cb.get(f"/api/v1/travel/options/{o['journeyId']}/{o['fromStopId']}/{o['toStopId']}").json()["seatMap"]["seats"]
    assert seats["2"]["status"] == "sold" and seats["3"]["status"] == "available"
    bid = first.json()["id"]
    ticket = ca.get(f"{CUST}/bookings/{bid}/ticket").json()
    assert ticket["pnr"] == first.json()["pnr"] and [p["seat"] for p in ticket["passengers"]] == ["2", "4"] and ticket["code"] is None
    assert cb.get(f"{CUST}/bookings/{bid}").status_code == 404 and cb.get(f"{CUST}/bookings/{bid}/ticket").status_code == 404
    assert APIClient().get(f"{CUST}/bookings/{bid}").status_code in (401, 403)


def test_train_berth_rac_waitlist_and_promotion(net):
    users = [make_customer(f"t{i}@x.com") for i in range(4)]
    for u in users:
        fund(u)
    o = search(client(users[0]), "train", "hyderabad", "vijayawada").json()["results"][0]
    assert o["classes"][0]["availability"]["label"] == "Available 1" and o["classes"][0]["perPerson"] == "483.00"  # 420 + 40, +5%
    statuses = []
    ids = []
    for u in users[:3]:
        r = book(client(u), o, "3A", pax(age=65)).json()
        statuses.append(r["passengers"][0]["status"])
        ids.append(r["id"])
    assert statuses == ["CNF", "RAC", "WL"]
    first = TravelBooking.objects.get(pk=ids[0]).passengers.get()
    assert first.seat == "B1-1"  # senior gets a lower berth
    full = book(client(users[3]), o, "3A", pax())
    assert full.status_code == 409 and "Not enough" in full.json()["error"]["message"]
    r = client(users[0]).post(f"{CUST}/bookings/{ids[0]}/cancel", {"reason": "Plans changed"}, format="json").json()
    assert r["status"] == "cancelled" and r["refunded"] == r["total"]  # more than 24 h ahead: free under the tiers
    assert TravelBooking.objects.get(pk=ids[1]).passengers.get().seat_status == "CNF"
    assert TravelBooking.objects.get(pk=ids[2]).passengers.get().seat_status == "RAC"
    assert Notification.objects.filter(customer=users[1].customer_profile, title__startswith="Your berth is confirmed").exists()


def test_flight_fare_moves_with_load_and_needs_reconfirmation(net):
    a = make_customer("f@x.com")
    fund(a)
    api = client(a)
    o = search(api, "flight", "hyderabad", "delhi", adults=1).json()["results"][0]
    review = api.post(f"{CUST}/review", body(o, "economy", pax()), format="json").json()
    other = make_customer("g@x.com")
    fund(other)
    assert book(client(other), o, "economy", pax(2)).status_code == 201  # load factor 2/4 → fare steps up
    stale = api.post(f"{CUST}/bookings", {**body(o, "economy", pax()), "contactPhone": "+91 98765 43210", "expectedTotal": review["total"],
                                          "idempotencyKey": str(uuid.uuid4())}, format="json")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "price_changed"
    new = stale.json()["error"]["details"]["review"]["total"]
    assert D(new) > D(review["total"]) and stale.json()["error"]["details"]["previous"] == review["total"]
    ok = api.post(f"{CUST}/bookings", {**body(o, "economy", pax()), "contactPhone": "+91 98765 43210", "expectedTotal": new,
                                       "idempotencyKey": str(uuid.uuid4())}, format="json")
    assert ok.status_code == 201 and ok.json()["total"] == new
    infants = api.post(f"{CUST}/review", body(o, "economy", pax(), infants=2), format="json").json()
    assert not infants["bookable"] and "infant" in infants["problem"]
    child = api.post(f"{CUST}/review", body(o, "economy", [{"name": "Baby", "age": 1, "gender": "female"}, *pax()]), format="json").json()
    assert "infant" in child["problem"]


def test_payment_failure_hold_retry_and_expiry(net):
    a = make_customer("p@x.com")
    api = client(a)
    o = search(api, "bus", "hyderabad", "vijayawada").json()["results"][0]
    r = book(api, o, "seater", pax(), seats=["3"])
    assert r.status_code == 201 and r.json()["status"] == "pending_payment" and r.json()["paymentError"] and not r.json()["pnr"]
    assert api.get(f"{CUST}/bookings/{r.json()['id']}/ticket").status_code == 409  # no ticket without payment
    fund(a)
    paid = api.post(f"{CUST}/bookings/{r.json()['id']}/pay").json()
    assert paid["status"] == "confirmed" and paid["pnr"] and balance(a.customer_profile) == D("100000") - D(paid["total"])
    r2 = book(api, o, "seater", pax(), seats=["2"])
    assert r2.json()["status"] == "confirmed"
    WalletTransaction.objects.all().delete()  # empty wallet
    r3 = book(api, o, "sleeper", pax(), seats=["4"])
    assert r3.json()["status"] == "pending_payment"
    TravelBooking.objects.filter(pk=r3.json()["id"]).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    booking.expire_holds()
    assert TravelBooking.objects.get(pk=r3.json()["id"]).status == "failed"
    j = Journey.objects.get(pk=o["journeyId"])
    assert "4" not in engine.sold_seats(j)  # released


def test_cancellation_tiers_and_operator_cancel(net):
    a = make_customer("c@x.com")
    fund(a)
    api = client(a)
    soon = search(api, "bus", "hyderabad", "vijayawada", (engine.today() + timedelta(days=0 if timezone.now().astimezone(engine.tz()).hour < 18 else 1)).isoformat()).json()
    if soon["results"]:  # inside 24 h → 50% fee under the tiers
        bk = book(api, soon["results"][0], "seater", pax(), seats=["3"]).json()
        detail = api.get(f"{CUST}/bookings/{bk['id']}").json()
        c = detail["cancellation"]
        within = datetime.fromisoformat(detail["departsAt"]) - timezone.now() <= timedelta(hours=24)
        assert c["allowed"] and c["feePercent"] == (50 if within else 0) and D(c["refund"]) == D(bk["total"]) * (D("0.5") if within else 1)
    o = search(api, "train", "hyderabad", "vijayawada").json()["results"][0]
    bk = book(api, o, "3A", pax()).json()
    n = booking.operator_update(Journey.objects.get(pk=o["journeyId"]), Journey.Status.CANCELLED)
    assert n == 1
    after = api.get(f"{CUST}/bookings/{bk['id']}").json()
    assert after["status"] == "cancelled" and after["refunded"] == after["total"] and after["refund"]["to"] == "Click. Wallet"
    assert search(api, "train", "hyderabad", "vijayawada").json()["results"][0]["available"] is False


def test_account_features_and_central_list(net, customer):
    fund(customer)
    api = client(customer)
    search(api, "bus", "hyderabad", "vijayawada")
    assert api.get(f"{CUST}/recent").json()["results"][0]["destination"]["slug"] == "vijayawada"
    assert api.delete(f"{CUST}/recent").status_code == 204 and api.get(f"{CUST}/recent").json()["results"] == []
    fav = api.post(f"{CUST}/routes", {"origin": "hyderabad", "destination": "delhi"}, format="json").json()["favoriteId"]
    assert search(api, "flight", "hyderabad", "delhi").json()["savedRouteId"] == fav
    assert any(w["kind"] == "travel_route" for w in api.get("/api/v1/customer/wishlist").json())
    t = api.post(f"{CUST}/travellers", {"name": "Priya Sharma", "age": 27, "gender": "female", "berthPreference": "UB"}, format="json").json()
    assert api.patch(f"{CUST}/travellers/{t['id']}", {"age": 28}, format="json").json()["age"] == 28
    assert api.post(f"{CUST}/travellers", {"name": "1234", "age": 27, "gender": "female"}, format="json").status_code == 400
    other = client(make_customer("o@x.com"))
    assert other.delete(f"{CUST}/travellers/{t['id']}").status_code == 404
    alert = api.post(f"{CUST}/alerts", {"origin": "hyderabad", "destination": "delhi", "mode": "flight", "date": day(20)}, format="json").json()
    assert alert["lastFare"]
    assert api.patch(f"{CUST}/preferences", {"busTypes": ["sleeper"], "nonstop": True}, format="json").json()["busTypes"] == ["sleeper"]
    o = search(api, "bus", "hyderabad", "vijayawada").json()["results"][0]
    bk = book(api, o, "seater", pax(), seats=["2"]).json()
    hub = api.get("/api/v1/customer/reservations", {"group": "upcoming"}).json()
    assert [r["link"] for r in hub["results"]] == [f"/travel/bookings/{bk['id']}"] and hub["counts"]["upcoming"] == 1
    nxt = api.get(f"{CUST}/next").json()["booking"]
    assert nxt["id"] == bk["id"]
    assert Passenger.objects.filter(booking_id=bk["id"]).count() == 1
