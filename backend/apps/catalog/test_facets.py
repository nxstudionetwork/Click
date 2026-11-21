from decimal import Decimal

from apps.catalog.models import MenuCategory, Product
from apps.stores.models import StoreCategory
from conftest import make_store


def _bakery_and_biryani():
    bakery_cat = StoreCategory.objects.create(name="Bakery", slug="bakery", store_type="restaurant")
    biryani_cat = StoreCategory.objects.create(name="Biryani", slug="biryani", store_type="restaurant")
    bakery = make_store("Crumb Lab")
    bakery.categories.add(bakery_cat)
    cakes, breads = MenuCategory.objects.create(store=bakery, name="Cakes"), MenuCategory.objects.create(store=bakery, name="Breads")
    for i, price in enumerate([90, 120, 180, 240, 480]):
        Product.objects.create(store=bakery, category=cakes, name=f"Cake {i}", price=Decimal(price), dietary="veg")
    Product.objects.create(store=bakery, category=breads, name="Sourdough", price=Decimal("150"), dietary="veg")
    biryani = make_store("Dum House")
    biryani.categories.add(biryani_cat)
    Product.objects.create(store=biryani, category=MenuCategory.objects.create(store=biryani, name="Biryani"), name="Chicken Biryani",
                           price=Decimal("99"), dietary="non_veg")


def test_facets_follow_the_selected_category(api, db):
    _bakery_and_biryani()
    f = api.get("/api/v1/catalog/facets", {"type": "restaurant", "category": "bakery"}).json()
    assert [s["name"] for s in f["sections"]] == ["Cakes", "Breads"]
    assert "Biryani" not in str(f)
    assert [b["max"] for b in f["priceBands"]] == [150, 200, 300] and f["veg"] is True and f["items"] == 6


def test_dishes_filter_by_section_price_and_diet(api, db):
    _bakery_and_biryani()
    r = api.get("/api/v1/catalog/dishes", {"type": "restaurant", "category": "bakery", "section": "cakes", "max_price": 200}).json()["results"]
    assert [p["name"] for p in r] == ["Cake 0", "Cake 1", "Cake 2"]
    assert api.get("/api/v1/catalog/dishes", {"type": "restaurant", "category": "biryani", "veg": 1}).json()["results"] == []
    assert api.get("/api/v1/catalog/facets", {"type": "nope"}).status_code == 400
