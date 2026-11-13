"""
==========================================================================
 DEVELOPMENT MOCK DATA: never load into production.
==========================================================================
Seed data for local development and UI/flow testing, loaded with:

    python manage.py seed_dev_data

* Writes through the real Django models and, for customer activity, the real
  domain services (cart -> order placement -> status transitions -> payments,
  wallet, rewards, notifications), so relationships match production exactly.
* Repeatable: catalogue rows are upserted by natural keys; customer history is
  only created once per section. It never deletes anything.
* All people, phones, emails, addresses, brands and venues are fictional.
  Test accounts use the reserved `click.local` email domain.
"""

MARKER = "DEVELOPMENT MOCK DATA"

# Approximate centres of the Bengaluru localities used by the seed (public geography, WGS84).
LOCALITY_CENTRES = {
    "Indiranagar": (12.9719, 77.6412), "Koramangala": (12.9352, 77.6245), "Jayanagar": (12.9250, 77.5938),
    "HSR Layout": (12.9116, 77.6474), "Malleshwaram": (13.0035, 77.5710), "Whitefield": (12.9698, 77.7500),
    "Yelahanka": (13.1005, 77.5963), "Basavanagudi": (12.9406, 77.5738), "Bellandur": (12.9260, 77.6762),
}


def locality_point(locality: str, key: str):
    """A stable point within ~500 m of the locality centre (the same `key` always gets the same point)."""
    from decimal import Decimal
    from zlib import crc32

    name = next((n for n in LOCALITY_CENTRES if n.lower() in locality.lower()), None)
    if name is None:
        return None, None
    lat, lng = LOCALITY_CENTRES[name]
    h = crc32(key.encode())
    dlat, dlng = ((h & 0xFFFF) / 0xFFFF - 0.5) * 0.009, (((h >> 16) & 0xFFFF) / 0xFFFF - 0.5) * 0.009
    return Decimal(f"{lat + dlat:.6f}"), Decimal(f"{lng + dlng:.6f}")
