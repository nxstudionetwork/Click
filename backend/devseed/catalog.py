"""DEVELOPMENT MOCK DATA: restaurants, grocery stores, shops, products and offers (all fictional)."""

from datetime import timedelta
from decimal import Decimal as D

from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import MenuCategory, Product
from apps.stores.models import Store, StoreCategory, StoreOffer, StoreType

from . import MARKER, locality_point

# name, cuisines, rating, rating_count, price_level, eta, fee, min_order, accepting_orders, locality
RESTAURANTS = [
    ("Saffron Smoke Biryani House", ["Biryani", "North Indian"], "4.6", 2140, 2, (25, 35), "29", "149", True, "Indiranagar"),
    ("Crust & Coal Pizzeria", ["Pizza"], "4.4", 980, 3, (30, 40), "39", "199", True, "Indiranagar"),
    ("Dosa District", ["South Indian"], "4.7", 3520, 1, (20, 30), "19", "99", True, "Jayanagar"),
    ("Stack Burger Lab", ["Burgers"], "4.2", 760, 2, (25, 35), "29", "149", True, "Koramangala"),
    ("Green Bowl Kitchen", ["Healthy"], "4.5", 640, 3, (20, 30), "35", "199", True, "HSR Layout"),
    ("Midnight Mithai", ["Desserts"], "4.8", 1890, 2, (15, 25), "25", "99", True, "Malleshwaram"),
    ("Wok Theory", ["Chinese"], "4.1", 520, 2, (30, 45), "35", "149", True, "Koramangala"),
    ("Tandoor Republic", ["North Indian"], "4.3", 1430, 3, (35, 50), "45", "249", True, "Indiranagar"),
    ("Brew Ritual Cafe", ["Cafe", "Desserts"], "4.6", 410, 2, (15, 25), "19", "99", True, "Indiranagar"),
    ("Coastal Curry Co.", ["Kerala", "South Indian"], "3.9", 210, 2, (40, 55), "49", "199", False, "Whitefield"),
    ("Basil & Lime Thai Kitchen", ["Thai"], "4.4", 690, 3, (30, 45), "39", "249", True, "Koramangala"),
    ("Taco Tierra", ["Mexican"], "4.0", 330, 2, (25, 40), "35", "149", True, "HSR Layout"),
    ("Butter & Crumb Bakehouse", ["Bakery", "Cafe"], "4.7", 1180, 2, (15, 25), "19", "99", True, "Jayanagar"),
    ("The Extraordinarily Long-Named Kerala Coastal Kitchen & Toddy Shop", ["Kerala"], "4.2", 95, 2, (35, 50), "45", "199", True, "Whitefield"),
    ("Momo Mantra", ["Chinese", "Momos"], "4.3", 2300, 1, (20, 30), "19", "99", True, "Malleshwaram"),
    ("Royal Rasoi", ["North Indian", "Biryani"], "3.8", 870, 2, (35, 55), "39", "199", True, "Yelahanka"),
    ("Sushi Sakura Bar", ["Japanese"], "4.6", 410, 4, (40, 60), "59", "499", True, "Indiranagar"),
    ("Udupi Upahara", ["South Indian"], "4.5", 5100, 1, (15, 25), "0", "79", True, "Basavanagudi"),
    ("Fresh Off The Grill", ["Burgers", "Healthy"], "0.0", 0, 2, (25, 35), "29", "149", True, "Bellandur"),
    ("Night Owl Shawarma", ["Middle Eastern"], "4.1", 1520, 1, (20, 35), "25", "99", False, "Koramangala"),
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
    "Thai": [("Green Curry with Jasmine Rice", "veg", "329"), ("Pad Thai (Chicken)", "non_veg", "349"), ("Tom Yum Soup", "veg", "199")],
    "Mexican": [("Loaded Bean Burrito", "veg", "249"), ("Chicken Tinga Tacos (3)", "non_veg", "279"), ("Nachos Grande", "veg", "229")],
    "Bakery": [("Sourdough Loaf", "vegan", "199"), ("Cinnamon Roll", "veg", "129"), ("Blueberry Muffin", "veg", "99")],
    "Kerala": [("Appam with Vegetable Stew", "vegan", "189"), ("Kerala Fish Curry Meals", "non_veg", "299"), ("Malabar Parotta (2 pc)", "veg", "69")],
    "Momos": [("Steamed Veg Momos (8)", "veg", "129"), ("Chicken Jhol Momos (8)", "non_veg", "169"), ("Pan-fried Paneer Momos (8)", "veg", "159")],
    "Japanese": [("Salmon Nigiri (6)", "non_veg", "699"), ("Avocado Maki Roll (8)", "vegan", "449"), ("Chicken Katsu Bowl", "non_veg", "529")],
    "Middle Eastern": [("Chicken Shawarma Roll", "non_veg", "149"), ("Falafel Plate with Hummus", "vegan", "229"), ("Mutton Mandi (Half)", "non_veg", "449")],
}

# Grocery & retail (fictional brands): (name, type, categories, rating, count, price_level, eta, fee, min, locality,
#   {section: [(name, brand, unit, price, compare_at|None, stock|None)]})
SHOPS = [
    ("FreshCart Daily", StoreType.GROCERY, ["Fruits & Vegetables", "Dairy & Eggs"], "4.5", 1210, 1, (10, 20), "15", "99", "Koramangala", {
        "Fruits & Vegetables": [("Bananas (Robusta)", "", "1 dozen", "59", "69", 40), ("Tomatoes", "", "1 kg", "38", None, 25), ("Alphonso Mangoes", "", "6 pc", "449", "549", 3)],
        "Dairy & Eggs": [("Toned Milk", "Meadowfresh", "1 L", "54", None, 60), ("Farm Eggs", "Hillcrest Farms", "Pack of 12", "119", "135", 0), ("Greek Yogurt", "Cultura", "400 g", "120", None, None)],
    }),
    ("Pantry Point", StoreType.GROCERY, ["Staples", "Snacks & Drinks"], "4.3", 640, 1, (15, 25), "19", "149", "Koramangala", {
        "Staples": [("Basmati Rice", "Golden Harvest", "5 kg", "649", "799", 15), ("Toor Dal", "Kisan Select", "1 kg", "189", None, 22), ("Cold-pressed Groundnut Oil", "Vanam", "1 L", "349", "399", 8)],
        "Snacks & Drinks": [("Masala Peanuts", "Crunchwala", "200 g", "55", None, 50), ("Sparkling Water", "Glacier Springs", "Pack of 6", "180", "210", 12), ("Dark Chocolate 70%", "Cocoa Coast", "150 g", "99", None, 4)],
    }),
    ("Orchard & Co. Organics", StoreType.GROCERY, ["Fruits & Vegetables", "Staples"], "4.7", 380, 3, (20, 35), "29", "299", "HSR Layout", {
        "Fruits & Vegetables": [("Organic Spinach", "", "250 g", "45", None, 18), ("Hass Avocado", "", "2 pc", "299", "349", 6)],
        "Staples": [("Organic Jaggery Powder", "Earthen Roots", "500 g", "165", None, 9), ("Millet Muesli", "Morning Millet", "400 g", "275", "325", 11)],
    }),
    ("Corner Kirana Express", StoreType.GROCERY, ["Staples", "Dairy & Eggs"], "4.0", 150, 1, (10, 15), "0", "0", "Jayanagar", {
        "Staples": [("Atta (Whole Wheat)", "Chakki Gold", "5 kg", "289", "315", 30), ("Iodised Salt", "Sagar", "1 kg", "28", None, 80)],
        "Dairy & Eggs": [("Paneer", "Meadowfresh", "200 g", "95", None, 14), ("Salted Butter", "Creamline", "100 g", "58", None, 20)],
    }),
    ("Daily Basket Express", StoreType.GROCERY, ["Household", "Snacks & Drinks"], "4.2", 260, 1, (10, 20), "9", "99", "Bellandur", {
        "Household": [("Dishwash Liquid Lemon", "SparkleHome", "750 ml", "149", "175", 25), ("Laundry Detergent Pods (24)", "SparkleHome", "24 pods", "399", None, 0)],
        "Snacks & Drinks": [("Cold-pressed Orange Juice", "Squeezed", "1 L", "220", "260", 7), ("Baked Ragi Chips", "Crunchwala", "100 g", "65", None, 33)],
    }),
    ("Volt Electronics", StoreType.RETAIL, ["Electronics"], "4.4", 920, 3, (45, 90), "49", "0", "Indiranagar", {
        "Audio": [("Wireless Earbuds Pro", "Sonique", "1 unit", "2499", "3999", 7), ("Bluetooth Speaker Mini", "Boomlet", "1 unit", "3299", "3999", 2)],
        "Accessories": [("65W USB-C Charger", "Voltix", "1 unit", "1299", "1799", 25), ("Braided USB-C Cable 1.5m", "Voltix", "1 unit", "349", None, 60)],
    }),
    ("Thread & Loom", StoreType.RETAIL, ["Fashion"], "4.2", 410, 2, (60, 120), "39", "0", "Koramangala", {
        "Men": [("Linen Shirt — Sage", "Thread & Loom", "M / L / XL", "1499", "1999", 12), ("Everyday Chinos", "Thread & Loom", "30–36", "1799", None, 9)],
        "Women": [("Block-print Kurta", "Thread & Loom", "S–XL", "1299", "1699", 5), ("Cotton Dupatta", "Thread & Loom", "Free size", "499", None, 0)],
    }),
    ("Hearth Home Store", StoreType.RETAIL, ["Home & Kitchen"], "4.6", 530, 2, (60, 120), "49", "0", "Jayanagar", {
        "Kitchen": [("Cast Iron Skillet 10\"", "Ironclad", "1 unit", "1899", "2499", 6), ("Glass Storage Jars (Set of 3)", "Clearhome", "Set of 3", "699", None, 20)],
        "Decor": [("Handwoven Cushion Cover", "Hearth", "16x16 in", "399", "549", 30)],
    }),
    ("Paperback Lane", StoreType.RETAIL, ["Books & Stationery"], "4.8", 270, 2, (45, 90), "29", "0", "Basavanagudi", {
        "Books": [("The Startup Playbook", "Lanternhouse Press", "Paperback", "399", "499", 10), ("Bengaluru: A City History", "Lanternhouse Press", "Hardcover", "799", None, 1)],
        "Stationery": [("Dot-grid Notebook A5", "Paperback Lane", "160 pages", "299", None, 45)],
    }),
    ("Stride Sports Co.", StoreType.RETAIL, ["Sports & Fitness"], "4.3", 340, 2, (60, 120), "49", "0", "Whitefield", {
        "Running": [("Featherlight Running Shoes", "Stride", "UK 6–11", "3499", "4999", 8), ("Dri-fit Running Tee", "Stride", "S–XXL", "799", None, 40)],
        "Fitness": [("Yoga Mat 6mm", "Asana Pro", "1 unit", "1199", "1499", 15), ("Adjustable Dumbbells (Pair)", "Ironclad", "2–10 kg", "5999", None, 0),
                    ("Steel Water Bottle 1L", "Stride", "1 L", "599", "699", 50), ("Resistance Bands Set", "Asana Pro", "Set of 5", "699", None, 3)],
    }),
]

# Extra display offers so the Offers page has 20 active entries (plus expired/inactive ones to test filtering).
OFFERS = {
    "saffron-smoke-biryani-house": "20% off up to ₹100", "crust-coal-pizzeria": "Free delivery over ₹399",
    "stack-burger-lab": "Buy 1 get 1 on classics", "midnight-mithai": "₹50 off first order", "tandoor-republic": "15% off weekends",
    "basil-lime-thai-kitchen": "Free Thai iced tea over ₹599", "taco-tierra": "Taco Tuesday: 2 for 1", "momo-mantra": "Flat ₹30 off momo platters",
    "butter-crumb-bakehouse": "10% off before 11 AM", "udupi-upahara": "Free filter coffee with any meal", "sushi-sakura-bar": "₹200 off over ₹1,499",
    "royal-rasoi": "Family feast: 25% off for 4", "freshcart-daily": "Flat ₹40 off over ₹499", "pantry-point": "Staples week: up to 20% off",
    "daily-basket-express": "Free delivery all day", "volt-electronics": "No-cost EMI on audio", "thread-loom": "Buy 2 get 10% off",
    "hearth-home-store": "Kitchen sale: up to 30% off", "stride-sports-co": "Extra 10% off running shoes", "paperback-lane": "Buy 3 books, get 1 free",
}
EXPIRED_OFFERS = {"dosa-district": "Diwali dosa fest (ended)", "wok-theory": "Monsoon noodle deal (ended)"}


def _store(name, store_type, cats, rating, count, price, eta, fee, minimum, accepting, locality, cat_objs):
    store, _ = Store.objects.update_or_create(
        slug=slugify(name),
        defaults=dict(
            name=name, store_type=store_type, status=Store.Status.ACTIVE, is_accepting_orders=accepting,
            description=f"{', '.join(cats)}. {MARKER}.", city="Bengaluru", locality=locality,
            rating_average=D(rating), rating_count=count, price_level=price, delivery_time_min=eta[0], delivery_time_max=eta[1],
            delivery_fee=D(fee), min_order_amount=D(minimum), **dict(zip(("latitude", "longitude"), locality_point(locality, name))),
        ),
    )
    store.categories.add(*[cat_objs[c] for c in cats])
    return store


def _product(store, section, pos, i, name, price, dietary="unspecified", brand="", unit="", compare_at=None, stock=None, available=True):
    cat, _ = MenuCategory.objects.get_or_create(store=store, name=section, defaults={"position": pos})
    Product.objects.update_or_create(
        store=store, name=name,
        defaults=dict(category=cat, price=D(price), dietary=dietary, brand=brand, unit_label=unit,
                      compare_at_price=D(compare_at) if compare_at else None, stock_quantity=stock,
                      description=f"{brand + ' ' if brand else 'House-made '}{name.lower() if not brand else name}{', ' + unit if unit else ''}.",
                      position=i, is_featured=(i == 0), is_available=available, is_active=True),
    )


def seed_catalog(log) -> None:
    cuisines = sorted({c for r in RESTAURANTS for c in r[1]})
    cat_objs = {}
    for pos, name in enumerate(cuisines):
        cat_objs[name], _ = StoreCategory.objects.get_or_create(store_type=StoreType.RESTAURANT, slug=slugify(name), defaults={"name": name, "position": pos})
    for name, cats, rating, count, price, eta, fee, minimum, accepting, locality in RESTAURANTS:
        store = _store(name, StoreType.RESTAURANT, cats, rating, count, price, eta, fee, minimum, accepting, locality, cat_objs)
        for pos, cuisine in enumerate(cats):
            for i, (item, dietary, item_price) in enumerate(MENU[cuisine]):
                # One sold-out dish per few stores, to test unavailable states.
                _product(store, cuisine, pos, i, item, item_price, dietary=dietary, available=not (i == 2 and pos == 0 and len(name) % 3 == 0))

    for name, store_type, cats, rating, count, price, eta, fee, minimum, locality, sections in SHOPS:
        shop_cats = {}
        for pos, c in enumerate(cats):
            shop_cats[c], _ = StoreCategory.objects.get_or_create(store_type=store_type, slug=slugify(c), defaults={"name": c, "position": pos})
        store = _store(name, store_type, cats, rating, count, price, eta, fee, minimum, True, locality, shop_cats)
        for pos, (section, items) in enumerate(sections.items()):
            for i, (item, brand, unit, item_price, compare_at, stock) in enumerate(items):
                _product(store, section, pos, i, item, item_price, brand=brand, unit=unit, compare_at=compare_at, stock=stock)

    now = timezone.now()
    for slug, title in OFFERS.items():
        StoreOffer.objects.get_or_create(store=Store.objects.get(slug=slug), title=title)
    for slug, title in EXPIRED_OFFERS.items():
        StoreOffer.objects.get_or_create(store=Store.objects.get(slug=slug), title=title,
                                         defaults={"starts_at": now - timedelta(days=40), "ends_at": now - timedelta(days=10)})
    log(f"catalog: {len(RESTAURANTS)} restaurants, {len(SHOPS)} grocery/retail stores, offers upserted")
    from .shop import seed_shop

    seed_shop(log)  # Click. Shopping marketplace: taxonomy, brands, sellers, listings, variants, deals, campaigns
    from .groceries import seed_groceries

    seed_groceries(log)  # Click. Groceries: category registry, items, local vendors, hours, delivery settings
