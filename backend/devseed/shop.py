"""
DEVELOPMENT MOCK DATA: Click. Shopping marketplace.

  * a 16-category taxonomy with subcategories, search synonyms and category attribute definitions
  * fictional brands (no real brand is implied) and 12 retail sellers (one outside Bengaluru, one unverified,
    one prepaid-only) with their own delivery fee, free-delivery threshold, dispatch time and return terms
  * about 200 listings with real attribute values, variants (size / colour) with their own stock, and genuine
    compare-at prices on some; listing dates spread over 4 months so "New Arrivals" means something
  * deals with real start/end times (some limited by quantity) and Shopping campaigns with date windows
  * reviewers who buy through the real cart and checkout, receive their orders through the real status flow and
    then review them: every rating, review count and "best seller" figure comes from those records

Listings have no photos: Click. never borrows stock photos for specific products, so the app shows its branded
placeholder until a seller uploads real photos (Django admin -> Products -> images).
"""

import uuid
from datetime import timedelta
from decimal import Decimal as D
from zlib import crc32

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.carts import services as cart_services
from apps.core.api.exceptions import DomainError
from apps.catalog.models import (AttributeDefinition, Brand, MenuCategory, Product, ProductAttributeValue, ProductDeal, ProductVariant,
                                 ShopCategory)
from apps.customers.models import Address, CustomerProfile
from apps.orders import services as order_services
from apps.orders.models import Order, OrderStatus, OrderStatusEvent
from apps.shop.models import ProductReview, ShopCampaign
from apps.shop.reviews import save_review
from apps.stores.models import Store, StoreCategory, StoreOffer, StoreType
from apps.users.models import User
from apps.wallet.models import WalletTransaction

from . import MARKER, locality_point


def h(s: str) -> int:
    return crc32(s.encode())


A = AttributeDefinition.Kind
# slug: (name, icon, synonyms, return days, warranty, [(code, name, kind, unit, filterable, comparable)])
TOP = {
    "electronics": ("Electronics", "device", "gadgets,tech", 7, "1 year manufacturer warranty", [
        ("color", "Colour", A.CHOICE, "", True, True), ("connectivity", "Connectivity", A.CHOICE, "", True, True)]),
    "mobiles-accessories": ("Mobiles & Accessories", "phone", "mobile,phone accessories", 7, "6 months warranty", [
        ("compatible", "Compatible with", A.CHOICE, "", True, True), ("material", "Material", A.CHOICE, "", True, True),
        ("color", "Colour", A.CHOICE, "", True, True)]),
    "fashion": ("Fashion", "shirt", "clothes,clothing,apparel,wear", 15, "", [
        ("fabric", "Fabric", A.CHOICE, "", True, True), ("fit", "Fit", A.CHOICE, "", True, True), ("sleeve", "Sleeve", A.CHOICE, "", True, True)]),
    "footwear": ("Footwear", "shoe", "shoes,footwear", 15, "", [
        ("material", "Upper material", A.CHOICE, "", True, True), ("closure", "Closure", A.CHOICE, "", True, True),
        ("color", "Colour", A.CHOICE, "", True, True)]),
    "home-kitchen": ("Home & Kitchen", "home", "home,household", 10, "", [
        ("material", "Material", A.CHOICE, "", True, True), ("color", "Colour", A.CHOICE, "", True, True),
        ("dimensions", "Dimensions", A.TEXT, "", False, True)]),
    "beauty": ("Beauty & Personal Care", "beauty", "beauty,personal care,cosmetics", 7, "", [
        ("skin_type", "Suitable for", A.CHOICE, "", True, True), ("volume", "Volume", A.NUMBER, "ml", False, True),
        ("ingredient", "Key ingredient", A.CHOICE, "", True, True)]),
    "appliances": ("Appliances", "appliance", "appliance,appliances", 10, "1 year manufacturer warranty", [
        ("power", "Power", A.NUMBER, "W", False, True), ("capacity", "Capacity", A.CHOICE, "", True, True),
        ("color", "Colour", A.CHOICE, "", True, True)]),
    "books": ("Books", "book", "book,novel,reading", 7, "", [
        ("format", "Format", A.CHOICE, "", True, True), ("language", "Language", A.CHOICE, "", True, True),
        ("author", "Author", A.TEXT, "", False, True), ("pages", "Pages", A.NUMBER, "", False, True)]),
    "sports-fitness": ("Sports & Fitness", "dumbbell", "sports,fitness,gym,workout", 10, "", [
        ("material", "Material", A.CHOICE, "", True, True), ("weight", "Weight", A.TEXT, "", False, True),
        ("color", "Colour", A.CHOICE, "", True, True)]),
    "toys-games": ("Toys & Games", "toy", "toys,games,toy", 7, "", [
        ("age", "Age group", A.CHOICE, "", True, True), ("material", "Material", A.CHOICE, "", True, True)]),
    "baby-kids": ("Baby & Kids", "baby", "baby,kids,children,child", 7, "", [
        ("age", "Age group", A.CHOICE, "", True, True), ("material", "Material", A.CHOICE, "", True, True)]),
    "bags-luggage": ("Bags & Luggage", "briefcase", "bag,bags,luggage", 10, "1 year warranty", [
        ("capacity", "Capacity", A.CHOICE, "", True, True), ("material", "Material", A.CHOICE, "", True, True),
        ("color", "Colour", A.CHOICE, "", True, True)]),
    "jewellery": ("Jewellery", "gem", "jewelry,jewellery", 7, "", [
        ("material", "Material", A.CHOICE, "", True, True), ("color", "Colour", A.CHOICE, "", True, True)]),
    "pet-supplies": ("Pet Supplies", "paw", "pet,pets,dog,cat", 7, "", [
        ("pet", "For", A.CHOICE, "", True, True), ("material", "Material", A.CHOICE, "", True, True)]),
    "office-stationery": ("Office & Stationery", "edit", "stationery,office", 7, "", [
        ("material", "Material", A.CHOICE, "", True, True), ("pages", "Pages", A.NUMBER, "", False, True)]),
    "furniture": ("Furniture", "sofa", "furniture", 10, "1 year warranty", [
        ("material", "Material", A.CHOICE, "", True, True), ("color", "Colour", A.CHOICE, "", True, True),
        ("dimensions", "Dimensions", A.TEXT, "", False, True)]),
}

# Subcategory-specific attributes (in addition to the top category's).
SUB_ATTRS = {
    "audio": [("battery", "Battery life", A.NUMBER, "hours", False, True), ("anc", "Noise cancellation", A.BOOLEAN, "", True, True),
              ("water", "Water resistance", A.CHOICE, "", True, True)],
    "wearables": [("battery", "Battery life", A.NUMBER, "days", False, True), ("display", "Display", A.CHOICE, "", True, True),
                  ("water", "Water resistance", A.CHOICE, "", True, True)],
    "power-charging": [("output", "Output", A.CHOICE, "", True, True)],
}

# Sellers: slug, name, locality, categories, fee, free above, dispatch days, cod, verified, return policy, rating, count
SELLERS = [
    ("volt-electronics", "Volt Electronics", "Indiranagar", ["Electronics"], "49", "499", 1, True, True, "7-day returns on unopened items; replacement for defects."),
    ("thread-loom", "Thread & Loom", "Koramangala", ["Fashion"], "39", "999", 2, True, True, "15-day easy returns on unworn items with tags."),
    ("hearth-home-store", "Hearth Home Store", "Jayanagar", ["Home & Kitchen"], "49", "799", 2, True, True, "10-day returns; damaged items replaced."),
    ("paperback-lane", "Paperback Lane", "Basavanagudi", ["Books & Stationery"], "29", "499", 1, True, True, "7-day replacement for damaged or misprinted books."),
    ("stride-sports-co", "Stride Sports Co.", "Whitefield", ["Sports & Fitness"], "49", "999", 1, True, True, "15-day returns on unused items."),
    ("pixel-point-mobiles", "Pixel Point Mobiles", "Malleshwaram", ["Electronics"], "29", "399", 1, True, True, "7-day replacement for defects."),
    ("glow-theory-beauty", "Glow Theory Beauty", "Koramangala", ["Beauty"], "39", "599", 1, True, True, "7-day returns on sealed products only."),
    ("little-tribe-kids", "Little Tribe Kids", "HSR Layout", ["Kids"], "49", "799", 2, True, True, "7-day returns on unused toys and clothes."),
    ("kraft-carry", "Kraft & Carry", "Indiranagar", ["Bags & Footwear"], "59", "1499", 2, True, False, "10-day returns on unused items."),
    ("woodnest-living", "Woodnest Living", "Bellandur", ["Furniture"], "149", "4999", 3, True, True, "10-day returns; assembly help on request."),
    ("appliance-hub", "Appliance Hub", "Yelahanka", ["Appliances"], "79", "1999", 2, True, True, "10-day replacement for manufacturing defects."),
    ("mumbai-loom-house", "Mumbai Loom House", "Mumbai", ["Fashion", "Jewellery"], "79", "1499", 3, False, True, "15-day returns. Prepaid orders only."),
]
MUMBAI = (D("19.076000"), D("72.877700"))

# Subcategories: (top, slug, name, synonyms, seller, variants spec, products)
# product: (name, brand, price, mrp or None, {attribute code: value}, extra)
#   extra: colors=[...], sizes=[...], stock=n, highlights=[...], returns=None (not returnable), replacement=True
SIZES = ["S", "M", "L", "XL"]
SHOE = ["UK 6", "UK 7", "UK 8", "UK 9", "UK 10"]
SUBS = [
    ("electronics", "audio", "Audio", "headphones,headphone,earbuds,earphones,speaker,speakers,audio", "volt-electronics", None, [
        ("Pulse ANC Wireless Earbuds", "Sonique", "2299", "3999", {"connectivity": "Bluetooth 5.3", "battery": "32", "anc": "Yes", "water": "IPX4", "color": "Black"}, {}),
        ("Pulse Lite Wireless Earbuds", "Sonique", "1299", "1999", {"connectivity": "Bluetooth 5.3", "battery": "28", "anc": "No", "water": "IPX4", "color": "White"}, {}),
        ("Studio Over-ear Headphones", "Auralis", "4999", "6999", {"connectivity": "Bluetooth 5.4", "battery": "45", "anc": "Yes", "water": "None", "color": "Black"}, {}),
        ("Commute On-ear Headphones", "Auralis", "1799", None, {"connectivity": "Bluetooth 5.3", "battery": "30", "anc": "No", "water": "None", "color": "Blue"}, {}),
        ("Neckband Sport Earphones", "Kinetiq", "999", "1499", {"connectivity": "Bluetooth 5.3", "battery": "20", "anc": "No", "water": "IPX5", "color": "Black"}, {}),
        ("Wired Studio Earphones", "Kinetiq", "449", None, {"connectivity": "Wired", "battery": "0", "anc": "No", "water": "None", "color": "Black"}, {}),
        ("Boomlet Go Portable Speaker", "Boomlet", "1999", "2999", {"connectivity": "Bluetooth 5.3", "battery": "12", "anc": "No", "water": "IP67", "color": "Teal"}, {}),
        ("Boomlet Max Party Speaker", "Boomlet", "6499", "8999", {"connectivity": "Bluetooth 5.4", "battery": "18", "anc": "No", "water": "IPX5", "color": "Black"}, {}),
        ("Clarity Gaming Headset", "Kinetiq", "2499", None, {"connectivity": "Wired", "battery": "0", "anc": "No", "water": "None", "color": "Black"}, {}),
        ("Pulse Pro Wireless Earbuds", "Sonique", "3499", "4999", {"connectivity": "Bluetooth 5.4", "battery": "40", "anc": "Yes", "water": "IPX5", "color": "Silver"}, {}),
    ]),
    ("electronics", "wearables", "Wearables", "smartwatch,smart watch,watch,fitness band,fitness tracker", "volt-electronics", None, [
        ("Orbit Smartwatch", "Kinetiq", "3999", "5999", {"connectivity": "Bluetooth 5.3", "battery": "7", "display": "AMOLED", "water": "IP67", "color": "Black"}, {}),
        ("Orbit Lite Smartwatch", "Kinetiq", "2499", None, {"connectivity": "Bluetooth 5.3", "battery": "10", "display": "LCD", "water": "IP67", "color": "Grey"}, {}),
        ("Stride Fitness Band", "Stride", "1499", "1999", {"connectivity": "Bluetooth 5.0", "battery": "14", "display": "AMOLED", "water": "IP67", "color": "Black"}, {}),
        ("Halo Kids Smartwatch", "Kinetiq", "1999", None, {"connectivity": "Bluetooth 5.0", "battery": "5", "display": "LCD", "water": "IPX4", "color": "Blue"}, {}),
        ("Orbit Pro Smartwatch", "Kinetiq", "6999", "8999", {"connectivity": "Bluetooth 5.4", "battery": "12", "display": "AMOLED", "water": "IP68", "color": "Silver"}, {}),
    ]),
    ("electronics", "laptop-accessories", "Laptop Accessories", "keyboard,mouse,laptop stand,webcam,usb hub", "volt-electronics", None, [
        ("Silent Wireless Mouse", "Voltix", "599", "899", {"connectivity": "2.4 GHz wireless", "color": "Black"}, {}),
        ("Compact Mechanical Keyboard", "Voltix", "2999", "3999", {"connectivity": "Bluetooth 5.1", "color": "Grey"}, {}),
        ("Aluminium Laptop Stand", "Voltix", "1299", None, {"connectivity": "Wired", "color": "Silver"}, {}),
        ("7-in-1 USB-C Hub", "Voltix", "1999", "2799", {"connectivity": "USB-C", "color": "Grey"}, {}),
        ("Full HD Webcam", "Auralis", "2199", None, {"connectivity": "USB-A", "color": "Black"}, {}),
    ]),
    ("electronics", "power-charging", "Power & Charging", "charger,chargers,power bank,powerbank,cable,adapter", "pixel-point-mobiles", None, [
        ("10000 mAh Slim Power Bank", "Voltix", "1199", "1799", {"connectivity": "USB-C", "output": "22.5W", "color": "Black"}, {}),
        ("20000 mAh Power Bank", "Voltix", "1999", "2499", {"connectivity": "USB-C", "output": "33W", "color": "Black"}, {}),
        ("Dual-port 30W Charger", "Voltix", "899", None, {"connectivity": "USB-C", "output": "30W", "color": "White"}, {}),
        ("Magnetic Wireless Charger", "Voltix", "1499", "1999", {"connectivity": "Wireless", "output": "15W", "color": "White"}, {}),
        ("Car Charger 2-port", "Gripz", "599", None, {"connectivity": "USB-C", "output": "38W", "color": "Black"}, {}),
    ]),
    ("mobiles-accessories", "cases-covers", "Cases & Covers", "case,cases,cover,covers,phone case,back cover", "pixel-point-mobiles", None, [
        ("Clear MagSafe Case for iPhone 16", "Armorly", "899", "1299", {"compatible": "iPhone 16", "material": "Polycarbonate", "color": "Clear"}, {}),
        ("Silicone Case for iPhone 16", "Armorly", "699", None, {"compatible": "iPhone 16", "material": "Silicone"}, {"colors": ["Black", "Navy", "Pink"]}),
        ("Rugged Armour Case for iPhone 15", "Armorly", "999", "1499", {"compatible": "iPhone 15", "material": "TPU", "color": "Black"}, {}),
        ("Leather Folio for Galaxy S24", "Armorly", "1299", None, {"compatible": "Galaxy S24", "material": "Vegan leather"}, {"colors": ["Brown", "Black"]}),
        ("Slim Matte Case for Pixel 9", "Gripz", "599", "799", {"compatible": "Pixel 9", "material": "Polycarbonate", "color": "Grey"}, {}),
        ("Shockproof Clear Case for Galaxy S24", "Gripz", "499", None, {"compatible": "Galaxy S24", "material": "TPU", "color": "Clear"}, {}),
        ("Wallet Case for iPhone 15", "Armorly", "1099", None, {"compatible": "iPhone 15", "material": "Vegan leather", "color": "Brown"}, {}),
        ("Kickstand Case for Pixel 9", "Gripz", "799", "999", {"compatible": "Pixel 9", "material": "TPU", "color": "Black"}, {}),
        ("Glitter Case for iPhone 16", "Gripz", "549", None, {"compatible": "iPhone 16", "material": "TPU", "color": "Pink"}, {}),
    ]),
    ("mobiles-accessories", "screen-protection", "Screen Protection", "screen guard,screen protector,tempered glass", "pixel-point-mobiles", None, [
        ("Tempered Glass for iPhone 16 (Pack of 2)", "ClearShield", "499", "799", {"compatible": "iPhone 16", "material": "Tempered glass"}, {}),
        ("Privacy Glass for iPhone 15", "ClearShield", "599", None, {"compatible": "iPhone 15", "material": "Tempered glass"}, {}),
        ("Matte Screen Guard for Galaxy S24", "ClearShield", "449", None, {"compatible": "Galaxy S24", "material": "Tempered glass"}, {}),
        ("Camera Lens Protector for iPhone 16", "ClearShield", "349", None, {"compatible": "iPhone 16", "material": "Tempered glass"}, {}),
    ]),
    ("mobiles-accessories", "mobile-accessories", "Mobile Accessories", "phone holder,car mount,selfie stick,tripod,phone stand,pop socket", "pixel-point-mobiles", None, [
        ("Magnetic Car Mount", "Gripz", "799", "1199", {"compatible": "Universal", "material": "Aluminium", "color": "Black"}, {}),
        ("Foldable Phone Stand", "Gripz", "399", None, {"compatible": "Universal", "material": "Aluminium", "color": "Silver"}, {}),
        ("Bluetooth Selfie Stick Tripod", "Gripz", "999", "1499", {"compatible": "Universal", "material": "Aluminium", "color": "Black"}, {}),
        ("Phone Grip Ring", "Gripz", "199", None, {"compatible": "Universal", "material": "Zinc alloy", "color": "Gold"}, {}),
        ("Waterproof Phone Pouch", "Gripz", "299", None, {"compatible": "Universal", "material": "PVC", "color": "Clear"}, {}),
        ("Braided Lightning Cable 1m", "Voltix", "449", "599", {"compatible": "iPhone 15", "material": "Nylon braid", "color": "White"}, {}),
    ]),
    ("fashion", "mens-clothing", "Men's Clothing", "shirt,shirts,t-shirt,t-shirts,tshirt,tee,jeans,chinos,trousers,men,mens", "thread-loom", "size", [
        ("Oxford Cotton Shirt", "Urban Drift", "1199", "1799", {"fabric": "Cotton", "fit": "Regular", "sleeve": "Full sleeve"}, {"colors": ["White", "Blue", "Black"]}),
        ("Classic Crew T-shirt", "Lumen Basics", "399", "599", {"fabric": "Cotton", "fit": "Regular", "sleeve": "Half sleeve"}, {"colors": ["Black", "White", "Navy", "Olive"]}),
        ("Slim Stretch Jeans", "Urban Drift", "1699", "2499", {"fabric": "Denim", "fit": "Slim", "sleeve": "Not applicable"}, {"colors": ["Blue", "Black"], "sizes": ["30", "32", "34", "36"]}),
        ("Polo T-shirt", "Lumen Basics", "699", None, {"fabric": "Cotton pique", "fit": "Regular", "sleeve": "Half sleeve"}, {"colors": ["Navy", "Maroon", "White"]}),
        ("Black Formal Shirt", "Urban Drift", "1399", "1999", {"fabric": "Cotton blend", "fit": "Slim", "sleeve": "Full sleeve"}, {"colors": ["Black"]}),
        ("Linen Kurta", "Mitti", "1499", None, {"fabric": "Linen", "fit": "Regular", "sleeve": "Full sleeve"}, {"colors": ["Beige", "White"]}),
        ("Hooded Sweatshirt", "Lumen Basics", "1299", "1899", {"fabric": "Cotton fleece", "fit": "Relaxed", "sleeve": "Full sleeve"}, {"colors": ["Grey", "Black"]}),
        ("Cargo Joggers", "Urban Drift", "999", None, {"fabric": "Cotton twill", "fit": "Relaxed", "sleeve": "Not applicable"}, {"colors": ["Olive", "Black"]}),
    ]),
    ("fashion", "womens-clothing", "Women's Clothing", "kurta,kurti,dress,dresses,top,tops,saree,women,womens", "thread-loom", "size", [
        ("Floral Midi Dress", "Mitti", "1599", "2299", {"fabric": "Rayon", "fit": "Regular", "sleeve": "Short sleeve"}, {"colors": ["Blue", "Pink"]}),
        ("Cotton Straight Kurta", "Mitti", "899", "1299", {"fabric": "Cotton", "fit": "Regular", "sleeve": "3/4 sleeve"}, {"colors": ["Yellow", "Green", "Maroon"]}),
        ("Ribbed Knit Top", "Lumen Basics", "599", None, {"fabric": "Cotton blend", "fit": "Slim", "sleeve": "Full sleeve"}, {"colors": ["Black", "Cream"]}),
        ("High-rise Wide Jeans", "Urban Drift", "1799", "2499", {"fabric": "Denim", "fit": "Wide", "sleeve": "Not applicable"}, {"colors": ["Blue"], "sizes": ["26", "28", "30", "32"]}),
        ("Linen Co-ord Set", "Mitti", "2299", None, {"fabric": "Linen", "fit": "Relaxed", "sleeve": "Half sleeve"}, {"colors": ["Beige", "Olive"]}),
        ("Oversized Shirt", "Urban Drift", "1199", None, {"fabric": "Cotton", "fit": "Oversized", "sleeve": "Full sleeve"}, {"colors": ["White", "Blue"]}),
        ("Printed Palazzo Pants", "Mitti", "799", "999", {"fabric": "Rayon", "fit": "Relaxed", "sleeve": "Not applicable"}, {"colors": ["Black", "Maroon"]}),
    ]),
    ("fashion", "ethnic-wear", "Ethnic Wear", "saree,sarees,lehenga,dupatta,ethnic", "mumbai-loom-house", None, [
        ("Handloom Cotton Saree", "Mumbai Loom House", "2499", "3299", {"fabric": "Cotton", "fit": "Free size", "sleeve": "Not applicable", }, {"colors": ["Maroon", "Teal"]}),
        ("Banarasi Silk Dupatta", "Mumbai Loom House", "1499", None, {"fabric": "Silk blend", "fit": "Free size", "sleeve": "Not applicable"}, {"colors": ["Gold", "Pink"]}),
        ("Chanderi Kurta Set", "Mumbai Loom House", "2999", "3999", {"fabric": "Chanderi", "fit": "Regular", "sleeve": "3/4 sleeve"}, {"colors": ["Cream", "Green"], "sizes": SIZES}),
    ]),
    ("fashion", "kids-clothing", "Kids' Clothing", "kids wear,kids clothes,boys,girls", "little-tribe-kids", "kids", [
        ("Dino Print T-shirt", "Little Tribe", "349", None, {"fabric": "Cotton", "fit": "Regular", "sleeve": "Half sleeve"}, {"colors": ["Green", "Blue"]}),
        ("Twirl Party Dress", "Little Tribe", "899", "1199", {"fabric": "Cotton blend", "fit": "Regular", "sleeve": "Sleeveless"}, {"colors": ["Pink", "Yellow"]}),
        ("Everyday Shorts (Pack of 2)", "Little Tribe", "599", None, {"fabric": "Cotton", "fit": "Regular", "sleeve": "Not applicable"}, {"colors": ["Navy"]}),
        ("Hooded Rain Jacket", "Little Tribe", "1099", "1499", {"fabric": "Polyester", "fit": "Regular", "sleeve": "Full sleeve"}, {"colors": ["Yellow", "Red"]}),
    ]),
    ("footwear", "sports-shoes", "Sports Shoes", "running shoes,sports shoes,sneakers,trainers,shoes,shoe", "stride-sports-co", "shoe", [
        ("Tempo Running Shoes", "Paceline", "2999", "4499", {"material": "Mesh", "closure": "Lace-up"}, {"colors": ["Black", "Blue"]}),
        ("Cloudstep Walking Shoes", "Paceline", "2299", None, {"material": "Knit", "closure": "Slip-on"}, {"colors": ["Grey", "Black"]}),
        ("Court Training Shoes", "Stride", "2499", "3299", {"material": "Synthetic", "closure": "Lace-up"}, {"colors": ["White"]}),
        ("Trail Grip Shoes", "Paceline", "3999", "5499", {"material": "Mesh", "closure": "Lace-up"}, {"colors": ["Olive", "Black"]}),
        ("Black Running Shoes", "Stride", "1999", "2799", {"material": "Mesh", "closure": "Lace-up"}, {"colors": ["Black"]}),
    ]),
    ("footwear", "casual-shoes", "Casual Shoes", "casual shoes,loafers,sandals,slippers,flip flops,sneaker", "kraft-carry", "shoe", [
        ("Canvas Low-top Sneakers", "Cobbler Co.", "1499", "1999", {"material": "Canvas", "closure": "Lace-up"}, {"colors": ["White", "Navy"]}),
        ("Suede Loafers", "Cobbler Co.", "2499", None, {"material": "Suede", "closure": "Slip-on"}, {"colors": ["Brown", "Navy"]}),
        ("Comfort Sandals", "Cobbler Co.", "999", "1299", {"material": "Synthetic", "closure": "Velcro"}, {"colors": ["Black", "Brown"]}),
        ("Kolhapuri Flats", "Cobbler Co.", "799", None, {"material": "Leather", "closure": "Slip-on"}, {"colors": ["Brown"]}),
        ("Everyday Flip Flops", "Cobbler Co.", "349", None, {"material": "Rubber", "closure": "Slip-on"}, {"colors": ["Black", "Blue"]}),
        ("Leather Chelsea Boots", "Cobbler Co.", "3999", "5499", {"material": "Leather", "closure": "Slip-on"}, {"colors": ["Brown", "Black"]}),
    ]),
    ("home-kitchen", "kitchen", "Kitchen", "kitchen,cookware,pan,pans,kadai,utensils,bottle,lunch box,kitchenware", "hearth-home-store", None, [
        ("Non-stick Kadai 24 cm", "Nestwell", "1299", "1899", {"material": "Aluminium", "dimensions": "24 cm"}, {}),
        ("Stainless Steel Pressure Cooker 3 L", "Nestwell", "1799", "2299", {"material": "Stainless steel", "dimensions": "3 L"}, {}),
        ("Wooden Spatula Set (Set of 4)", "Hearth", "449", None, {"material": "Neem wood"}, {}),
        ("Insulated Lunch Box", "Clearhome", "799", "999", {"material": "Stainless steel", "color": "Blue"}, {}),
        ("Ceramic Dinner Set (16 pc)", "Hearth", "2999", "3999", {"material": "Ceramic", "color": "White"}, {}),
        ("Copper Water Bottle 1 L", "Hearth", "999", None, {"material": "Copper"}, {}),
        ("Knife Set with Block", "Ironclad", "1899", "2599", {"material": "Stainless steel", "color": "Black"}, {}),
        ("Spice Rack Organiser", "Clearhome", "699", None, {"material": "Bamboo"}, {}),
    ]),
    ("home-kitchen", "home-decor", "Home Decor", "decor,cushion,lamp,vase,wall art,candle,home decor", "hearth-home-store", None, [
        ("Ceramic Table Lamp", "Hearth", "1999", "2699", {"material": "Ceramic", "color": "Cream", "dimensions": "38 cm tall"}, {}),
        ("Terracotta Planter Set", "Hearth", "799", None, {"material": "Terracotta", "color": "Brown"}, {}),
        ("Scented Soy Candle", "Hearth", "499", None, {"material": "Soy wax", "color": "Cream"}, {}),
        ("Macrame Wall Hanging", "Hearth", "899", "1199", {"material": "Cotton", "color": "Beige"}, {}),
        ("Brass Decorative Bowl", "Hearth", "1299", None, {"material": "Brass", "color": "Gold"}, {}),
    ]),
    ("home-kitchen", "bed-bath", "Bed & Bath", "bedsheet,bedsheets,towel,towels,pillow,blanket,bath", "hearth-home-store", None, [
        ("Cotton Double Bedsheet Set", "Nestwell", "1499", "2199", {"material": "Cotton", "dimensions": "Double"}, {"colors": ["White", "Blue", "Grey"]}),
        ("Bath Towel (Pack of 2)", "Nestwell", "899", None, {"material": "Cotton", "color": "Grey"}, {}),
        ("Memory Foam Pillow", "Nestwell", "1299", "1799", {"material": "Memory foam", "color": "White"}, {}),
        ("Reversible Quilt", "Nestwell", "2499", None, {"material": "Microfibre", "color": "Teal"}, {}),
        ("Bath Mat", "Clearhome", "399", None, {"material": "Cotton", "color": "Beige"}, {}),
    ]),
    ("beauty", "skincare", "Skincare", "face wash,facewash,moisturiser,moisturizer,sunscreen,serum,skincare,cream", "glow-theory-beauty", None, [
        ("Vitamin C Brightening Serum", "Dew Botanics", "649", "899", {"skin_type": "All skin types", "volume": "30", "ingredient": "Vitamin C"}, {}),
        ("Gentle Foaming Face Wash", "Dew Botanics", "299", None, {"skin_type": "Oily skin", "volume": "150", "ingredient": "Tea tree"}, {}),
        ("SPF 50 Sunscreen Gel", "Aurum Skin", "499", "599", {"skin_type": "All skin types", "volume": "50", "ingredient": "Zinc oxide"}, {}),
        ("Ceramide Moisturiser", "Aurum Skin", "599", None, {"skin_type": "Dry skin", "volume": "50", "ingredient": "Ceramides"}, {}),
        ("Niacinamide 10% Serum", "Dew Botanics", "549", "699", {"skin_type": "Oily skin", "volume": "30", "ingredient": "Niacinamide"}, {}),
        ("Hydrating Sheet Masks (Pack of 5)", "Aurum Skin", "399", None, {"skin_type": "All skin types", "volume": "100", "ingredient": "Hyaluronic acid"}, {}),
        ("Lip Balm Trio", "Dew Botanics", "249", None, {"skin_type": "All skin types", "volume": "15", "ingredient": "Shea butter"}, {}),
        ("Kumkumadi Night Oil", "Saffra", "899", "1199", {"skin_type": "Dry skin", "volume": "30", "ingredient": "Saffron"}, {}),
    ]),
    ("beauty", "haircare", "Haircare", "shampoo,conditioner,hair oil,hair mask,haircare,hair", "glow-theory-beauty", None, [
        ("Onion Hair Oil", "Saffra", "399", "499", {"skin_type": "All hair types", "volume": "200", "ingredient": "Onion extract"}, {}),
        ("Sulphate-free Shampoo", "Dew Botanics", "449", None, {"skin_type": "Dry hair", "volume": "250", "ingredient": "Argan oil"}, {}),
        ("Keratin Hair Mask", "Aurum Skin", "599", "799", {"skin_type": "Damaged hair", "volume": "200", "ingredient": "Keratin"}, {}),
        ("Wide-tooth Wooden Comb", "Saffra", "199", None, {"skin_type": "All hair types", "volume": "0", "ingredient": "Neem wood"}, {"returns": None}),
        ("Leave-in Conditioner", "Dew Botanics", "399", None, {"skin_type": "Curly hair", "volume": "150", "ingredient": "Coconut oil"}, {}),
    ]),
    ("beauty", "fragrances", "Fragrances", "perfume,perfumes,deodorant,deo,fragrance,attar", "glow-theory-beauty", None, [
        ("Oud Noir Eau de Parfum", "Saffra", "1499", "1999", {"skin_type": "Unisex", "volume": "50", "ingredient": "Oud"}, {}),
        ("Citrus Splash Body Mist", "Dew Botanics", "399", None, {"skin_type": "Women", "volume": "150", "ingredient": "Citrus"}, {}),
        ("Sandalwood Attar", "Saffra", "699", None, {"skin_type": "Unisex", "volume": "10", "ingredient": "Sandalwood"}, {}),
        ("Fresh Aqua Deodorant", "Aurum Skin", "249", None, {"skin_type": "Men", "volume": "150", "ingredient": "Marine"}, {}),
        ("Rose Eau de Toilette", "Dew Botanics", "1199", "1499", {"skin_type": "Women", "volume": "100", "ingredient": "Rose"}, {}),
    ]),
    ("appliances", "kitchen-appliances", "Kitchen Appliances", "mixer,grinder,mixer grinder,kettle,toaster,air fryer,blender", "appliance-hub", None, [
        ("750W Mixer Grinder", "Kitchenova", "3299", "4499", {"power": "750", "capacity": "3 jars", "color": "White"}, {}),
        ("Electric Kettle 1.5 L", "Kitchenova", "999", "1399", {"power": "1500", "capacity": "1.5 L", "color": "Silver"}, {}),
        ("Digital Air Fryer 4 L", "Brewmatic", "4999", "6999", {"power": "1400", "capacity": "4 L", "color": "Black"}, {}),
        ("Pop-up Toaster", "Kitchenova", "1499", None, {"power": "800", "capacity": "2 slices", "color": "White"}, {}),
        ("Drip Coffee Maker", "Brewmatic", "2999", "3999", {"power": "800", "capacity": "6 cups", "color": "Black"}, {}),
        ("Hand Blender", "Kitchenova", "1299", None, {"power": "400", "capacity": "600 ml", "color": "White"}, {}),
    ]),
    ("appliances", "home-appliances", "Home Appliances", "iron,vacuum,vacuum cleaner,fan,heater,steamer", "appliance-hub", None, [
        ("Steam Iron 1600W", "Kitchenova", "1499", "1999", {"power": "1600", "capacity": "300 ml", "color": "Blue"}, {}),
        ("Cordless Vacuum Cleaner", "Brewmatic", "7999", "9999", {"power": "150", "capacity": "0.6 L", "color": "Grey"}, {}),
        ("Table Fan 400 mm", "Kitchenova", "1799", None, {"power": "55", "capacity": "400 mm", "color": "White"}, {}),
        ("Garment Steamer", "Brewmatic", "2499", "3299", {"power": "1200", "capacity": "250 ml", "color": "White"}, {}),
    ]),
    ("books", "fiction", "Fiction", "novel,novels,fiction,story", "paperback-lane", None, [
        ("The Monsoon Archive", "Inkwell Books", "399", "499", {"format": "Paperback", "language": "English", "author": "R. Menon (fictional)", "pages": "312"}, {}),
        ("Letters from Nandi Hills", "Inkwell Books", "349", None, {"format": "Paperback", "language": "English", "author": "S. Iyer (fictional)", "pages": "248"}, {}),
        ("The Clockmaker's Daughter", "Lanternhouse Press", "499", None, {"format": "Hardcover", "language": "English", "author": "A. Das (fictional)", "pages": "384"}, {}),
        ("Silent Harbour", "Inkwell Books", "299", "399", {"format": "Paperback", "language": "English", "author": "M. Khan (fictional)", "pages": "220"}, {}),
        ("Kannada Short Stories Vol. 1", "Lanternhouse Press", "249", None, {"format": "Paperback", "language": "Kannada", "author": "Various (fictional)", "pages": "180"}, {}),
    ]),
    ("books", "non-fiction", "Non-fiction", "self help,business,biography,history,non fiction", "paperback-lane", None, [
        ("Deep Focus Habits", "Lanternhouse Press", "449", "599", {"format": "Paperback", "language": "English", "author": "K. Rao (fictional)", "pages": "256"}, {}),
        ("Money Basics for Beginners", "Inkwell Books", "349", None, {"format": "Paperback", "language": "English", "author": "P. Shah (fictional)", "pages": "200"}, {}),
        ("Cooking from the Coast", "Lanternhouse Press", "799", "999", {"format": "Hardcover", "language": "English", "author": "L. Fernandes (fictional)", "pages": "240"}, {}),
    ]),
    ("books", "childrens-books", "Children's Books", "kids books,children's books,picture book,story book", "paperback-lane", None, [
        ("The Little Elephant Who Could", "Inkwell Books", "249", None, {"format": "Paperback", "language": "English", "author": "N. Pillai (fictional)", "pages": "32"}, {}),
        ("Space Facts for Curious Kids", "Lanternhouse Press", "399", "499", {"format": "Hardcover", "language": "English", "author": "V. Bose (fictional)", "pages": "64"}, {}),
        ("Bedtime Stories Treasury", "Inkwell Books", "599", None, {"format": "Hardcover", "language": "English", "author": "Various (fictional)", "pages": "160"}, {}),
    ]),
    ("sports-fitness", "fitness-equipment", "Fitness Equipment", "dumbbell,dumbbells,yoga mat,resistance band,kettlebell,gym", "stride-sports-co", None, [
        ("Cast Iron Kettlebell 8 kg", "Asana Pro", "1499", None, {"material": "Cast iron", "weight": "8 kg", "color": "Black"}, {}),
        ("Foam Roller", "Asana Pro", "699", "899", {"material": "EVA foam", "weight": "0.5 kg", "color": "Blue"}, {}),
        ("Skipping Rope with Counter", "Stride", "399", None, {"material": "PVC", "weight": "0.2 kg", "color": "Black"}, {}),
    ]),
    ("sports-fitness", "outdoor-cycling", "Outdoor & Cycling", "cycling,bicycle,helmet,camping,trekking,outdoor", "stride-sports-co", None, [
        ("Cycling Helmet", "Stride", "1499", "1999", {"material": "Polycarbonate", "weight": "0.3 kg", "color": "Black"}, {}),
        ("Trekking Backpack 40 L", "Roamr", "2499", "3499", {"material": "Nylon", "weight": "1.1 kg", "color": "Olive"}, {}),
        ("Camping Headlamp", "Roamr", "699", None, {"material": "ABS", "weight": "0.1 kg", "color": "Black"}, {}),
        ("Badminton Racquet Pair", "Stride", "1199", "1599", {"material": "Aluminium", "weight": "0.1 kg", "color": "Red"}, {}),
    ]),
    ("toys-games", "building-stem", "Building & STEM", "lego,blocks,building blocks,stem,science kit,robot", "little-tribe-kids", None, [
        ("City Builder Blocks (500 pc)", "Brickbox", "1499", "1999", {"age": "6-8 years", "material": "ABS plastic"}, {}),
        ("Junior Robotics Kit", "Brickbox", "2999", "3499", {"age": "9-12 years", "material": "ABS plastic"}, {}),
        ("Magnetic Tiles (60 pc)", "Funwise", "1999", None, {"age": "3-5 years", "material": "ABS plastic"}, {}),
        ("Crystal Growing Science Kit", "Funwise", "799", None, {"age": "9-12 years", "material": "Mixed"}, {}),
    ]),
    ("toys-games", "board-games", "Board Games & Puzzles", "board game,board games,puzzle,puzzles,jigsaw,cards,chess", "little-tribe-kids", None, [
        ("Family Strategy Board Game", "Funwise", "999", "1299", {"age": "9-12 years", "material": "Cardboard"}, {}),
        ("1000-piece Jigsaw: Hampi", "Funwise", "699", None, {"age": "12+ years", "material": "Cardboard"}, {}),
        ("Wooden Chess Set", "Funwise", "1199", None, {"age": "6-8 years", "material": "Wood"}, {}),
        ("Word Builder Card Game", "Funwise", "399", None, {"age": "6-8 years", "material": "Cardboard"}, {}),
    ]),
    ("toys-games", "soft-toys", "Soft Toys", "soft toy,teddy,plush,stuffed toy", "little-tribe-kids", None, [
        ("Elephant Plush 30 cm", "Little Tribe", "599", None, {"age": "3-5 years", "material": "Polyester"}, {}),
        ("Sleepy Panda Plush", "Little Tribe", "799", "999", {"age": "3-5 years", "material": "Polyester"}, {}),
        ("Hand Puppet Set", "Funwise", "499", None, {"age": "3-5 years", "material": "Cotton"}, {}),
    ]),
    ("baby-kids", "baby-care", "Baby Care", "baby care,diaper bag,baby blanket,feeding bottle,baby", "little-tribe-kids", None, [
        ("Muslin Swaddle Set (3 pc)", "Little Tribe", "899", "1199", {"age": "0-12 months", "material": "Cotton muslin"}, {"returns": None}),
        ("Diaper Changing Bag", "Little Tribe", "1499", None, {"age": "0-24 months", "material": "Polyester"}, {}),
        ("Silicone Feeding Set", "Little Tribe", "699", None, {"age": "6-24 months", "material": "Food-grade silicone"}, {"returns": None}),
    ]),
    ("baby-kids", "school-essentials", "School Essentials", "school bag,lunch bag,water bottle,pencil box,school", "little-tribe-kids", None, [
        ("Kids School Backpack", "Little Tribe", "999", "1299", {"age": "6-8 years", "material": "Polyester"}, {}),
        ("Stainless Kids Bottle", "Little Tribe", "499", None, {"age": "3-5 years", "material": "Stainless steel"}, {}),
        ("Geometry & Pencil Box Kit", "Inkpot", "349", None, {"age": "9-12 years", "material": "Plastic"}, {}),
    ]),
    ("bags-luggage", "backpacks", "Backpacks", "backpack,backpacks,laptop bag,college bag,rucksack", "kraft-carry", None, [
        ("Everyday Laptop Backpack", "Roamr", "1799", "2499", {"capacity": "25 L", "material": "Polyester"}, {"colors": ["Black", "Navy", "Grey"]}),
        ("Anti-theft Backpack", "Roamr", "2499", None, {"capacity": "20 L", "material": "Polyester", "color": "Grey"}, {}),
        ("Canvas Rolltop Backpack", "Kraft & Carry", "1999", "2699", {"capacity": "22 L", "material": "Canvas", "color": "Olive"}, {}),
        ("Mini Daypack", "Kraft & Carry", "999", None, {"capacity": "12 L", "material": "Nylon", "color": "Pink"}, {}),
    ]),
    ("bags-luggage", "travel", "Travel", "suitcase,trolley,luggage,duffel,travel bag,cabin bag", "kraft-carry", None, [
        ("Hardshell Cabin Trolley 55 cm", "Roamr", "3999", "5999", {"capacity": "40 L", "material": "Polycarbonate"}, {"colors": ["Black", "Teal"]}),
        ("Weekend Duffel Bag", "Kraft & Carry", "1999", None, {"capacity": "35 L", "material": "Canvas", "color": "Brown"}, {}),
        ("Travel Toiletry Kit", "Roamr", "599", None, {"capacity": "3 L", "material": "Nylon", "color": "Black"}, {}),
    ]),
    ("jewellery", "earrings", "Earrings", "earrings,jhumka,jhumkas,studs,hoops", "mumbai-loom-house", None, [
        ("Oxidised Silver Jhumkas", "Rangoli Silver", "899", "1199", {"material": "Sterling silver 925", "color": "Silver"}, {"returns": None}),
        ("Gold-plated Hoop Earrings", "Rangoli Silver", "699", None, {"material": "Gold-plated brass", "color": "Gold"}, {"returns": None}),
        ("Pearl Drop Earrings", "Rangoli Silver", "1199", None, {"material": "Sterling silver 925", "color": "Silver"}, {"returns": None}),
    ]),
    ("jewellery", "necklaces", "Necklaces & Pendants", "necklace,necklaces,pendant,chain,mangalsutra", "mumbai-loom-house", None, [
        ("Temple Pendant Necklace", "Rangoli Silver", "1899", "2499", {"material": "Gold-plated brass", "color": "Gold"}, {}),
        ("Minimal Heart Pendant", "Rangoli Silver", "999", None, {"material": "Sterling silver 925", "color": "Silver"}, {}),
        ("Kundan Choker Set", "Rangoli Silver", "2999", "3999", {"material": "Gold-plated brass", "color": "Gold"}, {}),
    ]),
    ("pet-supplies", "pet-accessories", "Pet Accessories", "dog,cat,pet bed,leash,collar,pet bowl,pet toy", "little-tribe-kids", None, [
        ("Orthopaedic Dog Bed (Medium)", "Pawsome", "1999", "2499", {"pet": "Dogs", "material": "Memory foam"}, {}),
        ("Reflective Dog Leash", "Pawsome", "499", None, {"pet": "Dogs", "material": "Nylon"}, {}),
        ("Cat Scratching Post", "Pawsome", "1299", None, {"pet": "Cats", "material": "Sisal"}, {}),
        ("Steel Pet Bowl Set", "Pawsome", "399", None, {"pet": "Dogs & cats", "material": "Stainless steel"}, {}),
    ]),
    ("office-stationery", "notebooks-desk", "Notebooks & Desk", "notebook,notebooks,diary,planner,pen,pens,desk organiser,stationery", "paperback-lane", None, [
        ("2027 Daily Planner", "Inkpot", "499", "699", {"material": "Paper", "pages": "400"}, {}),
        ("Gel Pen Set (10 colours)", "Inkpot", "249", None, {"material": "Plastic", "pages": "0"}, {}),
        ("Bamboo Desk Organiser", "Inkpot", "799", None, {"material": "Bamboo", "pages": "0"}, {}),
        ("Hardbound Sketchbook A4", "Inkpot", "449", None, {"material": "Paper", "pages": "120"}, {}),
    ]),
    ("furniture", "study-office", "Study & Office", "chair,office chair,desk,study table,table,bookshelf,shelf", "woodnest-living", None, [
        ("Ergonomic Mesh Office Chair", "Woodnest", "6999", "9999", {"material": "Mesh & nylon", "color": "Black", "dimensions": "64 x 60 x 110 cm"}, {}),
        ("Engineered Wood Study Desk", "Woodnest", "5499", "6999", {"material": "Engineered wood", "color": "Brown", "dimensions": "100 x 50 x 75 cm"}, {}),
        ("5-tier Bookshelf", "Woodnest", "3999", None, {"material": "Engineered wood", "color": "White", "dimensions": "60 x 30 x 170 cm"}, {}),
        ("Folding Laptop Table", "Woodnest", "1299", "1799", {"material": "Engineered wood", "color": "Brown", "dimensions": "60 x 40 x 28 cm"}, {}),
        ("Solid Wood Bedside Table", "Woodnest", "4499", None, {"material": "Sheesham wood", "color": "Brown", "dimensions": "45 x 40 x 55 cm"}, {}),
    ]),
]

# Existing retail listings (from devseed.catalog) placed into the taxonomy: (store, name) -> (subcategory, brand, attrs, extra)
EXISTING = {
    ("volt-electronics", "Wireless Earbuds Pro"): ("audio", "Sonique", {"connectivity": "Bluetooth 5.3", "battery": "30", "anc": "Yes", "water": "IPX4", "color": "Black"}, {}),
    ("volt-electronics", "Bluetooth Speaker Mini"): ("audio", "Boomlet", {"connectivity": "Bluetooth 5.0", "battery": "10", "anc": "No", "water": "IPX5", "color": "Blue"}, {}),
    ("volt-electronics", "65W USB-C Charger"): ("power-charging", "Voltix", {"connectivity": "USB-C", "output": "65W", "color": "White"}, {}),
    ("volt-electronics", "Braided USB-C Cable 1.5m"): ("power-charging", "Voltix", {"connectivity": "USB-C", "output": "60W", "color": "Black"}, {}),
    ("thread-loom", "Linen Shirt — Sage"): ("mens-clothing", "Thread & Loom", {"fabric": "Linen", "fit": "Regular", "sleeve": "Full sleeve"}, {"colors": ["Green"], "sizes": ["M", "L", "XL"]}),
    ("thread-loom", "Everyday Chinos"): ("mens-clothing", "Thread & Loom", {"fabric": "Cotton twill", "fit": "Slim", "sleeve": "Not applicable"}, {"colors": ["Beige"], "sizes": ["30", "32", "34", "36"]}),
    ("thread-loom", "Block-print Kurta"): ("womens-clothing", "Thread & Loom", {"fabric": "Cotton", "fit": "Regular", "sleeve": "3/4 sleeve"}, {"colors": ["Blue"], "sizes": SIZES}),
    ("thread-loom", "Cotton Dupatta"): ("ethnic-wear", "Thread & Loom", {"fabric": "Cotton", "fit": "Free size", "sleeve": "Not applicable"}, {}),
    ("hearth-home-store", "Cast Iron Skillet 10\""): ("kitchen", "Ironclad", {"material": "Cast iron", "dimensions": "10 in", "color": "Black"}, {}),
    ("hearth-home-store", "Glass Storage Jars (Set of 3)"): ("kitchen", "Clearhome", {"material": "Glass", "color": "Clear"}, {}),
    ("hearth-home-store", "Handwoven Cushion Cover"): ("home-decor", "Hearth", {"material": "Cotton", "color": "Beige", "dimensions": "16 x 16 in"}, {}),
    ("paperback-lane", "The Startup Playbook"): ("non-fiction", "Lanternhouse Press", {"format": "Paperback", "language": "English", "author": "J. Varma (fictional)", "pages": "288"}, {}),
    ("paperback-lane", "Bengaluru: A City History"): ("non-fiction", "Lanternhouse Press", {"format": "Hardcover", "language": "English", "author": "T. Nair (fictional)", "pages": "420"}, {}),
    ("paperback-lane", "Dot-grid Notebook A5"): ("notebooks-desk", "Paperback Lane", {"material": "Paper", "pages": "160"}, {}),
    ("stride-sports-co", "Featherlight Running Shoes"): ("sports-shoes", "Stride", {"material": "Mesh", "closure": "Lace-up"}, {"colors": ["Grey"], "sizes": SHOE}),
    ("stride-sports-co", "Dri-fit Running Tee"): ("mens-clothing", "Stride", {"fabric": "Polyester", "fit": "Regular", "sleeve": "Half sleeve"}, {"colors": ["Black", "Blue"], "sizes": SIZES}),
    ("stride-sports-co", "Yoga Mat 6mm"): ("fitness-equipment", "Asana Pro", {"material": "TPE", "weight": "0.9 kg", "color": "Purple"}, {}),
    ("stride-sports-co", "Adjustable Dumbbells (Pair)"): ("fitness-equipment", "Ironclad", {"material": "Cast iron", "weight": "2-10 kg", "color": "Black"}, {}),
    ("stride-sports-co", "Steel Water Bottle 1L"): ("outdoor-cycling", "Stride", {"material": "Stainless steel", "weight": "0.3 kg", "color": "Silver"}, {}),
    ("stride-sports-co", "Resistance Bands Set"): ("fitness-equipment", "Asana Pro", {"material": "Latex", "weight": "0.4 kg", "color": "Red"}, {}),
}

VARIANT_SIZES = {"size": SIZES, "shoe": SHOE, "kids": ["2-3Y", "4-5Y", "6-7Y", "8-9Y"]}

CAMPAIGNS = [
    # kind, eyebrow, title, subtitle, image, cta label, path, category slug, priority, (start days, end days)
    ("essentials", "Discover something new", "Everyday picks made for you.", "Home, fashion and gadgets from trusted Click. sellers.",
     "/media/onboarding/shopping-1280.webp", "Shop now", "/shopping/search?sort=popular", None, 30, (-2, 21)),
    ("electronics", "Sound week", "Sound that moves with you.", "Earbuds, headphones and speakers, with deals that end this week.",
     "", "Explore audio", "/shopping/c/audio", "electronics", 20, (-1, 6)),
    ("home", "Home upgrades", "Make home feel new.", "Decor, kitchen and bedding picks from local sellers.",
     "/media/onboarding/market-1280.webp", "Shop home", "/shopping/c/home-kitchen", "home-kitchen", 10, (-3, 14)),
    ("festival", "Ended", "Monsoon sale (ended)", "This campaign has ended and must never show.", "", "Shop", "/shopping", None, 99, (-20, -2)),
    ("school", "Starting soon", "Back to school (not started)", "Starts next month; must not show yet.", "", "Shop", "/shopping/c/baby-kids", None, 99, (20, 40)),
]

DEALS = [  # (subcategory slug, product index, kind, percent, hours left, quantity limit)
    ("audio", 0, "limited", 15, 30, None), ("audio", 6, "flash", 25, 8, 25), ("wearables", 0, "limited", 20, 54, None),
    ("mens-clothing", 1, "price_drop", 10, 70, None), ("womens-clothing", 1, "limited", 20, 40, None), ("sports-shoes", 0, "flash", 30, 10, 15),
    ("kitchen", 0, "limited", 15, 60, None), ("home-decor", 0, "price_drop", 10, 72, None), ("skincare", 0, "limited", 20, 36, None),
    ("kitchen-appliances", 2, "flash", 20, 12, 10), ("backpacks", 0, "limited", 15, 48, None), ("building-stem", 0, "limited", 10, 66, None),
    ("cases-covers", 0, "price_drop", 20, 50, None), ("study-office", 0, "limited", 12, 58, None),
]

SELLER_OFFERS = [  # store, title, description, type, value, cap, minimum order
    ("volt-electronics", "₹150 off over ₹1,999", "On your Volt Electronics order", "flat", "150", None, "1999"),
    ("thread-loom", "10% off over ₹1,299", "Up to ₹200 off at Thread & Loom", "percent", "10", "200", "1299"),
    ("glow-theory-beauty", "Free delivery", "On any Glow Theory order", "free_delivery", "0", None, "0"),
]

REVIEWERS = [("Ananya", "Koramangala"), ("Rohit", "Indiranagar"), ("Meera", "Jayanagar"), ("Karthik", "HSR Layout"),
             ("Fatima", "Whitefield"), ("Vikram", "Malleshwaram")]
REVIEW_TEXT = {
    5: [("Exactly as described", "Great quality for the price. Delivery was on time and the packing was neat."),
        ("Love it", "Using it every day. Would happily buy again from this seller.")],
    4: [("Good value", "Does the job well. One small thing could be better, but happy overall."),
        ("Nice, with a small catch", "Quality is good. Took a day longer than the estimate.")],
    3: [("Okay", "It's fine for the price, nothing special.")],
    2: [("Not for me", "The finish wasn't as good as the photos suggested.")],
}
NS = uuid.UUID("0b5e6c1a-7f2d-4c8e-9a10-5401c0de5eed")


def _attrs(category, specs):
    for pos, (code, name, kind, unit, filterable, comparable) in enumerate(specs):
        AttributeDefinition.objects.update_or_create(category=category, code=code, defaults=dict(
            name=name, kind=kind, unit=unit, is_filterable=filterable, is_comparable=comparable, position=pos))


def _taxonomy():
    tops, subs = {}, {}
    for pos, (slug, (name, icon, syn, _r, _w, specs)) in enumerate(TOP.items()):
        tops[slug], _ = ShopCategory.objects.update_or_create(slug=slug, defaults=dict(name=name, icon=icon, synonyms=syn, position=pos, is_active=True,
                                                                                       parent=None))
        _attrs(tops[slug], specs)
    for pos, (top, slug, name, syn, *_rest) in enumerate(SUBS):
        subs[slug], _ = ShopCategory.objects.update_or_create(slug=slug, defaults=dict(name=name, parent=tops[top], synonyms=syn, position=pos, is_active=True))
        _attrs(subs[slug], SUB_ATTRS.get(slug, []))
    return tops, subs


def _sellers():
    out = {}
    for slug, name, locality, cats, fee, free, dispatch, cod, verified, policy in SELLERS:
        if locality == "Mumbai":
            lat, lng, city = *MUMBAI, "Mumbai"
        else:
            (lat, lng), city = locality_point(locality, name), "Bengaluru"
        store, _ = Store.objects.update_or_create(slug=slug, defaults=dict(
            name=name, store_type=StoreType.RETAIL, status=Store.Status.ACTIVE, is_accepting_orders=True,
            description=f"{', '.join(cats)}. {MARKER}.", city=city, locality=locality, latitude=lat, longitude=lng,
            delivery_fee=D(fee), free_delivery_above=D(free), dispatch_days=dispatch, cod_enabled=cod, return_policy=policy,
            verified_at=timezone.now() - timedelta(days=90) if verified else None,
            delivery_time_min=60 * 24, delivery_time_max=60 * 24 * 5, min_order_amount=D("0")))
        for c in cats:
            cat, _ = StoreCategory.objects.get_or_create(store_type=StoreType.RETAIL, slug=slugify(c), defaults={"name": c})
            store.categories.add(cat)
        out[slug] = store
    return out


def _brand(name, cache):
    if name not in cache:
        cache[name], _ = Brand.objects.update_or_create(slug=slugify(name), defaults={"name": name, "is_active": True})
    return cache[name]


def _apply(product, sub, top_slug, brand, attrs, extra, variant_kind):
    top = TOP[top_slug]
    defs = {d.code: d for d in AttributeDefinition.objects.filter(category_id__in=sub.lineage_ids())}
    for code, value in attrs.items():
        if code in defs and value not in ("", None):
            d = defs[code]
            ProductAttributeValue.objects.update_or_create(product=product, definition=d, defaults={
                "value": value, "number": D(value) if d.kind == A.NUMBER else None})
    product.shop_category, product.brand_ref, product.brand = sub, brand, brand.name
    product.return_days = extra.get("returns", top[3]) if "returns" in extra else top[3]
    product.replacement_only = top_slug in ("books", "electronics", "appliances") and "replacement" not in extra
    product.warranty = top[4]
    product.highlights = _highlights(attrs, defs)
    colors, sizes = extra.get("colors"), extra.get("sizes") or VARIANT_SIZES.get(variant_kind)
    sized = bool(variant_kind or extra.get("sizes"))
    if colors and (len(colors) > 1 or sized):
        _variants(product, [("Color", colors)] + ([("Size", sizes)] if sized else []))
    elif colors and "color" in defs:
        ProductAttributeValue.objects.update_or_create(product=product, definition=defs["color"], defaults={"value": colors[0]})
    product.save()


def _highlights(attrs, defs) -> list[str]:
    out = []
    for code, value in attrs.items():
        d = defs.get(code)
        if d is None or value in ("", "0", "None", "Not applicable"):
            continue
        if d.kind == A.BOOLEAN:
            if value == "Yes":
                out.append(d.name)
        else:
            out.append(f"{d.name}: {value} {d.unit}".strip())
    return out[:5]


def _variants(product, axes):
    combos = [{}]
    for axis, values in axes:
        combos = [{**c, axis: v} for c in combos for v in values]
    base, mrp = product.price, product.compare_at_price
    keep = []
    for pos, opts in enumerate(combos):
        key = ProductVariant.key_for(opts)
        n = h(product.name + key)
        bump = D("100") if opts.get("Size") in ("XL", "36", "UK 10", "8-9Y") else D("0")
        stock = 0 if n % 9 == 0 else 3 + n % 25
        v = ProductVariant.objects.filter(product=product, options_key=key).first() or ProductVariant(product=product)
        v.options, v.price, v.compare_at_price = opts, base + bump, (mrp + bump) if mrp else None
        v.sku, v.position, v.is_active = f"{slugify(product.name)[:30]}-{pos}".upper(), pos, True
        if v.pk is None:
            v.stock_quantity = stock
        v.save()
        keep.append(v.pk)
    ProductVariant.objects.filter(product=product).exclude(pk__in=keep).update(is_active=False)
    product.stock_quantity = None


def seed_shop(log) -> None:
    tops, subs = _taxonomy()
    sellers = _sellers()
    brands: dict = {}
    count = 0
    for top_slug, sub_slug, _name, _syn, seller_slug, variant_kind, products in SUBS:
        store = sellers[seller_slug]
        section, _ = MenuCategory.objects.get_or_create(store=store, name=_name)
        for i, (name, brand_name, price, mrp, attrs, extra) in enumerate(products):
            n = h(name)
            product, created = Product.objects.update_or_create(store=store, name=name, defaults=dict(
                category=section, price=D(price), compare_at_price=D(mrp) if mrp else None,
                description=f"{name} by {brand_name}. Sold and shipped by {store.name}.",
                stock_quantity=extra.get("stock", 0 if n % 17 == 0 else 4 + n % 40), is_active=True, is_available=True, position=i,
                is_cod_available=seller_slug != "mumbai-loom-house"))
            _apply(product, subs[sub_slug], top_slug, _brand(brand_name, brands), attrs, extra, variant_kind)
            if created:  # spread listing dates over ~4 months (a third are "new")
                Product.objects.filter(pk=product.pk).update(created_at=timezone.now() - timedelta(days=n % 120, hours=n % 23))
            count += 1
    for (store_slug, name), (sub_slug, brand_name, attrs, extra) in EXISTING.items():
        product = Product.objects.filter(store__slug=store_slug, name=name).first()
        if product:
            top_slug = next(t for t, s, *_ in SUBS if s == sub_slug)
            _apply(product, subs[sub_slug], top_slug, _brand(brand_name, brands), attrs, extra, None)
            count += 1

    now = timezone.now()
    for kind, eyebrow, title, subtitle, image, cta, path, cat, priority, (start, end) in CAMPAIGNS:
        ShopCampaign.objects.update_or_create(title=title, defaults=dict(
            kind=kind, eyebrow=eyebrow, subtitle=subtitle, image_url=image, cta_label=cta, cta_path=path,
            category=tops.get(cat) if cat else None, priority=priority, is_active=True,
            starts_at=now + timedelta(days=start), ends_at=now + timedelta(days=end)))
    # Redeemable seller offers (applied and re-validated by the server at checkout).
    for slug, title, desc, kind, value, cap, minimum in SELLER_OFFERS:
        StoreOffer.objects.update_or_create(store=sellers[slug], title=title, defaults=dict(
            description=desc, discount_type=kind, discount_value=D(value), max_discount=D(cap) if cap else None,
            min_order_amount=D(minimum), is_active=True, starts_at=None, ends_at=now + timedelta(days=30)))
    ShopCategory.objects.filter(slug="audio").update(icon="headphones")
    by_sub = {s: p for _t, s, _n, _y, _sel, _v, p in SUBS}
    for sub_slug, idx, kind, pct, hours, limit in DEALS:
        name = by_sub[sub_slug][idx][0]
        product = Product.objects.get(store__slug=next(sel for _t, s, _n, _y, sel, *_ in SUBS if s == sub_slug), name=name)
        ProductDeal.objects.update_or_create(product=product, kind=kind, defaults=dict(
            percent_off=pct, starts_at=now - timedelta(hours=2), ends_at=now + timedelta(hours=hours), quantity_limit=limit, is_active=True))
    log(f"shop: {len(TOP)} categories, {len(SUBS)} subcategories, {len(brands)} brands, {len(sellers)} sellers, {count} listings, "
        f"{len(DEALS)} deals, {len(CAMPAIGNS)} campaigns (1 ended, 1 upcoming)")


# --- history through the real services ---------------------------------------------------------------------

RETAIL_PATH = [OrderStatus.CONFIRMED, OrderStatus.PACKED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]


def _variant_for(product):
    v = product.variants.filter(is_active=True).exclude(stock_quantity=0).first()
    return v.id if v else None


def _buy(profile, address, lines, key, *, method="cash_on_delivery", final=OrderStatus.DELIVERED, days_ago=0):
    """Cart -> checkout -> status flow, exactly as a customer and sellers would. Returns the orders."""
    cart = cart_services.get_or_create_cart(profile)
    cart_services.clear_cart(cart)
    for product, qty in lines:
        cart_services.add_item(profile, product.id, qty, variant_id=_variant_for(product))
    _, orders, _ = order_services.place_checkout(customer=profile, address_id=address.id, payment_method=method, idempotency_key=key)
    for order in orders:
        if final != OrderStatus.PLACED:
            for step in RETAIL_PATH[: RETAIL_PATH.index(final) + 1]:
                order = order_services.transition_order(order, step)
        at = timezone.now() - timedelta(days=days_ago, hours=3)
        Order.objects.filter(pk=order.pk).update(created_at=at, delivered_at=at + timedelta(days=2) if final == OrderStatus.DELIVERED else None)
        for i, ev in enumerate(OrderStatusEvent.objects.filter(order=order).order_by("created_at")):
            OrderStatusEvent.objects.filter(pk=ev.pk).update(created_at=at + timedelta(hours=10 * i))
    return orders


def _reviewer(name, locality):
    email = f"reviewer.{name.lower()}@click.local"
    user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=f"{name} (dev reviewer)", phone_verified=False)
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    lat, lng = locality_point(locality, email)
    address, _ = Address.objects.get_or_create(customer=profile, line1="Dev reviewer address", defaults=dict(
        label="home", recipient_name=name, phone="+91 00000 00099", line2=locality, city="Bengaluru", state="Karnataka",
        postal_code="560001", country="IN", is_default=True, latitude=lat, longitude=lng))
    return profile, address


@transaction.atomic
def seed_reviews(log) -> None:
    """Dev reviewers buy ~10 listings each, receive them and review most of them (ratings come from these)."""
    if ProductReview.objects.filter(customer__user__email__startswith="reviewer.").exists():
        return
    listings = list(Product.objects.filter(shop_category__isnull=False, is_active=True, store__store_type=StoreType.RETAIL).order_by("name"))
    made = 0
    for r, (name, locality) in enumerate(REVIEWERS):
        profile, address = _reviewer(name, locality)
        picks = [p for p in listings if (h(p.name) + r * 7) % 4 == 0][:10]
        for j in range(0, len(picks), 2):
            pair = [p for p in picks[j:j + 2] if _orderable(p)]
            if not pair:
                continue
            try:
                with transaction.atomic():
                    _buy(profile, address, [(p, 1 + (h(p.name) % 2)) for p in pair], uuid.uuid5(NS, f"reviewer-{name.lower()}-{j}"),
                         days_ago=1 + (h(pair[0].name) + j) % 40)
            except DomainError as e:  # e.g. stock ran out in an earlier seed run: skip, never fake
                log(f"  skipped reviewer order: {e}")
                continue
            for p in pair:
                n = h(p.name + name)
                if n % 10 < 7:
                    rating = [5, 5, 4, 5, 4, 3, 5, 4, 2, 5][n % 10]
                    title, body = REVIEW_TEXT[rating][n % len(REVIEW_TEXT[rating])]
                    save_review(profile, p, rating=rating, title=title, body=body, create=True)
                    made += 1
    log(f"shop reviews: {made} verified-purchase reviews from {len(REVIEWERS)} dev reviewers (orders placed and delivered through the real services)")


def _orderable(p) -> bool:
    variants = p.variants.filter(is_active=True)
    if variants.exists():
        return variants.exclude(stock_quantity=0).exists()
    return p.is_orderable


def seed_shop_history(profile, log) -> None:
    """The test customer's Shopping history: a delivered two-seller checkout (returnable), one shipped order, views."""
    seed_reviews(log)
    if profile.checkouts.exists():
        return
    address = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
    WalletTransaction.objects.get_or_create(customer=profile, kind=WalletTransaction.Kind.PROMO, description="Shopping test credit (DEVELOPMENT MOCK DATA)",
                                            defaults={"amount": D("5000.00")})
    earbuds = Product.objects.get(store__slug="volt-electronics", name="Pulse Lite Wireless Earbuds")
    tee = Product.objects.get(store__slug="thread-loom", name="Classic Crew T-shirt")
    lamp = Product.objects.get(store__slug="hearth-home-store", name="Ceramic Table Lamp")
    try:
        with transaction.atomic():
            _buy(profile, address, [(earbuds, 1), (tee, 2)], uuid.uuid5(NS, "test-shop-1"), method="wallet", days_ago=4)
        with transaction.atomic():
            _buy(profile, address, [(lamp, 1)], uuid.uuid5(NS, "test-shop-2"), final=OrderStatus.SHIPPED, days_ago=1)
    except DomainError as e:
        log(f"  skipped test customer shopping orders: {e}")
        return
    log("shop: test customer has a delivered 2-seller checkout (wallet, returnable) and a shipped order")
