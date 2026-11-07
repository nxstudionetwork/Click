"""
DEVELOPMENT SEED DATA — never run in production.

Creates 10 restaurants with menus so the real API can be exercised end to end.
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


class Command(BaseCommand):
    help = "Seed development data (10 restaurants with menus). DEVELOPMENT ONLY."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing seeded stores first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not (settings.DEBUG or settings.TESTING):
            raise CommandError("seed_dev_data only runs with DJANGO_DEBUG=true.")
        slugs = [slugify(r[0]) for r in RESTAURANTS]
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
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new restaurants ({len(RESTAURANTS)} total defined)."))
