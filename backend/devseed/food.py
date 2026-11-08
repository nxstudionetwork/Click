"""DEVELOPMENT MOCK DATA: fuller restaurant menus, dish customisations and checkout-applicable offer rules."""

from decimal import Decimal as D

from django.utils.text import slugify

from apps.catalog.models import Product, ProductOption, ProductOptionGroup
from apps.stores.models import Store, StoreOffer, StoreType

from .catalog import RESTAURANTS, _product

# More dishes per cuisine (name, dietary, price), appended after the base menu in devseed.catalog.MENU.
EXTRA_MENU = {
    "Biryani": [("Veg Dum Biryani", "veg", "219"), ("Chicken 65 Biryani", "non_veg", "319"), ("Egg Biryani", "non_veg", "229"), ("Mirchi ka Salan", "veg", "89"), ("Double ka Meetha", "veg", "119")],
    "Pizza": [("Farmhouse Veggie", "veg", "299"), ("Pepperoni Classic", "non_veg", "399"), ("Paneer Tikka Pizza", "veg", "329"), ("Garlic Bread Sticks", "veg", "149"), ("Tiramisu Jar", "veg", "189")],
    "South Indian": [("Rava Onion Dosa", "veg", "139"), ("Set Dosa (3)", "veg", "109"), ("Medu Vada (2)", "veg", "79"), ("Pongal", "veg", "99"), ("Filter Coffee", "veg", "49")],
    "Burgers": [("Spicy Chicken Burger", "non_veg", "229"), ("Mushroom Swiss Burger", "veg", "209"), ("Loaded Fries", "veg", "149"), ("Chocolate Shake", "veg", "169")],
    "Healthy": [("Greek Salad", "veg", "269"), ("Millet Khichdi Bowl", "vegan", "229"), ("Cold-pressed Green Juice", "vegan", "149"), ("Hummus & Veg Platter", "vegan", "249")],
    "Desserts": [("Mango Kulfi", "veg", "119"), ("Chocolate Lava Cake", "veg", "169"), ("Rabri Jalebi", "veg", "139")],
    "Chinese": [("Hakka Noodles", "veg", "189"), ("Chilli Chicken Dry", "non_veg", "269"), ("Veg Fried Rice", "veg", "179"), ("Spring Rolls (6)", "veg", "159")],
    "North Indian": [("Paneer Butter Masala", "veg", "279"), ("Chicken Tikka (6 pc)", "non_veg", "309"), ("Jeera Rice", "veg", "139"), ("Butter Roti", "veg", "35")],
    "Cafe": [("Masala Chai", "veg", "69"), ("Iced Americano", "vegan", "159"), ("Club Sandwich", "non_veg", "229")],
    "Thai": [("Massaman Curry", "veg", "339"), ("Basil Fried Rice", "veg", "249"), ("Mango Sticky Rice", "vegan", "189")],
    "Mexican": [("Veg Quesadilla", "veg", "229"), ("Chicken Burrito Bowl", "non_veg", "299"), ("Churros with Chocolate", "veg", "159")],
    "Bakery": [("Butter Croissant", "veg", "99"), ("Banana Walnut Bread", "veg", "149"), ("Garlic Focaccia", "veg", "179")],
    "Kerala": [("Kerala Parotta & Chicken Curry", "non_veg", "259"), ("Avial with Rice", "vegan", "199"), ("Payasam", "veg", "99")],
    "Momos": [("Kurkure Veg Momos (8)", "veg", "149"), ("Chicken Tandoori Momos (8)", "non_veg", "189"), ("Thukpa", "non_veg", "179")],
    "Japanese": [("Veg Ramen", "veg", "449"), ("Chicken Teriyaki Don", "non_veg", "499"), ("Edamame", "vegan", "249")],
    "Middle Eastern": [("Paneer Shawarma Roll", "veg", "139"), ("Chicken Kebab Platter", "non_veg", "399"), ("Baklava (2 pc)", "veg", "149")],
}

# Customisation rules by cuisine: [(group, min, max, [(option, price_delta)]), ...], applied to the main dishes.
OPTION_RULES = {
    "Biryani": [("Portion", 1, 1, [("Regular", "0"), ("Family pack (serves 3)", "220")]),
                ("Add-ons", 0, 3, [("Raita", "30"), ("Extra salan", "40"), ("Boiled egg", "25")])],
    "Pizza": [("Size", 1, 1, [("Regular 8\"", "0"), ("Medium 10\"", "120"), ("Large 12\"", "220")]),
              ("Extra toppings", 0, 3, [("Extra cheese", "60"), ("Jalapeños", "40"), ("Black olives", "40")])],
    "Burgers": [("Make it a meal", 0, 1, [("Fries & a drink", "99")]),
                ("Extras", 0, 2, [("Cheese slice", "30"), ("Extra patty", "80")])],
    "Momos": [("Dips", 0, 2, [("Extra red chutney", "15"), ("Mayo dip", "15")])],
}
# Only the dishes these rules make sense for (sides/desserts stay simple).
NOT_CUSTOMISABLE = {"Mirchi ka Salan", "Double ka Meetha", "Garlic Bread Sticks", "Tiramisu Jar", "Loaded Fries", "Chocolate Shake", "Thukpa"}
COFFEE_SIZES = ("Size", 1, 1, [("Regular", "0"), ("Large", "40")])
COFFEES = {"Hazelnut Cappuccino", "Cold Brew Tonic", "Iced Americano", "Filter Coffee"}

# Offers the checkout engine can apply (conditions it can express: % with cap, flat, free delivery, minimum order).
# Offers with other conditions (first order, weekends, time of day, specific items, B1G1) stay display-only.
OFFER_RULES = {
    "20% off up to ₹100": ("percent", "20", "100", "0"),
    "Free delivery over ₹399": ("free_delivery", "0", None, "399"),
    "₹200 off over ₹1,499": ("flat", "200", None, "1499"),
    "Flat ₹40 off over ₹499": ("flat", "40", None, "499"),
    "Free delivery all day": ("free_delivery", "0", None, "0"),
}


def _options(product, rules):
    for gpos, (group, lo, hi, options) in enumerate(rules):
        g, _ = ProductOptionGroup.objects.update_or_create(product=product, name=group, defaults={"min_select": lo, "max_select": hi, "position": gpos})
        for opos, (name, delta) in enumerate(options):
            ProductOption.objects.update_or_create(group=g, name=name, defaults={"price_delta": D(delta), "position": opos, "is_available": True})


def seed_food(log) -> None:
    from .catalog import MENU

    groups = 0
    for name, cats, *_ in RESTAURANTS:
        store = Store.objects.get(slug=slugify(name))
        for pos, cuisine in enumerate(cats):
            for i, (item, dietary, price) in enumerate(EXTRA_MENU.get(cuisine, []), start=len(MENU[cuisine])):
                _product(store, cuisine, pos, i, item, price, dietary=dietary)
            for p in Product.objects.filter(store=store, category__name=cuisine):
                if cuisine in OPTION_RULES and p.name not in NOT_CUSTOMISABLE:
                    _options(p, OPTION_RULES[cuisine]); groups += 1
                if p.name in COFFEES:
                    _options(p, [COFFEE_SIZES]); groups += 1

    redeemable = 0
    for title, (kind, value, cap, minimum) in OFFER_RULES.items():
        redeemable += StoreOffer.objects.filter(title=title).update(
            discount_type=kind, discount_value=D(value), max_discount=D(cap) if cap else None, min_order_amount=D(minimum))
    count = Product.objects.filter(store__store_type=StoreType.RESTAURANT).count()
    log(f"food: {count} dishes, customisations on {groups} dishes, {redeemable} offers applicable at checkout")
