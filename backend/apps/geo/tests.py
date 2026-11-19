import pytest

from apps.geo import providers

PHOTON = {"features": [
    {"geometry": {"coordinates": [77.6386519, 12.9782941]}, "properties": {"name": "Indiranagar Metro Station", "street": "CMH Road", "postcode": "560038",
                                                                          "locality": "Indiranagar", "city": "Bengaluru", "state": "Karnataka", "countrycode": "IN"}},
    {"geometry": {"coordinates": [-0.1, 51.5]}, "properties": {"name": "Somewhere abroad", "countrycode": "GB"}},
]}
OSRM = {"code": "Ok", "routes": [{"distance": 5200.0, "duration": 900.0, "geometry": {"coordinates": [[77.64, 12.97], [77.63, 12.96], [77.62, 12.95]]}}]}


@pytest.fixture
def maps_on(settings, monkeypatch):
    settings.CLICK_GEOCODER_URL, settings.CLICK_ROUTER_URL = "https://geo.test", "https://route.test"
    calls = []

    def fake(url, params, ttl):
        calls.append(url)
        return OSRM if "route.test" in url else PHOTON

    monkeypatch.setattr(providers, "_get_json", fake)
    return calls


def test_search_keeps_indian_places_and_formats_addresses(auth_api, maps_on):
    r = auth_api.get("/api/v1/geo/search", {"q": "indiranagar metro", "lat": 12.97, "lng": 77.64}).json()
    assert r["enabled"] and [p["label"] for p in r["results"]] == ["Indiranagar Metro Station"]
    assert r["results"][0]["address"] == "CMH Road, Indiranagar, Bengaluru, Karnataka" and r["results"][0]["lat"] == 12.978294


def test_reverse_keeps_the_exact_point(auth_api, maps_on):
    p = auth_api.get("/api/v1/geo/reverse", {"lat": 12.9701, "lng": 77.6402}).json()["place"]
    assert p["label"] == "Indiranagar Metro Station" and (p["lat"], p["lng"]) == (12.9701, 77.6402)
    assert auth_api.get("/api/v1/geo/reverse", {"lat": "x"}).status_code == 400


def test_route_and_ride_quote_use_road_distance(auth_api, maps_on):
    r = auth_api.post("/api/v1/geo/route", {"points": [[12.97, 77.64], [12.95, 77.62]]}).json()["route"]
    assert r["distanceKm"] == 5.2 and r["durationMin"] == 15.0 and r["geometry"][0] == [12.97, 77.64]
    from apps.rides.pricing import estimate_route

    est = estimate_route([(12.97, 77.64), (12.95, 77.62)])
    assert est.basis == "road" and float(est.distance_km) == 5.2 and len(est.geometry) == 3


def test_everything_falls_back_when_maps_are_off(auth_api, settings):
    settings.CLICK_GEOCODER_URL = settings.CLICK_ROUTER_URL = ""
    assert auth_api.get("/api/v1/geo/search", {"q": "indiranagar"}).json() == {"results": [], "enabled": False}
    from apps.rides.pricing import estimate_route

    assert estimate_route([(12.97, 77.64), (12.95, 77.62)]).basis == "straight_line"


def test_maps_need_sign_in(api):
    assert api.get("/api/v1/geo/search", {"q": "x"}).status_code == 401


def test_reverse_returns_address_parts_for_saving(auth_api, maps_on):
    parts = auth_api.get("/api/v1/geo/reverse", {"lat": 12.97, "lng": 77.64}).json()["place"]["parts"]
    assert parts == {"street": "CMH Road", "locality": "Indiranagar", "city": "Bengaluru", "state": "Karnataka", "postalCode": "560038"}
