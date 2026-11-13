"""
DEVELOPMENT MOCK DATA: Click. Groceries local vendor network (all businesses and brands fictional).

* A grocery category registry (merchandising order, synonyms, icons).
* Canonical grocery items; each store lists the items it carries at its own price, MRP, stock and freshness date,
  so the same "Golden Harvest Basmati Rice 5 kg" can be compared across stores.
* 10 vendors in Bengaluru with real opening hours, delivery radius/fees/modes, verification state and offers;
  one is temporarily unavailable and two are independent produce/dairy vendors.
* Loose produce uses licensed Wikimedia Commons photos (devseed/grocery_media.py, credited). Packaged goods of
  fictional brands have no photo: the app shows a neutral placeholder rather than an invented image.
* Store ratings are never typed in: they come from the dev customers' order reviews (seed_grocery_history).
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zlib import crc32

from django.db.models import Avg, Count
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import MenuCategory, Product, ProductDeal
from apps.groceries.models import GroceryCategory, GroceryItem, GroceryStoreSettings, StoreHours
from apps.stores.models import Store, StoreCategory, StoreOffer, StoreType

from . import MARKER, locality_point
from .grocery_media import MEDIA

D = Decimal

# slug, name, section, icon, synonyms
CATEGORIES = [
    ("vegetables", "Vegetables", "fresh", "leaf", "veggies, veg, sabzi, vegetable"),
    ("fruits", "Fruits", "fresh", "apple", "fruit, phal"),
    ("leafy-greens-herbs", "Leafy Greens & Herbs", "fresh", "leaf", "greens, herbs, leaves, saag"),
    ("dairy", "Dairy", "dairy", "milk", "milk, curd, dahi, paneer, butter, cheese"),
    ("eggs", "Eggs", "dairy", "egg", "egg, anda"),
    ("bakery", "Bakery", "dairy", "bread", "bread, pav, buns, loaf"),
    ("breakfast", "Breakfast", "dairy", "coffee", "cereal, oats, muesli, tea, coffee"),
    ("rice-atta", "Rice & Atta", "essentials", "wheat", "rice, atta, flour, wheat, chawal"),
    ("pulses", "Pulses", "essentials", "wheat", "dal, lentils, daal"),
    ("oil-ghee", "Oil & Ghee", "essentials", "oil", "oil, ghee, cooking oil"),
    ("spices-salt-sugar", "Spices, Salt & Sugar", "essentials", "spice", "masala, spices, salt, sugar, jaggery"),
    ("snacks", "Snacks", "snacks", "cookie", "chips, biscuits, namkeen, chocolate, noodles"),
    ("beverages", "Beverages", "snacks", "drop", "drinks, juice, water, soda, cola"),
    ("cleaning", "Cleaning & Laundry", "home", "spray", "cleaner, detergent, dishwash, household, garbage bags, tissue"),
    ("personal-care", "Personal Care", "personal", "beauty", "soap, shampoo, toothpaste, hygiene"),
    ("baby-care", "Baby Care", "more", "baby", "diapers, wipes, baby"),
    ("pet-care", "Pet Care", "more", "paw", "dog food, cat, pet"),
]

# key: (name, brand, size, unit, category, base price, MRP or None, dietary, attributes, media key, description)
ITEMS = {
    "tomato": ("Tomatoes", "", "1", "kg", "vegetables", "38", None, "vegan", [], "tomato", "Firm, ripe tomatoes for curries and salads."),
    "onion": ("Onions", "", "1", "kg", "vegetables", "42", None, "vegan", [], "onion", "Medium red onions."),
    "potato": ("Potatoes", "", "1", "kg", "vegetables", "36", None, "vegan", [], "potato", "All-purpose potatoes."),
    "carrot": ("Carrots", "", "500", "g", "vegetables", "32", None, "vegan", [], "carrot", "Crunchy Ooty carrots."),
    "brinjal": ("Brinjal", "", "500", "g", "vegetables", "30", None, "vegan", [], "brinjal", "Purple brinjal."),
    "okra": ("Okra (Bhindi)", "", "500", "g", "vegetables", "40", None, "vegan", [], "okra", "Tender lady's finger."),
    "chilli": ("Green Chillies", "", "100", "g", "vegetables", "12", None, "vegan", [], "chilli", "Medium-hot green chillies."),
    "capsicum": ("Capsicum", "", "500", "g", "vegetables", "48", None, "vegan", [], "capsicum", "Bell peppers."),
    "garlic": ("Garlic", "", "200", "g", "vegetables", "45", None, "vegan", [], "garlic", "Whole garlic bulbs."),
    "ginger": ("Ginger", "", "200", "g", "vegetables", "28", None, "vegan", [], "ginger", "Fresh ginger root."),
    "beans": ("French Beans", "", "500", "g", "vegetables", "44", None, "vegan", [], "beans", "Tender green beans."),
    "gourd": ("Bottle Gourd (Lauki)", "", "1", "pc", "vegetables", "35", None, "vegan", [], "bottle_gourd", "One medium bottle gourd."),
    "coconut": ("Coconut", "", "1", "pc", "vegetables", "38", None, "vegan", [], "coconut", "Mature coconut for chutneys and curries."),
    "coriander": ("Coriander Leaves", "", "100", "g", "leafy-greens-herbs", "15", None, "vegan", [], "coriander", "A bunch of fresh coriander."),
    "mint": ("Mint Leaves", "", "100", "g", "leafy-greens-herbs", "18", None, "vegan", [], "mint", "Fresh mint (pudina)."),
    "spinach": ("Spinach", "", "250", "g", "leafy-greens-herbs", "25", None, "vegan", [], "spinach", "Palak, washed and trimmed."),
    "org_spinach": ("Organic Spinach", "", "250", "g", "leafy-greens-herbs", "45", None, "vegan", ["organic"], "spinach", "Certified organic palak."),
    "banana": ("Bananas (Robusta)", "", "12", "pc", "fruits", "59", None, "vegan", [], "banana", "A dozen ripe Robusta bananas."),
    "mango": ("Alphonso Mangoes", "", "6", "pc", "fruits", "449", None, "vegan", ["seasonal"], "mango", "Ratnagiri Alphonso, in season."),
    "apple": ("Apples (Shimla)", "", "1", "kg", "fruits", "189", None, "vegan", [], "apple", "Crisp red apples."),
    "pomegranate": ("Pomegranate", "", "500", "g", "fruits", "95", None, "vegan", [], "pomegranate", "Bhagwa pomegranates."),
    "orange": ("Oranges", "", "1", "kg", "fruits", "110", None, "vegan", [], "orange", "Juicy Nagpur oranges."),
    "lemon": ("Lemons", "", "250", "g", "fruits", "30", None, "vegan", [], "lemon", "Fresh lemons."),
    "avocado": ("Hass Avocado", "", "2", "pc", "fruits", "299", None, "vegan", [], "avocado", "Two ready-to-ripen Hass avocados."),
    "milk": ("Toned Milk", "Meadowfresh", "1", "l", "dairy", "54", None, "veg", [], None, "Pasteurised toned milk, 3% fat."),
    "milk_half": ("Full Cream Milk", "Meadowfresh", "500", "ml", "dairy", "35", None, "veg", [], None, "Pasteurised full cream milk, 6% fat."),
    "milk_gokul": ("Toned Milk", "Gokul Farms", "500", "ml", "dairy", "27", None, "veg", ["local"], None, "Milk from Gokul's partner farms near Bengaluru."),
    "curd": ("Fresh Curd", "Meadowfresh", "400", "g", "dairy", "45", None, "veg", [], None, "Thick set curd."),
    "yogurt": ("Greek Yogurt", "Cultura", "400", "g", "dairy", "120", None, "veg", ["high-protein"], None, "Strained Greek-style yogurt."),
    "paneer": ("Paneer", "Meadowfresh", "200", "g", "dairy", "95", None, "veg", [], None, "Soft malai paneer."),
    "butter": ("Salted Butter", "Creamline", "100", "g", "dairy", "58", None, "veg", [], None, "Table butter."),
    "cheese": ("Cheese Slices", "Creamline", "200", "g", "dairy", "140", "155", "veg", [], None, "10 processed cheese slices."),
    "eggs": ("Farm Eggs", "Hillcrest Farms", "12", "pc", "eggs", "119", "135", "non_veg", [], "eggs", "Twelve farm eggs."),
    "eggs_brown": ("Brown Eggs", "Hillcrest Farms", "6", "pc", "eggs", "78", None, "non_veg", [], "eggs", "Six brown eggs."),
    "bread": ("Whole Wheat Bread", "Daily Oven", "400", "g", "bakery", "50", None, "veg", [], None, "Sliced whole wheat loaf."),
    "bread_multi": ("Multigrain Bread", "Daily Oven", "400", "g", "bakery", "60", None, "veg", [], None, "Sliced multigrain loaf."),
    "pav": ("Pav Buns", "Daily Oven", "6", "pc", "bakery", "35", None, "veg", [], None, "Soft pav, pack of six."),
    "sourdough": ("Sourdough Loaf", "Bake Street", "450", "g", "bakery", "199", None, "vegan", [], None, "Naturally leavened, baked every morning."),
    "croissant": ("Butter Croissant", "Bake Street", "2", "pc", "bakery", "140", None, "veg", [], None, "Two all-butter croissants."),
    "muesli": ("Millet Muesli", "Morning Millet", "400", "g", "breakfast", "275", "325", "vegan", [], None, "Ragi, jowar and oats with seeds."),
    "oats": ("Rolled Oats", "Morning Millet", "1", "kg", "breakfast", "199", "230", "vegan", [], None, "Whole rolled oats."),
    "cornflakes": ("Cornflakes", "Sunrise Mills", "500", "g", "breakfast", "165", "185", "vegan", [], None, "Crisp corn flakes."),
    "coffee": ("Filter Coffee Powder", "Kaapi Estate", "250", "g", "breakfast", "160", None, "vegan", [], None, "80:20 coffee-chicory blend."),
    "tea": ("Assam Tea", "Tea Garden Co.", "250", "g", "breakfast", "140", "160", "vegan", [], None, "Strong CTC leaf tea."),
    "basmati": ("Basmati Rice", "Golden Harvest", "5", "kg", "rice-atta", "649", "799", "vegan", [], None, "Aged long-grain basmati."),
    "sona": ("Sona Masoori Rice", "Golden Harvest", "5", "kg", "rice-atta", "399", "450", "vegan", [], None, "Everyday raw rice."),
    "sona_kisan": ("Sona Masoori Rice", "Kisan Select", "5", "kg", "rice-atta", "379", "420", "vegan", [], None, "Everyday raw rice."),
    "atta": ("Atta (Whole Wheat)", "Chakki Gold", "5", "kg", "rice-atta", "289", "315", "vegan", [], None, "Stone-ground whole wheat flour."),
    "toor": ("Toor Dal", "Kisan Select", "1", "kg", "pulses", "189", None, "vegan", [], None, "Unpolished toor dal."),
    "moong": ("Moong Dal", "Kisan Select", "500", "g", "pulses", "92", None, "vegan", [], None, "Split yellow moong."),
    "chana": ("Chana Dal", "Kisan Select", "1", "kg", "pulses", "118", None, "vegan", [], None, "Split Bengal gram."),
    "groundnut_oil": ("Cold-pressed Groundnut Oil", "Vanam", "1", "l", "oil-ghee", "349", "399", "vegan", ["cold-pressed"], None, "Wood-pressed groundnut oil."),
    "sunflower": ("Sunflower Oil", "Golden Harvest", "1", "l", "oil-ghee", "155", "175", "vegan", [], None, "Refined sunflower oil."),
    "ghee": ("Cow Ghee", "Creamline", "500", "ml", "oil-ghee", "335", "365", "veg", [], None, "Pure cow ghee."),
    "salt": ("Iodised Salt", "Sagar", "1", "kg", "spices-salt-sugar", "28", None, "vegan", [], None, "Free-flowing iodised salt."),
    "sugar": ("Sugar", "Kisan Select", "1", "kg", "spices-salt-sugar", "52", None, "vegan", [], None, "Fine white sugar."),
    "jaggery": ("Organic Jaggery Powder", "Earthen Roots", "500", "g", "spices-salt-sugar", "165", None, "vegan", ["organic"], None, "Chemical-free jaggery powder."),
    "turmeric": ("Turmeric Powder", "Masala Ghar", "100", "g", "spices-salt-sugar", "38", None, "vegan", [], None, "Salem turmeric."),
    "chilli_powder": ("Red Chilli Powder", "Masala Ghar", "100", "g", "spices-salt-sugar", "45", None, "vegan", [], None, "Byadgi chilli powder."),
    "peanuts": ("Masala Peanuts", "Crunchwala", "200", "g", "snacks", "55", None, "vegan", [], None, "Spiced roasted peanuts."),
    "ragi_chips": ("Baked Ragi Chips", "Crunchwala", "100", "g", "snacks", "65", None, "vegan", ["baked"], None, "Baked, not fried."),
    "chips": ("Classic Salted Chips", "Crunchwala", "90", "g", "snacks", "30", None, "vegan", [], None, "Thin potato chips."),
    "chocolate": ("Dark Chocolate 70%", "Cocoa Coast", "150", "g", "snacks", "99", None, "vegan", [], None, "70% single-origin dark chocolate."),
    "biscuits": ("Marie Biscuits", "Tea Time", "250", "g", "snacks", "35", None, "veg", [], None, "Light tea-time biscuits."),
    "noodles": ("Instant Noodles (4 pack)", "Quickbowl", "280", "g", "snacks", "56", None, "veg", [], None, "Masala instant noodles."),
    "water": ("Packaged Drinking Water", "Glacier Springs", "1", "l", "beverages", "20", None, "vegan", [], None, "Packaged drinking water."),
    "sparkling": ("Sparkling Water", "Glacier Springs", "6", "pack", "beverages", "180", "210", "vegan", [], None, "Six 300 ml cans."),
    "oj": ("Cold-pressed Orange Juice", "Squeezed", "1", "l", "beverages", "220", "260", "vegan", ["no-added-sugar"], None, "Cold-pressed, no added sugar."),
    "cola": ("Cola", "Fizzup", "750", "ml", "beverages", "40", None, "vegan", [], None, "Carbonated soft drink."),
    "dishwash": ("Dishwash Liquid Lemon", "SparkleHome", "750", "ml", "cleaning", "149", "175", "", [], None, "Lemon dishwash gel."),
    "pods": ("Laundry Detergent Pods (24)", "SparkleHome", "24", "pc", "cleaning", "399", None, "", [], None, "Pre-measured laundry pods."),
    "floor": ("Floor Cleaner", "SparkleHome", "1", "l", "cleaning", "189", "215", "", [], None, "Pine floor cleaner."),
    "bags": ("Garbage Bags (Medium, 30)", "BinWise", "30", "pc", "cleaning", "99", None, "", [], None, "Medium garbage bags."),
    "tissue": ("Kitchen Towels (2 rolls)", "SoftRoll", "2", "pc", "cleaning", "110", None, "", [], None, "Two absorbent kitchen rolls."),
    "soap": ("Neem Soap (3 pack)", "Herbveda", "3", "pc", "personal-care", "105", "120", "", [], None, "Three 100 g neem soaps."),
    "toothpaste": ("Toothpaste", "Brightsmile", "150", "g", "personal-care", "95", None, "", [], None, "Fluoride toothpaste."),
    "shampoo": ("Herbal Shampoo", "Herbveda", "340", "ml", "personal-care", "245", "275", "", [], None, "Mild herbal shampoo."),
    "handwash": ("Hand Wash", "Herbveda", "250", "ml", "personal-care", "89", None, "", [], None, "Gentle hand wash."),
    "wipes": ("Baby Wipes (72)", "Tiny Care", "72", "pc", "baby-care", "149", "179", "", [], None, "Water-based baby wipes."),
    "diapers": ("Diapers, Medium (34)", "Tiny Care", "34", "pc", "baby-care", "599", "699", "", [], None, "Medium diapers, 7–12 kg."),
    "dog_food": ("Adult Dog Food", "Wagwell", "3", "kg", "pet-care", "899", "999", "", [], None, "Chicken and rice dry food."),
}
FRESH = {"vegetables", "fruits", "leafy-greens-herbs"}
GROUPS = {
    "produce": [k for k, v in ITEMS.items() if v[4] in FRESH and k != "org_spinach"],
    "dairy": ["milk", "milk_half", "curd", "yogurt", "paneer", "butter", "cheese", "eggs", "eggs_brown"],
    "bakery": ["bread", "bread_multi", "pav"],
    "breakfast": ["muesli", "oats", "cornflakes", "coffee", "tea"],
    "staples": ["basmati", "sona", "sona_kisan", "atta", "toor", "moong", "chana", "groundnut_oil", "sunflower", "ghee", "salt", "sugar",
                "jaggery", "turmeric", "chilli_powder"],
    "snacks": ["peanuts", "ragi_chips", "chips", "chocolate", "biscuits", "noodles", "water", "sparkling", "oj", "cola"],
    "home": ["dishwash", "pods", "floor", "bags", "tissue"],
    "personal": ["soap", "toothpaste", "shampoo", "handwash"],
    "baby_pet": ["wipes", "diapers", "dog_food"],
}

DAILY = [(d, time(7), time(22)) for d in range(7)]
# name, locality, store categories, price level, (eta min, max), base fee, min order, free above, independent, verified,
# accepting, radius km, fast radius km (0 = no fast delivery), hours, assortment, price factor, extra items, about
STORES = [
    ("FreshCart Daily", "Koramangala", ["Fruits & Vegetables", "Dairy & Eggs"], 1, (15, 30), "15", "99", "499", False, True, True, "6", "3",
     DAILY, ["produce", "dairy", "bakery", "breakfast", "snacks"], "1.04", ["org_spinach"], "Neighbourhood fresh market with a daily produce delivery."),
    ("Pantry Point", "Koramangala", ["Staples", "Snacks & Drinks"], 1, (20, 35), "19", "149", "799", False, True, True, "5", "3",
     DAILY, ["staples", "snacks", "breakfast", "home"], "1.00", ["milk", "eggs"], "Staples, snacks and household basics at everyday prices."),
    ("Orchard & Co. Organics", "HSR Layout", ["Fruits & Vegetables", "Staples"], 3, (30, 50), "29", "299", None, True, True, True, "8", "0",
     [(d, time(9), time(20)) for d in range(6)], ["breakfast"], "1.18",
     ["org_spinach", "avocado", "jaggery", "groundnut_oil", "muesli", "mango", "apple", "carrot", "tomato", "coriander", "mint", "lemon", "yogurt", "eggs_brown"],
     "Organic produce and pantry from small farms. Closed Sundays."),
    ("Corner Kirana Express", "Jayanagar", ["Staples", "Dairy & Eggs"], 1, (10, 20), "0", "0", None, True, False, True, "4", "2.5",
     [(d, time(6, 30), time(23)) for d in range(7)], ["staples", "dairy", "snacks", "home", "personal"], "0.97", ["onion", "potato", "tomato", "bread"],
     "Family-run kirana since 1998."),
    ("Daily Basket Express", "Bellandur", ["Household", "Snacks & Drinks"], 1, (15, 30), "9", "99", "599", False, False, True, "7", "3",
     [(d, time(6), time(23, 59)) for d in range(7)], ["home", "personal", "baby_pet", "snacks", "dairy"], "1.03", [],
     "Household, personal care, baby and pet essentials."),
    ("Sri Lakshmi Provisions", "Indiranagar", ["Staples", "Dairy & Eggs"], 1, (10, 25), "10", "149", "399", True, True, True, "5", "3",
     [(d, time(6, 30), time(22, 30)) for d in range(7)], ["staples", "dairy", "bakery", "snacks", "home", "personal"], "0.98",
     ["onion", "potato", "tomato", "chilli", "coriander", "ginger", "lemon", "banana", "coconut"], "Indiranagar's neighbourhood provision store."),
    ("Gokul Dairy Corner", "Malleshwaram", ["Dairy & Eggs"], 1, (10, 20), "10", "0", None, True, False, True, "4", "2",
     [(d, time(5, 30), time(11)) for d in range(7)] + [(d, time(16, 30), time(21)) for d in range(7)],
     ["bakery"], "1.00", ["milk_gokul", "milk", "curd", "paneer", "butter", "ghee", "eggs", "eggs_brown", "coffee", "tea"],
     "Fresh milk every morning from partner farms. Open mornings and evenings."),
    ("Bake Street Breads", "Indiranagar", ["Bakery"], 2, (15, 25), "20", "149", "499", True, False, True, "4", "3",
     [(d, time(7), time(21)) for d in range(7)], [], "1.05", ["sourdough", "croissant", "bread", "bread_multi", "pav", "butter", "cheese", "eggs", "coffee"],
     "Small-batch bakery. Breads out of the oven by 8 AM."),
    ("Green Basket Farm Produce", "Koramangala", ["Fruits & Vegetables"], 1, (20, 35), "15", "149", "299", True, True, True, "6", "3",
     [(d, time(6), time(21)) for d in range(7)], ["produce"], "0.95", ["org_spinach", "eggs"],
     "Vegetables and fruit picked up from growers near Hosur each morning."),
    ("Metro Mart Supermarket", "Whitefield", ["Staples", "Household"], 2, (25, 45), "25", "199", "999", False, True, False, "8", "4",
     [(d, time(8), time(23)) for d in range(7)], ["staples", "dairy", "snacks", "home", "personal", "baby_pet", "produce"], "0.96", [],
     "Large-format supermarket (temporarily not taking orders)."),
]

# store slug -> [(title, description, type, value, max, min order)]
OFFERS = {
    "freshcart-daily": [("Flat ₹40 off over ₹499", "On your FreshCart basket.", "flat", "40", None, "499")],
    "sri-lakshmi-provisions": [("10% off over ₹300", "Up to ₹75 off on any basket.", "percent", "10", "75", "300")],
    "green-basket-farm-produce": [("Free delivery over ₹299", "On fresh produce baskets.", "free_delivery", "0", None, "299")],
    "bake-street-breads": [("₹30 off over ₹250", "Fresh bakes, a little cheaper.", "flat", "30", None, "250")],
    "daily-basket-express": [("Free delivery all day", "No minimum on delivery fee waiver.", "free_delivery", "0", None, "0")],
}
# (store slug, item key, percent, kind)
DEALS = [("pantry-point", "basmati", 12, ProductDeal.Kind.LIMITED), ("freshcart-daily", "apple", 15, ProductDeal.Kind.FLASH),
         ("sri-lakshmi-provisions", "groundnut_oil", 10, ProductDeal.Kind.PRICE_DROP)]


def _h(*parts) -> int:
    return crc32("|".join(parts).encode())


def _price(base: str, factor: str, key: str) -> Decimal:
    jitter = Decimal((_h(key) % 7) - 3) / 100  # -3% … +3%, stable per store+item
    return (D(base) * D(factor) * (1 + jitter)).quantize(D("1"), rounding=ROUND_HALF_UP)


def _items(cats) -> dict:
    out = {}
    for key, (name, brand, size, unit, cslug, price, mrp, diet, attrs, media, desc) in ITEMS.items():
        image, credit, source = MEDIA.get(media, ("", "", "")) if media else ("", "", "")
        out[key], _ = GroceryItem.objects.update_or_create(
            name=name, brand=brand, size_value=D(size), size_unit=unit,
            defaults=dict(category=cats[cslug], description=desc, dietary=diet, attributes=attrs,
                          image_url=image, image_credit=credit, image_source=source, is_active=True))
    return out


def _listing(store, item: GroceryItem, key: str, factor: str, menu: dict, pos: int, today):
    name, brand, size, unit, cslug, base, mrp, *_ = ITEMS[key]
    price = _price(base, factor, f"{store.slug}|{key}")
    mrp_d = D(mrp) if mrp and D(mrp) > price else None
    h = _h(store.slug, key, "stock")
    stock = 0 if h % 14 == 0 else (h % 4) + 1 if h % 9 == 0 else 8 + h % 50
    fresh = cslug in FRESH
    menu_cat = menu.get(cslug)
    if menu_cat is None:
        menu_cat, _ = MenuCategory.objects.get_or_create(store=store, name=item.category.name, defaults={"position": item.category.position})
        menu[cslug] = menu_cat
    # Adopt a listing that predates the item registry (same store and name) instead of duplicating it.
    p = (Product.objects.filter(store=store, grocery_item=item).first()
         or Product.objects.filter(store=store, name=name, grocery_item__isnull=True).first() or Product(store=store))
    fields = dict(name=name, brand=brand, unit_label=item.size_label, category=menu_cat, grocery_item=item, price=price,
                  compare_at_price=mrp_d, stock_quantity=stock, description=item.description,
                  dietary=item.dietary or "unspecified", is_available=True, is_active=True, position=pos,
                  received_on=(today if h % 5 else today - timedelta(days=1)) if fresh else None,
                  variable_weight=fresh and unit in ("kg", "g"))
    for k, v in fields.items():
        setattr(p, k, v)
    p.save()
    return p


def seed_groceries(log) -> None:
    cats = {}
    for pos, (slug, name, section, icon, syn) in enumerate(CATEGORIES):
        cats[slug], _ = GroceryCategory.objects.update_or_create(slug=slug, defaults=dict(
            name=name, section=section, icon=icon, synonyms=syn, position=(pos + 1) * 10, is_active=True))
    items = _items(cats)
    today = timezone.localtime(timezone.now()).date()
    now = timezone.now()
    listings = 0
    for (name, loc, store_cats, price_level, eta, fee, minimum, free_above, independent, verified, accepting, radius, fast_r,
         hours, groups, factor, extra, about) in STORES:
        slug = slugify(name)
        cat_objs = [StoreCategory.objects.get_or_create(store_type=StoreType.GROCERY, slug=slugify(c), defaults={"name": c})[0] for c in store_cats]
        lat, lng = locality_point(loc, name)
        store, _ = Store.objects.update_or_create(slug=slug, defaults=dict(
            name=name, store_type=StoreType.GROCERY, status=Store.Status.ACTIVE, is_accepting_orders=accepting,
            description=f"{about} {MARKER}.", city="Bengaluru", locality=loc, latitude=lat, longitude=lng,
            price_level=price_level, delivery_time_min=eta[0], delivery_time_max=eta[1], delivery_fee=D(fee),
            min_order_amount=D(minimum), free_delivery_above=D(free_above) if free_above else None, cod_enabled=True,
            verified_at=(Store.objects.filter(slug=slug).values_list("verified_at", flat=True).first() or now) if verified else None,
        ))
        store.categories.add(*cat_objs)
        GroceryStoreSettings.objects.update_or_create(store=store, defaults=dict(
            is_independent=independent, about=about, address_line=f"{loc}, Bengaluru",
            policies="Substitutions only as you choose at checkout. Damaged or missing items: report within 24 hours for a refund.",
            freshness_note="Produce restocked every morning." if "produce" in groups or slug == "green-basket-farm-produce" else "",
            delivery_radius_km=D(radius), fast_enabled=D(fast_r) > 0, fast_radius_km=D(fast_r) if D(fast_r) > 0 else D("3"),
            prep_minutes=8 if price_level == 1 else 12, scheduled_enabled=True, slot_minutes=60, slot_capacity=6))
        StoreHours.objects.filter(store=store).delete()
        StoreHours.objects.bulk_create([StoreHours(store=store, weekday=d, opens_at=o, closes_at=c) for d, o, c in hours])
        keys = list(dict.fromkeys([k for g in groups for k in GROUPS[g]] + extra))
        menu = {}
        for pos, key in enumerate(keys):
            _listing(store, items[key], key, factor, menu, pos, today)
            listings += 1
        for title, desc, kind, value, cap, min_amount in OFFERS.get(slug, []):
            StoreOffer.objects.update_or_create(store=store, title=title, defaults=dict(
                description=desc, is_active=True, discount_type=kind, discount_value=D(value),
                max_discount=D(cap) if cap else None, min_order_amount=D(min_amount)))
    for slug, key, pct, kind in DEALS:
        name, brand, *_ = ITEMS[key]
        p = Product.objects.filter(store__slug=slug, grocery_item=items[key]).first()
        if p:
            ProductDeal.objects.update_or_create(product=p, kind=kind, defaults=dict(
                percent_off=pct, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=4), is_active=True))
    # Grocery listings that predate the item registry (none expected) stay hidden from Groceries rather than guessed.
    log(f"groceries: {len(CATEGORIES)} categories, {len(ITEMS)} items, {len(STORES)} vendors, {listings} listings")


def recompute_store_ratings() -> None:
    """Grocery store ratings come only from customers' order reviews."""
    from apps.orders.models import OrderReview

    for store in Store.objects.filter(store_type=StoreType.GROCERY):
        agg = OrderReview.objects.filter(store=store).aggregate(a=Avg("rating"), n=Count("id"))
        Store.objects.filter(pk=store.pk).update(rating_average=D(agg["a"] or 0).quantize(D("0.1"), rounding=ROUND_HALF_UP),
                                                 rating_count=agg["n"])


NS = uuid.UUID("0b8f6d1e-3c3a-4d55-9a71-6f7a1e2c9b11")


# --- order history: the only source of Buy again, Running low, Frequently bought together, Popular and ratings ----

TEST_HISTORY = [  # (store, days ago, [(item, qty)])
    ("sri-lakshmi-provisions", 26, [("milk", 2), ("bread", 1), ("eggs", 1), ("sona", 1), ("toor", 1), ("groundnut_oil", 1)]),
    ("sri-lakshmi-provisions", 21, [("milk", 2), ("bread", 1), ("atta", 1), ("onion", 1), ("tomato", 1)]),
    ("sri-lakshmi-provisions", 16, [("milk", 2), ("bread", 1), ("eggs", 1), ("curd", 1)]),
    ("sri-lakshmi-provisions", 11, [("milk", 2), ("bread", 1), ("onion", 1), ("tomato", 1), ("chilli", 1)]),
    ("freshcart-daily", 9, [("banana", 1), ("apple", 1), ("yogurt", 2)]),
    ("sri-lakshmi-provisions", 6, [("milk", 2), ("bread", 1), ("eggs", 1), ("curd", 1)]),
]
VIEWER_BASKETS = [
    [("sona", 1), ("toor", 1), ("groundnut_oil", 1), ("salt", 1)],
    [("milk", 2), ("bread", 1), ("eggs", 1)],
    [("sona", 1), ("toor", 1), ("sunflower", 1), ("turmeric", 1)],
    [("onion", 1), ("tomato", 1), ("potato", 1), ("coriander", 1)],
    [("basmati", 1), ("toor", 1), ("groundnut_oil", 1)],
    [("milk", 1), ("curd", 1), ("paneer", 1)],
]
VIEWER_STORES = ["sri-lakshmi-provisions", "freshcart-daily", "pantry-point", "green-basket-farm-produce", "corner-kirana-express",
                 "sri-lakshmi-provisions", "orchard-co-organics", "sri-lakshmi-provisions"]
REVIEWS = [(5, "Everything fresh and packed well."), (4, "Quick delivery, one item was swapped as I asked."), (5, ""),
           (4, "Good prices for the area."), (3, "Delivery took longer than the estimate."), (5, "Friendly store, accurate order.")]
PATH = ["placed", "confirmed", "preparing", "ready", "out_for_delivery", "delivered"]


def _history_order(customer, store, address_snapshot, lines, days, key, review=None) -> bool:
    from apps.groceries.models import GroceryOrderDetails
    from apps.orders.models import Order, OrderItem, OrderReview, OrderStatusEvent
    from apps.payments.models import Payment

    if Order.objects.filter(customer=customer, idempotency_key=key).exists():
        return False
    at = timezone.now() - timedelta(days=days, hours=_h(str(key)) % 6)
    products = []
    for item_key, qty in lines:
        name, brand, size, unit, *_ = ITEMS[item_key]
        p = Product.objects.filter(store=store, grocery_item__name=name, grocery_item__brand=brand,
                                   grocery_item__size_value=D(size), grocery_item__size_unit=unit).first()
        if p:
            products.append((p, qty))
    if not products:
        return False
    subtotal = sum((p.price * q for p, q in products), D("0"))
    fee = D("0") if store.free_delivery_above is not None and subtotal >= store.free_delivery_above else store.delivery_fee
    from django.conf import settings

    tax = (subtotal * settings.CLICK_TAX_RATE).quantize(D("0.01"))
    order = Order.objects.create(
        customer=customer, store=store, status="delivered", delivery_address=address_snapshot, subtotal=subtotal, delivery_fee=fee,
        tax=tax, total=subtotal + fee + tax, currency=store.currency, idempotency_key=key,
        estimated_delivery_at=at + timedelta(minutes=35), delivered_at=at + timedelta(minutes=32))
    Order.objects.filter(pk=order.pk).update(created_at=at)
    OrderItem.objects.bulk_create([OrderItem(order=order, product=p, product_name=p.name, unit_price=p.price, quantity=q,
                                             line_total=p.price * q) for p, q in products])
    for p, q in products:
        Product.objects.filter(pk=p.pk).update(units_sold=p.units_sold + q)
        p.units_sold += q
    for i, st in enumerate(PATH):
        ev = OrderStatusEvent.objects.create(order=order, from_status=PATH[i - 1] if i else "", to_status=st, actor=None)
        OrderStatusEvent.objects.filter(pk=ev.pk).update(created_at=at + timedelta(minutes=6 * i))
    pay = Payment.objects.create(order=order, method="cash_on_delivery", status=Payment.Status.CAPTURED, amount=order.total, currency=order.currency)
    Payment.objects.filter(pk=pay.pk).update(created_at=at)
    GroceryOrderDetails.objects.create(order=order, delivery_mode="fast", substitution="similar", eta_min=20, eta_max=30)
    from apps.rewards.services import award_for_delivered_order

    award_for_delivered_order(order)  # the real loyalty rule, as for any delivered order
    if review:
        r = OrderReview.objects.create(order=order, customer=customer, store=store, rating=review[0], comment=review[1])
        OrderReview.objects.filter(pk=r.pk).update(created_at=at + timedelta(hours=2))
    return True


def seed_grocery_history(profile, log) -> None:
    from .showtime import VIEWERS, _viewer

    address = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
    made = 0
    for i, (slug, days, lines) in enumerate(TEST_HISTORY):
        store = Store.objects.get(slug=slug)
        made += _history_order(profile, store, address.snapshot(), lines, days, uuid.uuid5(NS, f"test-{i}"))
    for v, (name, loc) in enumerate(VIEWERS):
        viewer = _viewer(name, loc)
        snap = {"label": "home", "recipient_name": f"{name} (dev viewer)", "line1": "Dev address", "city": "Bengaluru", "locality": loc}
        for j in range(3):
            slug = VIEWER_STORES[(v + j * 3) % len(VIEWER_STORES)]
            store = Store.objects.get(slug=slug)
            basket = VIEWER_BASKETS[(v + j) % len(VIEWER_BASKETS)]
            review = REVIEWS[(v * 3 + j) % len(REVIEWS)] if (v + j) % 2 == 0 else None
            made += _history_order(viewer, store, snap, basket, 2 + (v * 3 + j * 7) % 26, uuid.uuid5(NS, f"viewer-{name}-{j}"), review)
    recompute_store_ratings()
    log(f"grocery history: {made} delivered orders (test customer + dev viewers), store ratings from reviews")
