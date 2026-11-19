"""
Click maps platform: place search, reverse geocoding and road routing behind small provider interfaces.

No Google services. Defaults are open-source, OpenStreetMap-based engines:
  * CLICK_GEOCODER_URL — a Photon server (https://github.com/komoot/photon): typo-tolerant search-as-you-type with
    location bias, plus reverse geocoding. Development uses the public instance (fair use); production should
    self-host it or point at a contracted provider.
  * CLICK_ROUTER_URL — an OSRM server (https://project-osrm.org): real road distance, duration and route geometry.
    Development uses the public demo server; production must self-host or use a contracted provider.

An empty URL switches the feature off: search falls back to Click's own places, and fares fall back to the labelled
straight-line estimate. Nothing is ever invented. Results are cached so repeated lookups never hit the provider twice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

USER_AGENT = "ClickApp/1.0 (maps; +https://github.com/nxstudionetwork/Click)"
TIMEOUT = 6


def _get_json(url: str, params: dict, ttl: int) -> dict | list | None:
    full = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    key = "geo:" + hashlib.sha256(full.encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — fixed https provider URL from settings
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — a provider outage must degrade gracefully, never break booking
        logger.warning("maps provider unavailable: %s (%s)", url.split("?")[0], e)
        return None
    cache.set(key, data, ttl)
    return data


@dataclass(frozen=True)
class GeoPlace:
    label: str
    address: str
    lat: float
    lng: float
    kind: str = "search"  # search | reverse
    street: str = ""
    locality: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "address": self.address, "lat": self.lat, "lng": self.lng,
                "parts": {"street": self.street, "locality": self.locality, "city": self.city, "state": self.state, "postal_code": self.postal_code}}


def _photon_place(feature: dict, kind: str) -> GeoPlace | None:
    p = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) != 2 or p.get("countrycode", "IN").upper() != "IN":
        return None
    street = " ".join(filter(None, [p.get("housenumber"), p.get("street")]))
    name = p.get("name") or street or p.get("locality") or p.get("district") or p.get("city")
    if not name:
        return None
    parts = [street if street != name else "", p.get("locality"), p.get("district"), p.get("city"), p.get("state")]
    seen, address = set(), []
    for part in parts:
        if part and part != name and part not in seen:
            seen.add(part)
            address.append(part)
    postcode = (p.get("postcode") or "").replace(" ", "")
    return GeoPlace(name, ", ".join(address[:4]), round(float(coords[1]), 6), round(float(coords[0]), 6), kind,
                    street=street, locality=p.get("locality") or p.get("district") or "", city=p.get("city") or p.get("county") or "",
                    state=p.get("state") or "", postal_code=postcode if postcode.isdigit() and len(postcode) == 6 else "")


def geocoder_enabled() -> bool:
    return bool(settings.CLICK_GEOCODER_URL)


def search(q: str, near: tuple[float, float] | None = None, limit: int = 8) -> list[GeoPlace]:
    """Places in India matching `q`, ranked towards `near` when given."""
    q = (q or "").strip()[:120]
    if not geocoder_enabled() or len(q) < 3:
        return []
    params = {"q": q, "limit": limit * 2, "lang": "en"}
    if near:
        params.update({"lat": round(near[0], 3), "lon": round(near[1], 3), "location_bias_scale": 0.4})
    data = _get_json(f"{settings.CLICK_GEOCODER_URL.rstrip('/')}/api/", params, ttl=60 * 60 * 24)
    out = []
    for f in (data or {}).get("features", []) if isinstance(data, dict) else []:
        place = _photon_place(f, "search")
        if place:
            out.append(place)
    return out[:limit]


def reverse(lat: float, lng: float) -> GeoPlace | None:
    """The nearest readable address for a point (e.g. the device's current location)."""
    if not geocoder_enabled():
        return None
    data = _get_json(f"{settings.CLICK_GEOCODER_URL.rstrip('/')}/reverse", {"lat": round(lat, 5), "lon": round(lng, 5), "lang": "en"},
                     ttl=60 * 60 * 24 * 7)
    features = (data or {}).get("features", []) if isinstance(data, dict) else []
    place = _photon_place(features[0], "reverse") if features else None
    if not place:
        return None
    from dataclasses import replace

    return replace(place, lat=lat, lng=lng, kind="reverse")


@dataclass(frozen=True)
class RoadRoute:
    distance_km: float
    duration_min: float
    geometry: list[list[float]]  # [[lat, lng], ...] simplified for drawing


def router_enabled() -> bool:
    return bool(settings.CLICK_ROUTER_URL)


def road_route(points: list[tuple[float, float]]) -> RoadRoute | None:
    """Driving route through the points in order, or None when routing is off or unavailable."""
    if not router_enabled() or len(points) < 2:
        return None
    coords = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    data = _get_json(f"{settings.CLICK_ROUTER_URL.rstrip('/')}/route/v1/driving/{coords}",
                     {"overview": "simplified", "geometries": "geojson", "alternatives": "false", "steps": "false"}, ttl=60 * 30)
    if not isinstance(data, dict) or data.get("code") != "Ok" or not data.get("routes"):
        return None
    r = data["routes"][0]
    line = [[round(c[1], 6), round(c[0], 6)] for c in (r.get("geometry") or {}).get("coordinates", [])]
    return RoadRoute(round(r["distance"] / 1000, 2), round(r["duration"] / 60, 1), line)
