"""
The Click Partner catalogue: partner types, categories and their configuration.

This is the single place where category-specific behaviour is defined:

  identity   how to label the partner's name (individual vs business)
  fields     category-specific onboarding fields (validated by schema.py)
  location   which location inputs apply (service area / radius)
  home       how Partner Home behaves for this category (see HOME below): the
             workspace that supplies real work, status labels, metrics, quick
             actions, earnings label, performance metrics and location needs

A category inherits its type's configuration and may override it
(`individual`, `defaults`, `extra_fields`, `hide_fields`, `field_labels`, `home`).
Data migrations and `manage.py sync_partner_catalog` upsert this into the
PartnerType / PartnerCategory tables; apps read it from the API, so adding a
category never requires frontend changes.
"""

from __future__ import annotations

import copy


def _opt(*pairs: tuple[str, str]) -> list[dict]:
    return [{"value": v, "label": label} for v, label in pairs]


HOURS = [
    {"key": "opens_at", "label": "Opens at", "kind": "time", "required": True},
    {"key": "closes_at", "label": "Closes at", "kind": "time", "required": True},
]

TYPES: list[dict] = [
    {
        "slug": "transport",
        "name": "Transport",
        "description": "Drive with Click: rides, autos, bikes and fleets.",
        "icon": "car",
        "configuration": {
            "tagline": "Accept rides and earn on your schedule.",
            "identity": {"individual": True},
            "fields": [
                {
                    "key": "vehicle_type", "label": "Vehicle type", "kind": "select", "required": True,
                    "options": _opt(
                        ("car", "Car / Cab"), ("auto", "Auto rickshaw"), ("bike", "Bike / Scooter"),
                        ("ev_bike", "Electric bike"), ("van", "Van"), ("mini_truck", "Mini truck"),
                    ),
                },
                {"key": "vehicle_model", "label": "Vehicle make & model", "kind": "text", "required": False,
                 "placeholder": "e.g. Maruti Dzire", "max_length": 60},
                {"key": "vehicle_color", "label": "Vehicle colour", "kind": "text", "required": False,
                 "placeholder": "e.g. White", "max_length": 20, "help": "Shown to riders so they can find your vehicle."},
                {"key": "vehicle_number", "label": "Vehicle registration number", "kind": "text", "required": True,
                 "placeholder": "e.g. KA 01 AB 1234", "max_length": 15,
                 "help": "As printed on your registration certificate. Used for verification."},
                {
                    "key": "availability", "label": "When will you drive?", "kind": "select", "required": True,
                    "options": _opt(("full_time", "Full time"), ("part_time", "Part time"), ("weekends", "Weekends")),
                },
            ],
            "location": {"title": "Where will you operate?", "address_label": "Your address", "service_area": True},
            "home": {
                "availability_label": "Online / Offline",
                "modules": [
                    {"key": "ride_requests", "label": "Ride requests", "empty": "No ride requests yet."},
                    {"key": "active_ride", "label": "Active ride", "empty": "You have no active ride."},
                    {"key": "trips", "label": "Trips", "empty": "No trips yet."},
                    {"key": "earnings", "label": "Earnings", "empty": "No earnings yet."},
                ],
            },
        },
        "categories": [
            {"slug": "driver", "name": "Driver", "description": "Drive your own car for Click rides.", "icon": "car"},
            {"slug": "cab-driver", "name": "Cab Driver", "description": "Taxi and cab rides around your city.", "icon": "car",
             "configuration": {"defaults": {"vehicle_type": "car"}}},
            {"slug": "auto-driver", "name": "Auto Driver", "description": "Auto rickshaw rides.", "icon": "auto",
             "configuration": {"defaults": {"vehicle_type": "auto"}}},
            {"slug": "bike-rider", "name": "Bike Rider", "description": "Quick bike taxi rides.", "icon": "bike",
             "configuration": {"defaults": {"vehicle_type": "bike"}}},
            {"slug": "delivery-rider", "name": "Delivery Rider", "description": "Deliver food, groceries and parcels.",
             "icon": "bike", "configuration": {"defaults": {"vehicle_type": "bike"}}},
            {"slug": "fleet-operator", "name": "Fleet Operator", "description": "Run a fleet of vehicles and drivers.",
             "icon": "fleet", "configuration": {
                 "individual": False, "hide_fields": ["vehicle_number", "vehicle_model"],
                 "extra_fields": [{"key": "fleet_size", "label": "Vehicles in your fleet", "kind": "number",
                                   "required": True, "min": 1, "max": 10000}],
             }},
            {"slug": "rental-vehicle", "name": "Rental Vehicle", "description": "Rent out cars, bikes or vans.",
             "icon": "key", "configuration": {
                 "individual": False, "hide_fields": ["vehicle_number", "vehicle_model"],
                 "extra_fields": [{"key": "fleet_size", "label": "Vehicles available to rent", "kind": "number",
                                   "required": True, "min": 1, "max": 10000}],
             }},
            {"slug": "transport-provider", "name": "Transport Provider", "description": "Buses, shuttles and other transport.",
             "icon": "bus", "configuration": {
                 "individual": False, "hide_fields": ["vehicle_number", "vehicle_model"],
                 "extra_fields": [{"key": "fleet_size", "label": "Vehicles operated", "kind": "number",
                                   "required": True, "min": 1, "max": 10000}],
             }},
        ],
    },
    {
        "slug": "food",
        "name": "Food & Dining",
        "description": "Restaurants, cafes, cloud kitchens and food vendors.",
        "icon": "food",
        "configuration": {
            "tagline": "Receive orders and serve more customers.",
            "identity": {"individual": False, "business_name_label": "Restaurant / outlet name"},
            "fields": [
                {
                    "key": "cuisines", "label": "Cuisines you serve", "kind": "multiselect", "required": True, "max_items": 6,
                    "options": _opt(
                        ("north_indian", "North Indian"), ("south_indian", "South Indian"), ("chinese", "Chinese"),
                        ("biryani", "Biryani"), ("pizza", "Pizza"), ("burgers", "Burgers"), ("street_food", "Street food"),
                        ("desserts", "Desserts"), ("bakery", "Bakery"), ("beverages", "Beverages"),
                        ("healthy", "Healthy"), ("continental", "Continental"), ("other", "Other"),
                    ),
                },
                {
                    "key": "food_type", "label": "Food type", "kind": "select", "required": True,
                    "options": _opt(("veg", "Pure vegetarian"), ("non_veg", "Non-vegetarian"), ("both", "Veg & non-veg")),
                },
                *HOURS,
                {"key": "fssai_number", "label": "FSSAI licence number", "kind": "text", "required": False,
                 "max_length": 20, "help": "Optional now. Needed before verification is approved."},
            ],
            "location": {"title": "Where is your outlet?", "address_label": "Outlet address", "service_area": False},
            "home": {
                "availability_label": "Open / Closed",
                "modules": [
                    {"key": "new_orders", "label": "New orders", "empty": "No new orders yet."},
                    {"key": "preparing", "label": "Preparing", "empty": "Nothing being prepared."},
                    {"key": "ready", "label": "Ready orders", "empty": "No orders ready for pickup."},
                    {"key": "completed", "label": "Completed", "empty": "No completed orders yet."},
                    {"key": "sales", "label": "Sales", "empty": "No sales yet."},
                ],
            },
        },
        "categories": [
            {"slug": "restaurant", "name": "Restaurant", "description": "Dine-in and delivery restaurants.", "icon": "food"},
            {"slug": "cafe", "name": "Cafe", "description": "Coffee, snacks and light meals.", "icon": "coffee",
             "configuration": {"field_labels": {"business_name": "Cafe name"}}},
            {"slug": "cloud-kitchen", "name": "Cloud Kitchen", "description": "Delivery-only kitchens.", "icon": "food",
             "configuration": {"field_labels": {"business_name": "Kitchen / brand name"}}},
            {"slug": "bakery", "name": "Bakery", "description": "Breads, cakes and baked goods.", "icon": "cake",
             "configuration": {"defaults": {"cuisines": ["bakery", "desserts"]}, "field_labels": {"business_name": "Bakery name"}}},
            {"slug": "catering", "name": "Catering", "description": "Event and bulk catering.", "icon": "food",
             "configuration": {"field_labels": {"business_name": "Catering business name"}}},
            {"slug": "food-vendor", "name": "Food Vendor", "description": "Food stalls, carts and street food.", "icon": "food",
             "configuration": {"defaults": {"cuisines": ["street_food"]}, "field_labels": {"business_name": "Stall / vendor name"}}},
        ],
    },
    {
        "slug": "retail",
        "name": "Grocery & Retail",
        "description": "Grocery stores, supermarkets and shops.",
        "icon": "grocery",
        "configuration": {
            "tagline": "Sell to customers nearby with fast delivery.",
            "identity": {"individual": False, "business_name_label": "Store name"},
            "fields": [
                *HOURS,
                {
                    "key": "fulfilment", "label": "How will customers get orders?", "kind": "multiselect", "required": True,
                    "options": _opt(("delivery", "Home delivery"), ("pickup", "Store pickup")),
                },
                {"key": "product_range", "label": "What do you sell?", "kind": "textarea", "required": False,
                 "max_length": 300, "placeholder": "e.g. Fresh produce, staples, dairy, household essentials"},
            ],
            "location": {"title": "Where is your store?", "address_label": "Store address", "service_area": True,
                         "service_radius": True},
            "home": {
                "availability_label": "Store open / closed",
                "modules": [
                    {"key": "new_orders", "label": "New orders", "empty": "No new orders yet."},
                    {"key": "packing", "label": "Packing", "empty": "Nothing to pack."},
                    {"key": "ready", "label": "Ready", "empty": "No orders ready."},
                    {"key": "inventory", "label": "Inventory", "empty": "No products added yet."},
                    {"key": "sales", "label": "Sales", "empty": "No sales yet."},
                ],
            },
        },
        "categories": [
            {"slug": "grocery-store", "name": "Grocery Store", "description": "Daily groceries and essentials.", "icon": "grocery"},
            {"slug": "supermarket", "name": "Supermarket", "description": "Large-format grocery and household.", "icon": "grocery"},
            {"slug": "retail-store", "name": "Retail Store", "description": "Any retail shop.", "icon": "shop"},
            {"slug": "general-store", "name": "General Store", "description": "Neighbourhood kirana and general stores.", "icon": "shop"},
            {"slug": "electronics-store", "name": "Electronics Store", "description": "Phones, gadgets and appliances.", "icon": "device"},
            {"slug": "fashion-store", "name": "Fashion Store", "description": "Clothing, footwear and accessories.", "icon": "shirt"},
            {"slug": "other-retail", "name": "Other Retail", "description": "Any other shop.", "icon": "shop"},
        ],
    },
    {
        "slug": "logistics",
        "name": "Parcel & Logistics",
        "description": "Parcel, courier and delivery businesses.",
        "icon": "parcel",
        "configuration": {
            "tagline": "Pick up, move and deliver parcels with Click.",
            "identity": {"individual": False, "business_name_label": "Company / partner name"},
            "fields": [
                {
                    "key": "services", "label": "Services you offer", "kind": "multiselect", "required": True,
                    "options": _opt(
                        ("same_day", "Same-day"), ("next_day", "Next-day"), ("express", "Express (under 2 hours)"),
                        ("intercity", "Intercity"), ("bulk", "Bulk / B2B"),
                    ),
                },
                {"key": "daily_capacity", "label": "Parcels you can handle per day", "kind": "number", "required": True,
                 "min": 1, "max": 1000000},
                {"key": "fleet_size", "label": "Delivery vehicles", "kind": "number", "required": False, "min": 0, "max": 100000},
            ],
            "location": {"title": "Where do you operate?", "address_label": "Hub / office address", "service_area": True,
                         "service_radius": True},
            "home": {
                "availability_label": "Accepting jobs",
                "modules": [
                    {"key": "available_jobs", "label": "Available jobs", "empty": "No delivery jobs yet."},
                    {"key": "active_deliveries", "label": "Active deliveries", "empty": "No active deliveries."},
                    {"key": "completed_deliveries", "label": "Completed deliveries", "empty": "No completed deliveries yet."},
                    {"key": "earnings", "label": "Earnings", "empty": "No earnings yet."},
                ],
            },
        },
        "categories": [
            {"slug": "parcel-partner", "name": "Parcel Partner", "description": "Pick up and deliver parcels.", "icon": "parcel",
             "configuration": {"individual": True, "hide_fields": ["fleet_size"]}},
            {"slug": "courier-partner", "name": "Courier Partner", "description": "Courier and document delivery.", "icon": "parcel"},
            {"slug": "delivery-agency", "name": "Delivery Agency", "description": "Agencies with delivery staff.", "icon": "fleet"},
            {"slug": "logistics-provider", "name": "Logistics Provider", "description": "Warehousing and freight.", "icon": "warehouse"},
            {"slug": "delivery-company", "name": "Fleet / Delivery Company", "description": "Delivery fleets at scale.", "icon": "fleet"},
        ],
    },
    {
        "slug": "services",
        "name": "Manpower & Services",
        "description": "Technicians, home services and manpower.",
        "icon": "wrench",
        "configuration": {
            "tagline": "Get service requests and grow your work.",
            "identity": {"individual": False, "business_name_label": "Service / business name"},
            "fields": [
                {
                    "key": "service_types", "label": "Services you provide", "kind": "multiselect", "required": True,
                    "max_items": 8,
                    "options": _opt(
                        ("cleaning", "Cleaning"), ("electrical", "Electrical"), ("plumbing", "Plumbing"),
                        ("carpentry", "Carpentry"), ("appliance_repair", "Appliance repair"),
                        ("vehicle_repair", "Vehicle repair"), ("painting", "Painting"), ("pest_control", "Pest control"),
                        ("event_staff", "Event staff"), ("security", "Security"), ("housekeeping", "Housekeeping"),
                        ("professional", "Professional services"), ("other", "Other"),
                    ),
                },
                {"key": "workforce_size", "label": "Workers available", "kind": "number", "required": True,
                 "min": 1, "max": 100000},
                {
                    "key": "availability", "label": "Working days", "kind": "select", "required": True,
                    "options": _opt(("all_days", "All days"), ("weekdays", "Weekdays"), ("weekends", "Weekends"),
                                    ("on_request", "On request")),
                },
                {"key": "experience_years", "label": "Years of experience", "kind": "number", "required": False,
                 "min": 0, "max": 60},
            ],
            "location": {"title": "Where do you work?", "address_label": "Base address", "service_area": True,
                         "service_radius": True},
            "home": {
                "availability_label": "Available / Unavailable",
                "modules": [
                    {"key": "service_requests", "label": "Service requests", "empty": "No service requests yet."},
                    {"key": "available_workers", "label": "Available workers", "empty": "No workers added yet."},
                    {"key": "active_jobs", "label": "Active jobs", "empty": "No active jobs."},
                    {"key": "completed_jobs", "label": "Completed jobs", "empty": "No completed jobs yet."},
                    {"key": "earnings", "label": "Earnings", "empty": "No earnings yet."},
                ],
            },
        },
        "categories": [
            {"slug": "manpower-provider", "name": "Manpower Provider", "description": "Supply skilled and general workers.", "icon": "team"},
            {"slug": "cleaning-service", "name": "Cleaning Service", "description": "Home and office cleaning.", "icon": "sparkle",
             "configuration": {"defaults": {"service_types": ["cleaning"]}}},
            *[
                {"slug": slug, "name": name, "description": desc, "icon": "wrench", "configuration": {
                    "individual": True, "hide_fields": ["workforce_size"], "defaults": {"service_types": [default]},
                }}
                for slug, name, desc, default in [
                    ("electrician", "Electrician", "Wiring, fittings and repairs.", "electrical"),
                    ("plumber", "Plumber", "Pipes, taps and water fittings.", "plumbing"),
                    ("carpenter", "Carpenter", "Furniture and woodwork.", "carpentry"),
                    ("mechanic", "Mechanic", "Vehicle servicing and repair.", "vehicle_repair"),
                    ("technician", "Technician", "Appliance and equipment repair.", "appliance_repair"),
                ]
            ],
            {"slug": "home-service", "name": "Home Service", "description": "Other services at customers' homes.", "icon": "home"},
            {"slug": "professional-service", "name": "Professional Service", "description": "Consultants and professionals.",
             "icon": "briefcase", "configuration": {"defaults": {"service_types": ["professional"]}}},
            {"slug": "event-service", "name": "Event Service", "description": "Event staff, decor and support.", "icon": "ticket",
             "configuration": {"defaults": {"service_types": ["event_staff"]}}},
        ],
    },
    {
        "slug": "entertainment",
        "name": "Cinema & Entertainment",
        "description": "Cinemas, theatres, venues and events.",
        "icon": "film",
        "configuration": {
            "tagline": "Sell tickets and fill every show.",
            "identity": {"individual": False, "business_name_label": "Venue name"},
            "fields": [
                {"key": "screens", "label": "Screens / halls", "kind": "number", "required": True, "min": 1, "max": 100},
                {"key": "seating_capacity", "label": "Total seating capacity", "kind": "number", "required": False,
                 "min": 1, "max": 200000},
                *HOURS,
            ],
            "location": {"title": "Where is your venue?", "address_label": "Venue address", "service_area": False},
            "home": {
                "availability_label": "Bookings open / closed",
                "modules": [
                    {"key": "todays_bookings", "label": "Today's bookings", "empty": "No bookings today."},
                    {"key": "shows", "label": "Shows", "empty": "No shows scheduled."},
                    {"key": "tickets", "label": "Tickets", "empty": "No tickets sold yet."},
                    {"key": "occupancy", "label": "Occupancy", "empty": "No occupancy data yet."},
                    {"key": "revenue", "label": "Revenue", "empty": "No revenue yet."},
                ],
            },
        },
        "categories": [
            {"slug": "cinema-hall", "name": "Cinema Hall", "description": "Movie theatres and multiplexes.", "icon": "film"},
            {"slug": "theatre", "name": "Theatre", "description": "Plays, performances and shows.", "icon": "ticket",
             "configuration": {"field_labels": {"screens": "Stages / auditoriums"}}},
            {"slug": "event-venue", "name": "Event Venue", "description": "Venues for concerts and events.", "icon": "ticket",
             "configuration": {"field_labels": {"screens": "Event spaces"}}},
            {"slug": "entertainment-provider", "name": "Entertainment Provider", "description": "Gaming, fun zones and experiences.",
             "icon": "sparkle", "configuration": {"field_labels": {"screens": "Zones / attractions"}}},
            {"slug": "ticketing-venue", "name": "Ticketing Venue", "description": "Any venue that sells tickets.", "icon": "ticket",
             "configuration": {"field_labels": {"screens": "Halls / gates"}}},
        ],
    },
    {
        "slug": "hospitality",
        "name": "Hotels & Venues",
        "description": "Hotels, resorts, venues and activities.",
        "icon": "hotel",
        "configuration": {
            "tagline": "Take bookings and welcome more guests.",
            "identity": {"individual": False, "business_name_label": "Property name"},
            "fields": [
                {
                    "key": "property_type", "label": "Property type", "kind": "select", "required": True,
                    "options": _opt(
                        ("hotel", "Hotel"), ("resort", "Resort"), ("guest_house", "Guest house"),
                        ("banquet", "Banquet / event hall"), ("sports", "Sports venue"), ("activity", "Activity centre"),
                        ("other", "Other"),
                    ),
                },
                {"key": "capacity", "label": "Rooms or guest capacity", "kind": "number", "required": True,
                 "min": 1, "max": 100000},
                {"key": "check_in_time", "label": "Check-in / opening time", "kind": "time", "required": False},
            ],
            "location": {"title": "Where is your property?", "address_label": "Property address", "service_area": False},
            "home": {
                "availability_label": "Accepting bookings",
                "modules": [
                    {"key": "bookings", "label": "Bookings", "empty": "No bookings yet."},
                    {"key": "check_ins", "label": "Today's check-ins", "empty": "No check-ins today."},
                    {"key": "occupancy", "label": "Occupancy", "empty": "No occupancy data yet."},
                    {"key": "revenue", "label": "Revenue", "empty": "No revenue yet."},
                ],
            },
        },
        "categories": [
            {"slug": "hotel", "name": "Hotel", "description": "Hotels and business stays.", "icon": "hotel",
             "configuration": {"defaults": {"property_type": "hotel"}}},
            {"slug": "resort", "name": "Resort", "description": "Resorts and holiday stays.", "icon": "hotel",
             "configuration": {"defaults": {"property_type": "resort"}}},
            {"slug": "venue", "name": "Venue", "description": "Banquet halls and event venues.", "icon": "ticket",
             "configuration": {"defaults": {"property_type": "banquet"}, "field_labels": {"capacity": "Guest capacity"}}},
            {"slug": "sports-venue", "name": "Sports Venue", "description": "Turfs, courts and sports clubs.", "icon": "ball",
             "configuration": {"defaults": {"property_type": "sports"}, "field_labels": {"capacity": "Courts / players capacity"}}},
            {"slug": "activity-provider", "name": "Activity Provider", "description": "Adventure, tours and activities.",
             "icon": "compass", "configuration": {"defaults": {"property_type": "activity"},
                                                  "field_labels": {"capacity": "Guests per session"}}},
        ],
    },
    {
        "slug": "local",
        "name": "Local Business",
        "description": "Independent sellers and local service providers.",
        "icon": "store",
        "configuration": {
            "tagline": "Bring your local business online with Click.",
            "identity": {"individual": False, "business_name_label": "Business name"},
            "fields": [
                {
                    "key": "offering", "label": "What do you offer?", "kind": "select", "required": True,
                    "options": _opt(("products", "Products"), ("services", "Services"), ("both", "Products & services")),
                },
                {"key": "business_summary", "label": "Describe your business", "kind": "textarea", "required": True,
                 "max_length": 300, "placeholder": "What customers can get from you"},
                {"key": "opens_at", "label": "Opens at", "kind": "time", "required": False},
                {"key": "closes_at", "label": "Closes at", "kind": "time", "required": False},
            ],
            "location": {"title": "Where is your business?", "address_label": "Business address", "service_area": True},
            "home": {
                "availability_label": "Open / Closed",
                "modules": [
                    {"key": "requests", "label": "Orders & requests", "empty": "No orders or requests yet."},
                    {"key": "customers", "label": "Customers", "empty": "No customers yet."},
                    {"key": "sales", "label": "Sales", "empty": "No sales yet."},
                ],
            },
        },
        "categories": [
            {"slug": "local-business", "name": "Local Business", "description": "Any neighbourhood business.", "icon": "store"},
            {"slug": "independent-seller", "name": "Independent Seller", "description": "Sell your own products.", "icon": "bag",
             "configuration": {"individual": True, "defaults": {"offering": "products"}}},
            {"slug": "service-provider", "name": "Service Provider", "description": "Offer a local service.", "icon": "wrench",
             "configuration": {"defaults": {"offering": "services"}}},
            {"slug": "other", "name": "Other", "description": "Something else? Tell us about it.", "icon": "plus"},
        ],
    },
]

# --- Partner Home ------------------------------------------------------------------------------
# Category → workspace → Home configuration → visible modules → real backend data.
#
#   workspace      which provider supplies the partner's work (apps.partners.workspace.PROVIDERS):
#                  rides (Click. Ride), orders (stores the partner operates), venue (shows and bookings),
#                  or upcoming (the customer service doesn't exist on Click yet; Home says so honestly)
#   status         labels for the partner-controlled availability toggle (never "Online" for everyone)
#   location       "live" (current position while online, with permission) or "business" (saved address only)
#   metrics        Today's overview tiles, in order, from the keys the workspace provides
#   quick_actions  shortcut keys from the workspace (unknown or unsupported keys are dropped, never shown dead)
#   earnings_label / performance  as named
#   upcoming       for workspace "upcoming": what the service is called and what will appear when it launches

def _status(on: str, off: str, turn_on: str, turn_off: str, on_hint: str, off_hint: str, confirm_off: str = "") -> dict:
    return {"on": on, "off": off, "turn_on": turn_on, "turn_off": turn_off, "on_hint": on_hint, "off_hint": off_hint,
            "confirm_off": confirm_off}


HOME: dict[str, dict] = {
    "transport": {
        "workspace": "rides", "location": "live", "work_noun": "ride",
        "status": _status("Online", "Offline", "Go online", "Go offline",
                          "You’ll receive ride requests near you.", "You won’t receive ride requests.",
                          "You’ll stop receiving ride requests until you go online again."),
        "metrics": ["trips", "earnings", "distance", "online_time"],
        "quick_actions": ["requests", "active", "trips", "earnings"],
        "earnings_label": "Today’s earnings",
        "performance": ["rating", "acceptance_rate", "completion_rate"],
    },
    "food": {
        "workspace": "orders", "location": "business", "work_noun": "order",
        "status": _status("Open", "Closed", "Open restaurant", "Close restaurant",
                          "Customers can order from you now.", "Customers can’t place new orders.",
                          "Customers won’t be able to order until you open again. Orders already placed stay in your queue."),
        "metrics": ["orders", "sales", "completed", "pending"],
        "quick_actions": ["new", "preparing", "ready", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "retail": {
        "workspace": "orders", "location": "business", "work_noun": "order",
        "status": _status("Open", "Closed", "Open store", "Close store",
                          "Customers can order from your store now.", "Customers can’t place new orders.",
                          "Customers won’t be able to order until you open again. Orders already placed stay in your queue."),
        "metrics": ["orders", "sales", "items_sold", "pending"],
        "quick_actions": ["new", "packing", "inventory", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "local": {
        "workspace": "orders", "location": "business", "work_noun": "order",
        "status": _status("Open", "Closed", "Open business", "Close business",
                          "Customers can order from you now.", "Customers can’t place new orders.",
                          "Customers won’t be able to order until you open again."),
        "metrics": ["orders", "sales", "completed", "pending"],
        "quick_actions": ["new", "active", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "entertainment": {
        "workspace": "venue", "location": "business", "work_noun": "booking",
        "status": _status("Bookings open", "Bookings closed", "Open bookings", "Close bookings",
                          "Customers can book your shows.", "Customers can’t book new seats.",
                          "Customers won’t be able to book seats for your shows until you open bookings again. "
                          "Existing bookings stay valid."),
        "metrics": ["shows", "tickets", "occupancy", "revenue"],
        "quick_actions": ["shows", "bookings", "earnings"],
        "earnings_label": "Today’s revenue",
        "performance": ["occupancy_7d", "cancellation_rate"],
    },
    "hospitality": {
        "workspace": "upcoming", "location": "business", "work_noun": "booking",
        "status": _status("Accepting bookings", "Not accepting", "Accept bookings", "Stop bookings", "", ""),
        "upcoming": {"service": "Click. Stays", "what": "room and venue bookings, check-ins, check-outs and revenue"},
        "metrics": ["bookings", "check_ins", "check_outs", "revenue"],
        "quick_actions": [], "earnings_label": "Today’s revenue", "performance": [],
    },
    "logistics": {
        "workspace": "parcels", "location": "live", "work_noun": "delivery",
        "status": _status("Available", "Unavailable", "Go available", "Go unavailable",
                          "You’ll receive Click. Parcel delivery requests near you.", "You won’t receive delivery requests.",
                          "You’ll stop receiving delivery requests until you go available again."),
        "metrics": ["deliveries", "completed", "earnings", "pending"],
        "quick_actions": ["requests", "active", "earnings"], "earnings_label": "Today’s deliveries", "performance": [],
    },
    "services": {
        "workspace": "services", "location": "business", "work_noun": "job",
        "status": _status("Available", "Unavailable", "Go available", "Go unavailable",
                          "Customers near you can book you for jobs now.", "You won’t get ‘as soon as possible’ requests.",
                          "You won’t get new ‘as soon as possible’ requests until you go available again. Scheduled jobs stay booked."),
        "metrics": ["jobs", "completed", "earnings", "rating"],
        "quick_actions": ["requests", "active", "earnings"], "earnings_label": "Today’s jobs", "performance": [],
    },
}

# Category-level Home overrides (shallow-merged over the type's Home).
CATEGORY_HOME: dict[str, dict] = {
    # Transport partners who don't drive Click. Ride trips themselves.
    "delivery-rider": {"workspace": "parcels", "work_noun": "delivery",
        "status": _status("Available", "Unavailable", "Go available", "Go unavailable",
                          "You’ll receive Click. Parcel delivery requests near you.", "You won’t receive delivery requests.",
                          "You’ll stop receiving delivery requests until you go available again."),
        "metrics": ["deliveries", "completed", "earnings", "pending"], "quick_actions": ["requests", "active", "earnings"],
        "earnings_label": "Today’s deliveries", "performance": []},
    **{slug: {"workspace": "upcoming", "location": "business", "upcoming": {
        "service": "Click. Fleet", "what": "your vehicles, drivers, trips and fleet earnings"}}
       for slug in ("fleet-operator", "rental-vehicle", "transport-provider")},
}

for _t in TYPES:
    _t["configuration"]["home"] = {**_t["configuration"]["home"], **HOME[_t["slug"]]}
    for _c in _t["categories"]:
        if _c["slug"] in CATEGORY_HOME:
            _c["configuration"] = {**(_c.get("configuration") or {}), "home": CATEGORY_HOME[_c["slug"]]}


def categories_with_workspace(workspace: str) -> list[str]:
    """Category slugs whose resolved Home uses `workspace` (e.g. who may be matched to Click. Ride trips)."""
    return [c["slug"] for t in TYPES for c in t["categories"]
            if (CATEGORY_HOME.get(c["slug"], {}).get("workspace") or HOME[t["slug"]]["workspace"]) == workspace]


IDENTITY_LABELS = {
    True: {"business_name_label": "Your full name", "business_name_help": "As on your government ID."},
    False: {"business_name_label": "Business name", "business_name_help": "The name customers will see."},
}


def resolve_configuration(type_config: dict, category_config: dict) -> dict:
    """Merge a type's configuration with a category's overrides into what apps consume."""
    type_config = copy.deepcopy(type_config or {})
    category_config = category_config or {}

    identity = dict(type_config.get("identity") or {})
    if "individual" in category_config:
        identity["individual"] = category_config["individual"]
        identity.pop("business_name_label", None)
    individual = bool(identity.get("individual"))
    labels = {**IDENTITY_LABELS[individual], **{k: v for k, v in identity.items() if k != "individual"}}
    field_labels = category_config.get("field_labels") or {}
    if "business_name" in field_labels:
        labels["business_name_label"] = field_labels["business_name"]

    hidden = set(category_config.get("hide_fields") or [])
    defaults = category_config.get("defaults") or {}
    fields = []
    for field in [*(type_config.get("fields") or []), *(category_config.get("extra_fields") or [])]:
        if field["key"] in hidden:
            continue
        field = dict(field)
        if field["key"] in field_labels:
            field["label"] = field_labels[field["key"]]
        if field["key"] in defaults:
            field["default"] = defaults[field["key"]]
        fields.append(field)

    return {
        "tagline": type_config.get("tagline", ""),
        "identity": {"individual": individual, **labels},
        "fields": fields,
        "location": {"service_area": False, "service_radius": False, **(type_config.get("location") or {})},
        "home": {**(type_config.get("home") or {"modules": []}), **(category_config.get("home") or {})},
    }


def apply_catalog(PartnerType, PartnerCategory) -> None:
    """Idempotently upsert the catalogue. Works with live or historical (migration) models."""
    for t_index, t in enumerate(TYPES):
        ptype, _ = PartnerType.objects.update_or_create(
            slug=t["slug"],
            defaults={
                "name": t["name"], "description": t["description"], "icon": t["icon"],
                "sort_order": t_index, "configuration": t["configuration"], "is_active": True,
            },
        )
        for c_index, c in enumerate(t["categories"]):
            PartnerCategory.objects.update_or_create(
                partner_type=ptype, slug=c["slug"],
                defaults={
                    "name": c["name"], "description": c["description"], "icon": c.get("icon", ""),
                    "sort_order": c_index, "configuration": c.get("configuration", {}), "is_active": True,
                },
            )
