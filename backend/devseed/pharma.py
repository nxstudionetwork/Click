"""Development-only Click. Pharma data: 3 pharmacies with OTC products, prescription-only medicines and devices.
Prices are sample values; no product images are invented (the app shows icons). Never loaded in production."""

from __future__ import annotations

from decimal import Decimal as D

PHARMACIES = [  # slug, name, locality, lat, lng, eta (min, max), fee, rating, count
    ("wellkind-indiranagar", "Wellkind Pharmacy", "Indiranagar", "12.9719", "77.6412", (20, 35), "25", "4.6", 820),
    ("careline-koramangala", "CareLine Chemists", "Koramangala", "12.9352", "77.6245", (25, 40), "30", "4.5", 640),
    ("healthfirst-jayanagar", "HealthFirst Medicals", "Jayanagar", "12.9299", "77.5826", (30, 45), "20", "4.4", 410),
]
# name, composition, pack, manufacturer, aisle, price, rx, max per order
PRODUCTS = [
    ("Paracetamol 500 mg tablets", "Paracetamol 500 mg", "Strip of 15", "Generic", "otc", "28", False, 5),
    ("Paracetamol 650 mg tablets", "Paracetamol 650 mg", "Strip of 15", "Generic", "otc", "34", False, 5),
    ("Cetirizine 10 mg tablets", "Cetirizine 10 mg", "Strip of 10", "Generic", "otc", "22", False, 5),
    ("Oral rehydration salts", "ORS (WHO formula)", "Pack of 5 sachets", "Generic", "otc", "95", False, 6),
    ("Antacid chewable tablets", "Calcium carbonate 500 mg", "Bottle of 30", "Generic", "otc", "110", False, 4),
    ("Amoxicillin 500 mg capsules", "Amoxicillin 500 mg", "Strip of 10", "Generic", "medicines", "92", True, 3),
    ("Azithromycin 500 mg tablets", "Azithromycin 500 mg", "Strip of 3", "Generic", "medicines", "118", True, 2),
    ("Metformin 500 mg tablets", "Metformin 500 mg", "Strip of 20", "Generic", "diabetes", "45", True, 6),
    ("Amlodipine 5 mg tablets", "Amlodipine 5 mg", "Strip of 15", "Generic", "medicines", "52", True, 6),
    ("Atorvastatin 10 mg tablets", "Atorvastatin 10 mg", "Strip of 15", "Generic", "medicines", "88", True, 6),
    ("Antiseptic liquid", "Chloroxylenol 4.8% w/v", "250 ml", "Generic", "first_aid", "120", False, 4),
    ("Adhesive bandages", "", "Pack of 20", "Generic", "first_aid", "65", False, 6),
    ("Crepe bandage 10 cm", "", "1 roll", "Generic", "first_aid", "140", False, 4),
    ("Vitamin C 500 mg chewable", "Ascorbic acid 500 mg", "Bottle of 60", "Generic", "vitamins", "260", False, 4),
    ("Vitamin D3 1000 IU softgels", "Cholecalciferol 1000 IU", "Bottle of 60", "Generic", "vitamins", "340", False, 3),
    ("Multivitamin tablets", "", "Bottle of 30", "Generic", "vitamins", "395", False, 3),
    ("Digital thermometer", "", "1 unit", "Generic", "devices", "220", False, 2),
    ("Pulse oximeter", "", "1 unit", "Generic", "devices", "1150", False, 2),
    ("Automatic BP monitor", "", "1 unit", "Generic", "monitoring", "1890", False, 1),
    ("Glucometer test strips", "", "Pack of 50", "Generic", "diabetes", "899", False, 3),
    ("Baby diaper rash cream", "Zinc oxide", "50 g", "Generic", "baby_care", "185", False, 4),
    ("Gentle baby wash", "", "200 ml", "Generic", "baby_care", "240", False, 4),
    ("Sanitary pads (XL)", "", "Pack of 15", "Generic", "womens_care", "149", False, 6),
    ("Sunscreen SPF 50", "", "50 g", "Generic", "skin", "399", False, 3),
    ("Fluoride toothpaste", "", "150 g", "Generic", "dental", "99", False, 6),
    ("Hand sanitiser 70% alcohol", "Ethyl alcohol 70%", "500 ml", "Generic", "hygiene", "180", False, 6),
    ("Knee support (medium)", "", "1 unit", "Generic", "ortho", "450", False, 2),
    ("Adult diapers (M)", "", "Pack of 10", "Generic", "elder", "520", False, 4),
]
AISLE_NAME = {"otc": "Fever, pain & allergy", "medicines": "Prescription medicines", "diabetes": "Diabetes care", "first_aid": "First aid",
              "vitamins": "Vitamins & supplements", "devices": "Medical devices", "monitoring": "Health monitoring", "baby_care": "Baby care",
              "womens_care": "Women’s care", "skin": "Skin care", "dental": "Dental care", "hygiene": "Hygiene", "ortho": "Orthopaedic support",
              "elder": "Elder care"}


def seed_pharma(log) -> None:
    from apps.catalog.models import MenuCategory, Product
    from apps.stores.models import Store

    n = 0
    for i, (slug, name, loc, lat, lng, (t1, t2), fee, rating, count) in enumerate(PHARMACIES):
        store, _ = Store.objects.update_or_create(slug=slug, defaults=dict(
            store_type="pharmacy", status=Store.Status.ACTIVE, is_accepting_orders=True, name=name, city="Bengaluru", locality=loc,
            latitude=D(lat), longitude=D(lng), rating_average=D(rating), rating_count=count, delivery_time_min=t1, delivery_time_max=t2,
            delivery_fee=D(fee), min_order_amount=D("99"), cod_enabled=True,
            description="Licensed pharmacy. Prescription medicines are dispensed only against a prescription our pharmacist verifies."))
        cats = {}
        for pos, (code, label) in enumerate(AISLE_NAME.items()):
            cats[code], _ = MenuCategory.objects.update_or_create(store=store, name=label, defaults={"position": pos, "is_active": True})
        for j, (pname, comp, pack, mfr, aisle, price, rx, maxq) in enumerate(PRODUCTS):
            if (i + j) % 7 == 3:  # each pharmacy stocks most, not all, items
                continue
            adj = D(price) + D(i * 2)
            Product.objects.update_or_create(store=store, name=pname, defaults=dict(
                category=cats[aisle], price=adj, unit_label=pack, brand=mfr, composition=comp, pack_size=pack, manufacturer=mfr,
                health_category=aisle, requires_prescription=rx, max_per_order=maxq, is_available=True, is_active=True, position=j,
                is_cod_available=not rx, return_days=None, units_sold=(37 * (j + 1) + i * 11) % 160,
                description="Prescription-only: needs a prescription verified by this pharmacy." if rx else ""))
            n += 1
    log(f"pharma: {len(PHARMACIES)} pharmacies, {n} products (prescription-only items need a verified prescription)")
