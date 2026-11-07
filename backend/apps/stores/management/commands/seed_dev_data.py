"""
DEVELOPMENT SEED DATA — never run in production.

Creates 10 restaurants, 4 grocery stores and 4 retail stores so the real API can be exercised end to end.
Mirrors the frontend's TEMPORARY MOCK DATA (apps/customer/src/mock) in spirit
so the UI looks the same against the real API.

    python manage.py seed_dev_data [--reset]
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import MenuCategory, Product
from apps.stores.models import Store, StoreCategory, StoreOffer, StoreType

CATEGORIES = ["Biryani", "Pizza", "South Indian", "Burgers", "Healthy", "Desserts", "Chinese", "North Indian", "Cafe"]

# name, categories, rating, rating_count, price_level, eta(min,max), fee, min_order, open, offer
RESTAURANTS = [
    ("Saffron Smoke Biryani House", ["Biryani", "North Indian"], "4.6", 2140, 2, (25, 35), "29", "149", True, "20% off up to ₹100"),
    ("Crust & Coal Pizzeria", ["Pizza"], "4.4", 980, 3, (30, 40), "39", "199", True, "Free delivery over ₹399"),
    ("Dosa District", ["South Indian"], "4.7", 3520, 1, (20, 30), "19", "99", True, None),
    ("Stack Burger Lab", ["Burgers"], "4.2", 760, 2, (25, 35), "29", "149", True, "Buy 1 get 1 on classics"),
    ("Green Bowl Kitchen", ["Healthy"], "4.5", 640, 3, (20, 30), "35", "199", True, None),
    ("Midnight Mithai", ["Desserts"], "4.8", 1890, 2, (15, 25), "25", "99", True, "₹50 off first order"),
    ("Wok Theory", ["Chinese"], "4.1", 520, 2, (30, 45), "35", "149", True, None),
    ("Tandoor Republic", ["North Indian"], "4.3", 1430, 3, (35, 50), "45", "249", True, "15% off weekends"),
    ("Brew Ritual Cafe", ["Cafe", "Desserts"], "4.6", 410, 2, (15, 25), "19", "99", True, None),
    ("Coastal Curry Co.", ["South Indian", "North Indian"], "3.9", 210, 2, (40, 55), "49", "199", False, None),
]

MENU = {
    "Biryani": [("Hyderabadi Chicken Biryani", "non_veg", "289"), ("Paneer Tikka Biryani", "veg", "249"), ("Mutton Dum Biryani", "non_veg", "369")],
    "Pizza": [("Margherita Classica", "veg", "249"), ("Smoked Chicken Pesto", "non_veg", "389"), ("Four Cheese Bianca", "veg", "349")],
    "South Indian": [("Ghee Roast Dosa", "veg", "129"), ("Idli Vada Combo", "veg", "99"), ("Mysore Masala Dosa", "veg", "139")],
    "Burgers": [("The Classic Stack", "non_veg", "199"), ("Crispy Paneer Burger", "veg", "179"), ("Double Smash", "non_veg", "279")],
    "Healthy": [("Quinoa Power Bowl", "vegan", "299"), ("Grilled Chicken Salad", "non_veg", "319"), ("Avocado Toast", "veg", "249")],
    "Desserts": [("Kesar Rasmalai (2 pc)", "veg", "149"), ("Gulab Jamun Cheesecake", "veg", "199"), ("Hot Chocolate Fudge", "veg", "179")],
    "Chinese": [("Chilli Garlic Noodles", "veg", "199"), ("Kung Pao Chicken", "non_veg", "279"), ("Veg Manchurian Gravy", "veg", "219")],
    "North Indian": [("Butter Chicken", "non_veg", "339"), ("Dal Makhani", "veg", "239"), ("Garlic Naan", "veg", "59")],
    "Cafe": [("Cold Brew Tonic", "vegan", "189"), ("Hazelnut Cappuccino", "veg", "169"), ("Almond Croissant", "veg", "149")],
}


# Grocery & retail: (name, type, categories, rating, count, price, eta, fee, min, offer, {section: [(name, brand, unit, price, compare_at|None, stock|None)]})
SHOPS = [
    ("FreshCart Daily", StoreType.GROCERY, ["Fruits & Vegetables", "Dairy & Eggs"], "4.5", 1210, 1, (10, 20), "15", "99", "Flat ₹40 off over ₹499", {
        "Fruits & Vegetables": [("Bananas (Robusta)", "", "1 dozen", "59", "69", 40), ("Tomatoes", "", "1 kg", "38", None, 25), ("Alphonso Mangoes", "", "6 pc", "449", "549", 3)],
        "Dairy & Eggs": [("Toned Milk", "Nandini", "1 L", "54", None, 60), ("Farm Eggs", "Eggoz", "Pack of 12", "119", "135", 0), ("Greek Yogurt", "Epigamia", "400 g", "120", None, None)],
    }),
    ("Pantry Point", StoreType.GROCERY, ["Staples", "Snacks & Drinks"], "4.3", 640, 1, (15, 25), "19", "149", None, {
        "Staples": [("Basmati Rice", "India Gate", "5 kg", "649", "799", 15), ("Toor Dal", "Tata Sampann", "1 kg", "189", None, 22), ("Cold-pressed Groundnut Oil", "Anveshan", "1 L", "349", "399", 8)],
        "Snacks & Drinks": [("Masala Peanuts", "Haldiram's", "200 g", "55", None, 50), ("Sparkling Water", "Bisleri", "Pack of 6", "180", "210", 12), ("Dark Chocolate 70%", "Amul", "150 g", "99", None, 4)],
    }),
    ("Orchard & Co. Organics", StoreType.GROCERY, ["Fruits & Vegetables", "Staples"], "4.7", 380, 3, (20, 35), "29", "299", None, {
        "Fruits & Vegetables": [("Organic Spinach", "", "250 g", "45", None, 18), ("Hass Avocado", "", "2 pc", "299", "349", 6)],
        "Staples": [("Organic Jaggery Powder", "Two Brothers", "500 g", "165", None, 9), ("Millet Muesli", "Slurrp Farm", "400 g", "275", "325", 11)],
    }),
    ("Corner Kirana Express", StoreType.GROCERY, ["Staples", "Dairy & Eggs"], "4.0", 150, 1, (10, 15), "0", "0", None, {
        "Staples": [("Atta (Whole Wheat)", "Aashirvaad", "5 kg", "289", "315", 30), ("Iodised Salt", "Tata", "1 kg", "28", None, 80)],
        "Dairy & Eggs": [("Paneer", "Milky Mist", "200 g", "95", None, 14), ("Salted Butter", "Amul", "100 g", "58", None, 20)],
    }),
    ("Volt Electronics", StoreType.RETAIL, ["Electronics"], "4.4", 920, 3, (45, 90), "49", "0", "No-cost EMI on audio", {
        "Audio": [("Wireless Earbuds Pro", "Boat", "1 unit", "2499", "3999", 7), ("Bluetooth Speaker Mini", "JBL", "1 unit", "3299", "3999", 2)],
        "Accessories": [("65W USB-C Charger", "Ambrane", "1 unit", "1299", "1799", 25), ("Braided USB-C Cable 1.5m", "Portronics", "1 unit", "349", None, 60)],
    }),
    ("Thread & Loom", StoreType.RETAIL, ["Fashion"], "4.2", 410, 2, (60, 120), "39", "0", "Buy 2 get 10% off", {
        "Men": [("Linen Shirt — Sage", "Thread & Loom", "M / L / XL", "1499", "1999", 12), ("Everyday Chinos", "Thread & Loom", "30–36", "1799", None, 9)],
        "Women": [("Block-print Kurta", "Thread & Loom", "S–XL", "1299", "1699", 5), ("Cotton Dupatta", "Thread & Loom", "Free size", "499", None, 0)],
    }),
    ("Hearth Home Store", StoreType.RETAIL, ["Home & Kitchen"], "4.6", 530, 2, (60, 120), "49", "0", None, {
        "Kitchen": [("Cast Iron Skillet 10\"", "Meyer", "1 unit", "1899", "2499", 6), ("Glass Storage Jars (Set of 3)", "Borosil", "Set of 3", "699", None, 20)],
        "Decor": [("Handwoven Cushion Cover", "Hearth", "16x16 in", "399", "549", 30)],
    }),
    ("Paperback Lane", StoreType.RETAIL, ["Books & Stationery"], "4.8", 270, 2, (45, 90), "29", "0", None, {
        "Books": [("The Startup Playbook", "Penguin", "Paperback", "399", "499", 10), ("Bengaluru: A City History", "HarperCollins", "Hardcover", "799", None, 1)],
        "Stationery": [("Dot-grid Notebook A5", "Paperback Lane", "160 pages", "299", None, 45)],
    }),
]


class Command(BaseCommand):
    help = "Seed development data (restaurants, grocery and retail stores). DEVELOPMENT ONLY."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing seeded stores first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not (settings.DEBUG or settings.TESTING):
            raise CommandError("seed_dev_data only runs with DJANGO_DEBUG=true.")
        slugs = [slugify(r[0]) for r in RESTAURANTS] + [slugify(r[0]) for r in SHOPS]
        if opts["reset"]:
            Store.objects.filter(slug__in=slugs).delete()

        cats = {}
        for pos, name in enumerate(CATEGORIES):
            cats[name], _ = StoreCategory.objects.get_or_create(
                store_type=StoreType.RESTAURANT, slug=slugify(name), defaults={"name": name, "position": pos}
            )

        created = 0
        for name, store_cats, rating, count, price, eta, fee, minimum, is_open, offer in RESTAURANTS:
            store, was_created = Store.objects.get_or_create(
                slug=slugify(name),
                defaults=dict(
                    name=name, store_type=StoreType.RESTAURANT, status=Store.Status.ACTIVE, is_accepting_orders=is_open,
                    description=f"{' · '.join(store_cats)} favourites, cooked fresh.", city="Bengaluru",
                    locality="Indiranagar", rating_average=Decimal(rating), rating_count=count, price_level=price,
                    delivery_time_min=eta[0], delivery_time_max=eta[1], delivery_fee=Decimal(fee),
                    min_order_amount=Decimal(minimum),
                ),
            )
            if not was_created:
                continue
            created += 1
            store.categories.set([cats[c] for c in store_cats])
            if offer:
                StoreOffer.objects.create(store=store, title=offer)
            for pos, cat_name in enumerate(store_cats):
                menu_cat = MenuCategory.objects.create(store=store, name=cat_name, position=pos)
                for i, (item, dietary, item_price) in enumerate(MENU[cat_name]):
                    Product.objects.create(
                        store=store, category=menu_cat, name=item, price=Decimal(item_price), dietary=dietary,
                        description=f"House-made {item.lower()}.", position=i, is_featured=(i == 0),
                        is_available=not (pos == 0 and i == 2 and name.startswith("Tandoor")),
                    )
        for name, store_type, store_cats, rating, count, price, eta, fee, minimum, offer, sections in SHOPS:
            store, was_created = Store.objects.get_or_create(
                slug=slugify(name),
                defaults=dict(
                    name=name, store_type=store_type, status=Store.Status.ACTIVE, is_accepting_orders=True,
                    description=f"{', '.join(store_cats)} delivered to your door.", city="Bengaluru",
                    locality="Koramangala", rating_average=Decimal(rating), rating_count=count, price_level=price,
                    delivery_time_min=eta[0], delivery_time_max=eta[1], delivery_fee=Decimal(fee),
                    min_order_amount=Decimal(minimum),
                ),
            )
            if not was_created:
                continue
            created += 1
            for pos, cat_name in enumerate(store_cats):
                c, _ = StoreCategory.objects.get_or_create(
                    store_type=store_type, slug=slugify(cat_name), defaults={"name": cat_name, "position": pos}
                )
                store.categories.add(c)
            if offer:
                StoreOffer.objects.create(store=store, title=offer)
            for pos, (section, items) in enumerate(sections.items()):
                menu_cat = MenuCategory.objects.create(store=store, name=section, position=pos)
                for i, (item, brand, unit, item_price, compare_at, stock) in enumerate(items):
                    Product.objects.create(
                        store=store, category=menu_cat, name=item, brand=brand, unit_label=unit,
                        price=Decimal(item_price), compare_at_price=Decimal(compare_at) if compare_at else None,
                        stock_quantity=stock, description=f"{brand + ' ' if brand else ''}{item}, {unit}.",
                        position=i, is_featured=(i == 0),
                    )
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new stores ({len(RESTAURANTS) + len(SHOPS)} total defined)."))
