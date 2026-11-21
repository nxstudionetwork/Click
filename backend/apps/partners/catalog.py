"""
The Click Partner catalogue: partner types, categories and their configuration.

Partner types mirror the services customers can actually use in the Click Customer App (Rides, Restaurants,
Groceries, Shops, Pharmacy, Parcel, Services, Events, Cinema & Shows, Hotels, Attractions & Experiences, Travel). A type
is the primary business; its categories are sub-kinds of that business (a Restaurant type has Cafe, Bakery, Cloud
Kitchen...). Entries marked `retired` stay resolvable for partners who already chose them but are no longer offered.

This is the single place where category-specific behaviour is defined:

  identity      how to label the partner's name (individual vs business)
  fields        category-specific onboarding fields (validated by schema.py)
  location      which location inputs apply (service area / radius)
  capabilities  what this kind of partner can do on Click; the category's defaults are granted when the Partner ID is
                created and Click staff (Business OS) can grant/revoke them. Matching and routing check them.
  documents     the verification documents this kind of partner must provide (Documents & verification)
  home          how Partner Home behaves (see HOME below): the workspace that supplies real work, status labels,
                metrics, quick actions, earnings label, performance metrics, navigation and location needs

A category inherits its type's configuration and may override it
(`individual`, `defaults`, `extra_fields`, `hide_fields`, `field_labels`, `capabilities`, `home`).
Data migrations and `manage.py sync_partner_catalog` upsert this into the
PartnerType / PartnerCategory tables; apps read it from the API, so adding a
category never requires frontend changes.
"""

from __future__ import annotations

import copy


def _opt(*pairs: tuple[str, str]) -> list[dict]:
    return [{"value": v, "label": label} for v, label in pairs]


def _cap(key: str, label: str, default: bool = True) -> dict:
    return {"key": key, "label": label, "default": default}


def _doc(key: str, label: str, *, required: bool = True, expires: bool = False, help: str = "") -> dict:
    return {"key": key, "label": label, "required": required, "expires": expires, "help": help}


ID_PROOF = _doc("identity_proof", "Government photo ID", help="Aadhaar, PAN, passport or voter ID of the owner.")
GST = _doc("gst_certificate", "GST registration", required=False)

HOURS = [
    {"key": "opens_at", "label": "Opens at", "kind": "time", "required": True},
    {"key": "closes_at", "label": "Closes at", "kind": "time", "required": True},
]

STORE_FULFILMENT = {
    "key": "fulfilment", "label": "How will customers get orders?", "kind": "multiselect", "required": True,
    "options": _opt(("delivery", "Home delivery"), ("pickup", "Store pickup")),
}

TYPES: list[dict] = [
    {
        "slug": "transport",
        "name": "Rides",
        "description": "Provide rides and transport services to Click customers.",
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
                {"key": "licence_number", "label": "Driving licence number", "kind": "text", "required": False,
                 "placeholder": "e.g. KA01 20190012345", "max_length": 20,
                 "help": "Checked against your licence document during verification."},
                {
                    "key": "availability", "label": "When will you drive?", "kind": "select", "required": True,
                    "options": _opt(("full_time", "Full time"), ("part_time", "Part time"), ("weekends", "Weekends")),
                },
            ],
            "location": {"title": "Where will you operate?", "address_label": "Your address", "service_area": True},
            "capabilities": [_cap("rides", "Click. Ride trips"), _cap("parcel_delivery", "Parcel delivery", False)],
            "documents": [
                _doc("driving_licence", "Driving licence", expires=True, help="Front side, clearly readable."),
                _doc("vehicle_registration", "Vehicle registration (RC)"),
                _doc("vehicle_insurance", "Vehicle insurance", expires=True),
                ID_PROOF,
            ],
            "home": {"availability_label": "Online / Offline", "modules": []},
        },
        "categories": [
            {"slug": "driver", "name": "Driver", "description": "Drive your own car for Click rides.", "icon": "car"},
            {"slug": "cab-driver", "name": "Cab Driver", "description": "Taxi and cab rides around your city.", "icon": "car",
             "configuration": {"defaults": {"vehicle_type": "car"}}},
            {"slug": "auto-driver", "name": "Auto Driver", "description": "Auto rickshaw rides.", "icon": "auto",
             "configuration": {"defaults": {"vehicle_type": "auto"}}},
            {"slug": "bike-rider", "name": "Bike Rider", "description": "Quick bike taxi rides.", "icon": "bike",
             "configuration": {"defaults": {"vehicle_type": "bike"}}},
            {"slug": "delivery-rider", "name": "Delivery Rider", "description": "Deliver parcels for Click. Parcel customers.",
             "icon": "bike", "configuration": {"defaults": {"vehicle_type": "bike"}, "capabilities": ["parcel_delivery"]}},
            # Retired: no customer-facing Click service uses them. Kept so partners who chose them still resolve.
            {"slug": "fleet-operator", "retired": True, "name": "Fleet Operator", "description": "Run a fleet of vehicles and drivers.",
             "icon": "fleet", "configuration": {
                 "individual": False, "hide_fields": ["vehicle_number", "vehicle_model", "licence_number"], "capabilities": [],
                 "extra_fields": [{"key": "fleet_size", "label": "Vehicles in your fleet", "kind": "number",
                                   "required": True, "min": 1, "max": 10000}],
             }},
            {"slug": "rental-vehicle", "retired": True, "name": "Rental Vehicle", "description": "Rent out cars, bikes or vans.",
             "icon": "key", "configuration": {
                 "individual": False, "hide_fields": ["vehicle_number", "vehicle_model", "licence_number"], "capabilities": [],
                 "extra_fields": [{"key": "fleet_size", "label": "Vehicles available to rent", "kind": "number",
                                   "required": True, "min": 1, "max": 10000}],
             }},
            {"slug": "transport-provider", "retired": True, "name": "Transport Provider", "description": "Buses, shuttles and other transport.",
             "icon": "bus", "configuration": {
                 "individual": False, "hide_fields": ["vehicle_number", "vehicle_model", "licence_number"], "capabilities": [],
                 "extra_fields": [{"key": "fleet_size", "label": "Vehicles operated", "kind": "number",
                                   "required": True, "min": 1, "max": 10000}],
             }},
        ],
    },
    {
        "slug": "food",
        "name": "Restaurants",
        "description": "Accept and manage customer food orders.",
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
            "capabilities": [_cap("food_orders", "Food orders"), _cap("delivery", "Delivery"), _cap("pickup", "Pickup", False),
                             _cap("dine_in", "Dine-in", False)],
            "documents": [_doc("fssai_licence", "FSSAI food licence", expires=True), ID_PROOF, GST],
            "home": {"availability_label": "Open / Closed", "modules": []},
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
        "slug": "groceries",
        "name": "Groceries",
        "description": "Sell daily essentials to customers nearby.",
        "icon": "grocery",
        "configuration": {
            "tagline": "Sell to customers nearby with fast delivery.",
            "identity": {"individual": False, "business_name_label": "Store name"},
            "fields": [
                *HOURS, STORE_FULFILMENT,
                {"key": "product_range", "label": "What do you sell?", "kind": "textarea", "required": False,
                 "max_length": 300, "placeholder": "e.g. Fresh produce, staples, dairy, household essentials"},
            ],
            "location": {"title": "Where is your store?", "address_label": "Store address", "service_area": True,
                         "service_radius": True},
            "capabilities": [_cap("store_orders", "Grocery orders"), _cap("delivery", "Delivery"), _cap("pickup", "Store pickup", False)],
            "documents": [_doc("shop_establishment", "Shop & establishment licence"), ID_PROOF, GST,
                          _doc("fssai_licence", "FSSAI licence (packaged food)", required=False, expires=True)],
            "home": {"availability_label": "Store open / closed", "modules": []},
        },
        "categories": [
            {"slug": "grocery-store", "name": "Grocery Store", "description": "Daily groceries and essentials.", "icon": "grocery"},
            {"slug": "supermarket", "name": "Supermarket", "description": "Large-format grocery and household.", "icon": "grocery"},
            {"slug": "general-store", "name": "General Store", "description": "Neighbourhood kirana and general stores.", "icon": "shop"},
        ],
    },
    {
        "slug": "retail",
        "name": "Shops",
        "description": "Sell products and manage customer orders.",
        "icon": "shop",
        "configuration": {
            "tagline": "Sell your products to Click. Shopping customers.",
            "identity": {"individual": False, "business_name_label": "Store name"},
            "fields": [
                *HOURS, STORE_FULFILMENT,
                {"key": "product_range", "label": "What do you sell?", "kind": "textarea", "required": False,
                 "max_length": 300, "placeholder": "e.g. Running shoes, sportswear and accessories"},
            ],
            "location": {"title": "Where is your store?", "address_label": "Store address", "service_area": True,
                         "service_radius": True},
            "capabilities": [_cap("store_orders", "Product orders"), _cap("delivery", "Delivery"), _cap("pickup", "Store pickup", False),
                             _cap("returns", "Returns", False)],
            "documents": [_doc("shop_establishment", "Shop & establishment licence"), ID_PROOF, GST],
            "home": {"availability_label": "Store open / closed", "modules": []},
        },
        "categories": [
            {"slug": "retail-store", "name": "Retail Store", "description": "Any retail shop.", "icon": "shop"},
            {"slug": "electronics-store", "name": "Electronics Store", "description": "Phones, gadgets and appliances.", "icon": "device"},
            {"slug": "fashion-store", "name": "Fashion Store", "description": "Clothing, footwear and accessories.", "icon": "shirt"},
            {"slug": "other-retail", "name": "Other Retail", "description": "Any other shop.", "icon": "shop"},
        ],
    },
    {
        "slug": "pharmacy",
        "name": "Pharmacy",
        "description": "Sell medicines and health essentials, with prescription checks.",
        "icon": "plus",
        "configuration": {
            "tagline": "Serve Click. Pharma customers from your licensed pharmacy.",
            "identity": {"individual": False, "business_name_label": "Pharmacy name"},
            "fields": [
                {"key": "drug_licence_number", "label": "Drug licence number", "kind": "text", "required": True, "max_length": 40,
                 "help": "Retail drug licence (Form 20/21) issued by your State Drugs Control authority."},
                {"key": "pharmacist_name", "label": "Registered pharmacist", "kind": "text", "required": True, "max_length": 80},
                {"key": "pharmacist_registration", "label": "Pharmacist registration number", "kind": "text", "required": True,
                 "max_length": 40, "help": "State Pharmacy Council registration. Prescriptions are reviewed under this pharmacist."},
                *HOURS, STORE_FULFILMENT,
            ],
            "location": {"title": "Where is your pharmacy?", "address_label": "Pharmacy address", "service_area": True,
                         "service_radius": True},
            "capabilities": [_cap("store_orders", "Medicine orders"), _cap("prescriptions", "Prescription review"),
                             _cap("delivery", "Delivery"), _cap("pickup", "Store pickup", False)],
            "documents": [_doc("drug_licence", "Retail drug licence", expires=True),
                          _doc("pharmacist_certificate", "Pharmacist registration certificate", expires=True), ID_PROOF, GST],
            "home": {"availability_label": "Open / Closed", "modules": []},
        },
        "categories": [
            {"slug": "pharmacy", "name": "Pharmacy", "description": "A licensed retail pharmacy / chemist.", "icon": "plus"},
        ],
    },
    {
        "slug": "logistics",
        "name": "Parcel",
        "description": "Provide parcel pickup, delivery and logistics services.",
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
            "capabilities": [_cap("parcel_delivery", "Parcel pickup & delivery")],
            "documents": [ID_PROOF, _doc("business_registration", "Business registration", required=False),
                          _doc("driving_licence", "Driving licence", required=False, expires=True)],
            "home": {"availability_label": "Accepting jobs", "modules": []},
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
        "name": "Services",
        "description": "Provide customer-requested services through Click.",
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
            "capabilities": [_cap("service_jobs", "Service bookings"), _cap("quotes", "Quotes for larger jobs"),
                             _cap("emergency", "Emergency / instant jobs", False)],
            "documents": [ID_PROOF, _doc("skill_certificate", "Trade or skill certificate", required=False, expires=True),
                          _doc("police_verification", "Police verification", required=False, expires=True)],
            "home": {"availability_label": "Available / Unavailable", "modules": []},
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
        ],
    },
    {
        "slug": "events",
        "name": "Events",
        "description": "Plan, decorate, photograph and host events for customers.",
        "icon": "gift",
        "configuration": {
            "tagline": "Get quote requests from customers planning events.",
            "identity": {"individual": False, "business_name_label": "Business / team name"},
            "fields": [
                {"key": "workforce_size", "label": "Team size", "kind": "number", "required": True, "min": 1, "max": 100000},
                {"key": "experience_years", "label": "Years of experience", "kind": "number", "required": False, "min": 0, "max": 60},
                {"key": "events_per_month", "label": "Events you can take per month", "kind": "number", "required": False,
                 "min": 1, "max": 1000},
            ],
            "location": {"title": "Where do you work?", "address_label": "Base address", "service_area": True,
                         "service_radius": True},
            "capabilities": [_cap("event_quotes", "Event quotes & bookings")],
            "documents": [ID_PROOF, _doc("business_registration", "Business registration", required=False), GST],
            "home": {"availability_label": "Accepting requests", "modules": []},
        },
        "categories": [
            {"slug": "event-planner", "name": "Event Planner", "description": "Plan and run complete events.", "icon": "gift"},
            {"slug": "event-decorator", "name": "Decorator", "description": "Event decoration, stage and setup.", "icon": "sparkle"},
            {"slug": "event-photographer", "name": "Photographer / Videographer", "description": "Event photos and films.", "icon": "camera",
             "configuration": {"individual": True, "hide_fields": ["workforce_size"]}},
            {"slug": "event-entertainer", "name": "DJ / Entertainer / Host", "description": "Music, hosting and entertainment.", "icon": "headphones",
             "configuration": {"individual": True, "hide_fields": ["workforce_size"]}},
            {"slug": "event-makeup", "name": "Makeup & Mehendi Artist", "description": "Bridal and party makeup, mehendi.", "icon": "beauty",
             "configuration": {"individual": True, "hide_fields": ["workforce_size"]}},
            {"slug": "event-service", "name": "Event Staff & Support", "description": "Event staff, setup and support.", "icon": "ticket"},
            {"slug": "venue", "name": "Event Venue / Banquet", "description": "Banquet halls and event venues.", "icon": "ticket",
             "configuration": {"field_labels": {"workforce_size": "Staff at the venue"},
                               "extra_fields": [{"key": "capacity", "label": "Guest capacity", "kind": "number", "required": True,
                                                 "min": 1, "max": 100000}]}},
        ],
    },
    {
        "slug": "entertainment",
        "name": "Cinema & Shows",
        "description": "Manage shows, bookings and customer check-ins.",
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
            "capabilities": [_cap("show_tickets", "Show tickets"), _cap("food_and_beverages", "Food & beverages", False)],
            "documents": [_doc("cinema_licence", "Cinema / performance licence", expires=True),
                          _doc("fire_noc", "Fire safety NOC", expires=True), ID_PROOF, GST],
            "home": {"availability_label": "Bookings open / closed", "modules": []},
        },
        "categories": [
            {"slug": "cinema-hall", "name": "Cinema Hall", "description": "Movie theatres and multiplexes.", "icon": "film"},
            {"slug": "theatre", "name": "Theatre", "description": "Plays, performances and shows.", "icon": "ticket",
             "configuration": {"field_labels": {"screens": "Stages / auditoriums"}}},
            {"slug": "event-venue", "name": "Live Show Venue", "description": "Concert, comedy and live-show venues.", "icon": "ticket",
             "configuration": {"field_labels": {"screens": "Event spaces"}}},
            {"slug": "ticketing-venue", "name": "Ticketing Venue", "description": "Any venue that sells show tickets.", "icon": "ticket",
             "configuration": {"field_labels": {"screens": "Halls / gates"}}},
            {"slug": "entertainment-provider", "retired": True, "name": "Entertainment Provider",
             "description": "Gaming, fun zones and experiences.", "icon": "sparkle",
             "configuration": {"field_labels": {"screens": "Zones / attractions"}}},
        ],
    },
    {
        "slug": "hospitality",
        "name": "Hotels",
        "description": "Manage stays, rooms and customer bookings.",
        "icon": "hotel",
        "configuration": {
            "tagline": "Take bookings and welcome more guests.",
            "identity": {"individual": False, "business_name_label": "Property name"},
            "fields": [
                {
                    "key": "property_type", "label": "Property type", "kind": "select", "required": True,
                    "options": _opt(
                        ("hotel", "Hotel"), ("resort", "Resort"), ("guest_house", "Guest house / homestay"),
                        ("apartment", "Serviced apartment"), ("other", "Other"),
                    ),
                },
                {"key": "capacity", "label": "Rooms", "kind": "number", "required": True, "min": 1, "max": 100000},
                {"key": "check_in_time", "label": "Check-in time", "kind": "time", "required": False},
            ],
            "location": {"title": "Where is your property?", "address_label": "Property address", "service_area": False},
            "capabilities": [_cap("room_bookings", "Room bookings"), _cap("pay_at_property", "Pay at property", False)],
            "documents": [_doc("trade_licence", "Hotel / trade licence", expires=True), _doc("fire_noc", "Fire safety NOC", expires=True),
                          ID_PROOF, GST],
            "home": {"availability_label": "Accepting bookings", "modules": []},
        },
        "categories": [
            {"slug": "hotel", "name": "Hotel", "description": "Hotels and business stays.", "icon": "hotel",
             "configuration": {"defaults": {"property_type": "hotel"}}},
            {"slug": "resort", "name": "Resort", "description": "Resorts and holiday stays.", "icon": "hotel",
             "configuration": {"defaults": {"property_type": "resort"}}},
            {"slug": "homestay", "name": "Homestay", "description": "Homestays and guest houses.", "icon": "home",
             "configuration": {"defaults": {"property_type": "guest_house"}}},
            {"slug": "serviced-apartment", "name": "Serviced Apartment", "description": "Serviced apartments and villas.", "icon": "hotel",
             "configuration": {"defaults": {"property_type": "apartment"}, "field_labels": {"capacity": "Units"}}},
        ],
    },
    {
        "slug": "experiences",
        "name": "Attractions & Experiences",
        "description": "Sell entry tickets, darshan slots and experiences.",
        "icon": "temple",
        "configuration": {
            "tagline": "Sell tickets for your place on Click. Bookings.",
            "identity": {"individual": False, "business_name_label": "Place / organisation name"},
            "fields": [
                {"key": "daily_capacity", "label": "Visitors per day", "kind": "number", "required": True, "min": 1, "max": 1000000},
                *HOURS,
            ],
            "location": {"title": "Where is your place?", "address_label": "Address", "service_area": False},
            "capabilities": [_cap("entry_tickets", "Entry tickets & slots")],
            "documents": [_doc("operating_permission", "Permission to operate / trust registration"), ID_PROOF],
            "home": {"availability_label": "Bookings open / closed", "modules": []},
        },
        "categories": [
            {"slug": "attraction", "name": "Attraction", "description": "Museums, parks, monuments and attractions.", "icon": "compass"},
            {"slug": "temple", "name": "Temple / Place of Worship", "description": "Darshan tickets and seva bookings.", "icon": "temple"},
            {"slug": "activity-provider", "name": "Activity Provider", "description": "Adventure, tours and activities.", "icon": "compass"},
            {"slug": "sports-venue", "name": "Sports Venue", "description": "Turfs, courts and sports clubs.", "icon": "ball"},
        ],
    },
    {
        "slug": "travel",
        "name": "Travel",
        "description": "Offer bus trips, tours and travel bookings.",
        "icon": "bus",
        "configuration": {
            "tagline": "Run trips Click. Travel customers book.",
            "identity": {"individual": False, "business_name_label": "Travels / company name"},
            "fields": [
                {
                    "key": "travel_services", "label": "What do you offer?", "kind": "multiselect", "required": True,
                    "options": _opt(("bus", "Bus trips"), ("tours", "Tours & packages"), ("tickets", "Ticket booking"),
                                    ("transfers", "Airport / station transfers")),
                },
                {"key": "fleet_size", "label": "Vehicles operated", "kind": "number", "required": False, "min": 0, "max": 10000},
                {"key": "years_operating", "label": "Years operating", "kind": "number", "required": False, "min": 0, "max": 100},
            ],
            "location": {"title": "Where do you operate from?", "address_label": "Office address", "service_area": True},
            "capabilities": [_cap("travel_trips", "Scheduled trips"), _cap("travel_packages", "Tours & packages", False)],
            "documents": [_doc("business_registration", "Business registration"),
                          _doc("tourism_licence", "Tour operator / stage carriage permit", expires=True), ID_PROOF, GST],
            "home": {"availability_label": "Bookings open / closed", "modules": []},
        },
        "categories": [
            {"slug": "bus-operator", "name": "Bus Operator", "description": "Intercity and sleeper bus services.", "icon": "bus",
             "configuration": {"defaults": {"travel_services": ["bus"]}}},
            {"slug": "tour-operator", "name": "Tour Operator", "description": "Guided tours and holiday packages.", "icon": "compass",
             "configuration": {"defaults": {"travel_services": ["tours"]}, "capabilities": ["travel_trips", "travel_packages"]}},
            {"slug": "travel-agency", "name": "Travel Agency", "description": "Tickets, transfers and trip planning.", "icon": "plane"},
        ],
    },
    {
        # Retired: "local business" is not a customer-facing Click service. Existing partners keep working.
        "slug": "local",
        "retired": True,
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
            "capabilities": [_cap("store_orders", "Orders")],
            "documents": [ID_PROOF],
            "home": {"availability_label": "Open / Closed", "modules": []},
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
#                  rides, orders (stores the partner operates), venue (shows), parcels, services, events, hotels,
#                  experiences, travel, or upcoming (the customer service doesn't exist on Click; Home says so)
#   mode           the Partner App mode: navigation, work label and menu entries (driver, restaurant, store, ...)
#   status         labels for the partner-controlled availability toggle (never "Online" for everyone)
#   location       "live" (current position while online, with permission) or "business" (saved address only)
#   metrics        Today's overview tiles, in order, from the keys the workspace provides
#   quick_actions  shortcut keys from the workspace (unknown or unsupported keys are dropped, never shown dead)
#   earnings_label / performance  as named
#   upcoming       for workspace "upcoming": what the service is called and what will appear when it launches

def _status(on: str, off: str, turn_on: str, turn_off: str, on_hint: str, off_hint: str, confirm_off: str = "") -> dict:
    return {"on": on, "off": off, "turn_on": turn_on, "turn_off": turn_off, "on_hint": on_hint, "off_hint": off_hint,
            "confirm_off": confirm_off}


_STORE_STATUS = _status("Open", "Closed", "Open store", "Close store",
                        "Customers can order from your store now.", "Customers can’t place new orders.",
                        "Customers won’t be able to order until you open again. Orders already placed stay in your queue.")
_PARCEL_HOME = {
    "workspace": "parcels", "mode": "parcel", "location": "live", "work_noun": "delivery",
    "status": _status("Available", "Unavailable", "Go available", "Go unavailable",
                      "You’ll receive Click. Parcel delivery requests near you.", "You won’t receive delivery requests.",
                      "You’ll stop receiving delivery requests until you go available again."),
    "metrics": ["deliveries", "completed", "earnings", "pending"],
    "quick_actions": ["requests", "active", "earnings"], "earnings_label": "Today’s deliveries", "performance": [],
}

HOME: dict[str, dict] = {
    "transport": {
        "workspace": "rides", "mode": "driver", "location": "live", "work_noun": "ride",
        "status": _status("Online", "Offline", "Go online", "Go offline",
                          "You’ll receive ride requests near you.", "You won’t receive ride requests.",
                          "You’ll stop receiving ride requests until you go online again."),
        "metrics": ["trips", "earnings", "distance", "online_time"],
        "quick_actions": ["requests", "active", "trips", "earnings"],
        "earnings_label": "Today’s earnings",
        "performance": ["rating", "acceptance_rate", "completion_rate"],
    },
    "food": {
        "workspace": "orders", "mode": "restaurant", "location": "business", "work_noun": "order",
        "status": _status("Open", "Closed", "Open restaurant", "Close restaurant",
                          "Customers can order from you now.", "Customers can’t place new orders.",
                          "Customers won’t be able to order until you open again. Orders already placed stay in your queue."),
        "metrics": ["orders", "sales", "completed", "pending"],
        "quick_actions": ["new", "preparing", "ready", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "groceries": {
        "workspace": "orders", "mode": "store", "location": "business", "work_noun": "order", "status": _STORE_STATUS,
        "metrics": ["orders", "sales", "items_sold", "pending"],
        "quick_actions": ["new", "packing", "inventory", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "retail": {
        "workspace": "orders", "mode": "store", "location": "business", "work_noun": "order", "status": _STORE_STATUS,
        "metrics": ["orders", "sales", "items_sold", "pending"],
        "quick_actions": ["new", "packing", "inventory", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "pharmacy": {
        "workspace": "orders", "mode": "pharmacy", "location": "business", "work_noun": "order",
        "status": _status("Open", "Closed", "Open pharmacy", "Close pharmacy",
                          "Customers can order from your pharmacy now.", "Customers can’t place new orders.",
                          "Customers won’t be able to order until you open again. Orders already placed stay in your queue."),
        "metrics": ["orders", "sales", "items_sold", "pending"],
        "quick_actions": ["new", "prescriptions", "packing", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "local": {
        "workspace": "orders", "mode": "store", "location": "business", "work_noun": "order",
        "status": _status("Open", "Closed", "Open business", "Close business",
                          "Customers can order from you now.", "Customers can’t place new orders.",
                          "Customers won’t be able to order until you open again."),
        "metrics": ["orders", "sales", "completed", "pending"],
        "quick_actions": ["new", "active", "earnings"],
        "earnings_label": "Today’s sales",
        "performance": ["rating", "acceptance_rate", "fulfilment_rate"],
    },
    "entertainment": {
        "workspace": "venue", "mode": "cinema", "location": "business", "work_noun": "booking",
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
        "workspace": "hotels", "mode": "hotel", "location": "business", "work_noun": "stay",
        "status": _status("Accepting bookings", "Not accepting", "Accept bookings", "Stop bookings",
                          "Guests can book your rooms on Click.", "Guests can’t make new bookings.",
                          "Guests won’t be able to book until you accept bookings again. Existing reservations stay confirmed."),
        "metrics": ["arrivals", "in_house", "departures", "revenue"], "quick_actions": ["arrivals", "in_house", "earnings"],
        "earnings_label": "Today’s stays", "performance": [],
    },
    "logistics": _PARCEL_HOME,
    "services": {
        "workspace": "services", "mode": "services", "location": "business", "work_noun": "job",
        "status": _status("Available", "Unavailable", "Go available", "Go unavailable",
                          "Customers near you can book you for jobs now.", "You won’t get ‘as soon as possible’ requests.",
                          "You won’t get new ‘as soon as possible’ requests until you go available again. Scheduled jobs stay booked."),
        "metrics": ["jobs", "completed", "earnings", "rating"],
        "quick_actions": ["requests", "active", "earnings"], "earnings_label": "Today’s jobs", "performance": [],
    },
    "events": {
        "workspace": "events", "mode": "events", "location": "business", "work_noun": "event",
        "status": _status("Accepting requests", "Not accepting", "Accept requests", "Pause requests",
                          "Customers planning events can ask you for quotes.", "You won’t get new quote requests.",
                          "You won’t get new quote requests until you accept them again. Existing bookings stay confirmed."),
        "metrics": ["requests", "upcoming", "earnings", "rating"], "quick_actions": ["requests", "active", "earnings"],
        "earnings_label": "Completed today", "performance": [],
    },
    "experiences": {
        "workspace": "experiences", "mode": "experiences", "location": "business", "work_noun": "visit",
        "status": _status("Bookings open", "Bookings closed", "Open bookings", "Close bookings",
                          "Visitors can book tickets for your place.", "Visitors can’t book new tickets.",
                          "Visitors won’t be able to book until you open bookings again. Existing tickets stay valid."),
        "metrics": ["visits", "checked_in", "upcoming", "revenue"], "quick_actions": ["today", "check_in", "earnings"],
        "earnings_label": "Today’s visits", "performance": [],
    },
    "travel": {
        "workspace": "travel", "mode": "travel", "location": "business", "work_noun": "trip",
        "status": _status("Bookings open", "Bookings closed", "Open bookings", "Close bookings",
                          "Customers can book seats on your trips.", "Customers can’t book new seats.",
                          "Customers won’t be able to book your trips until you open bookings again. Existing tickets stay valid."),
        "metrics": ["departures", "passengers", "seats_sold", "revenue"], "quick_actions": ["today", "upcoming", "earnings"],
        "earnings_label": "Today’s bookings", "performance": [],
    },
}

# Category-level Home overrides (shallow-merged over the type's Home).
CATEGORY_HOME: dict[str, dict] = {
    # Delivery riders are transport partners who carry Click. Parcel jobs rather than ride trips.
    "delivery-rider": _PARCEL_HOME,
    **{slug: {"workspace": "upcoming", "mode": "upcoming", "location": "business", "upcoming": {
        "service": "Click. Fleet", "what": "your vehicles, drivers, trips and fleet earnings"}}
       for slug in ("fleet-operator", "rental-vehicle", "transport-provider")},
    "entertainment-provider": {"workspace": "upcoming", "mode": "upcoming", "upcoming": {
        "service": "Click. Fun zones", "what": "your bookings and visitors"}},
}

for _t in TYPES:
    _t["configuration"]["home"] = {**_t["configuration"]["home"], **HOME[_t["slug"]]}
    for _c in _t["categories"]:
        if _c["slug"] in CATEGORY_HOME:
            _c["configuration"] = {**(_c.get("configuration") or {}), "home": CATEGORY_HOME[_c["slug"]]}


def _resolved_home(t: dict, c: dict) -> dict:
    return {**HOME[t["slug"]], **CATEGORY_HOME.get(c["slug"], {})}


def categories_with_workspace(workspace: str) -> list[str]:
    """Category slugs whose resolved Home uses `workspace` (e.g. who may be matched to Click. Ride trips)."""
    return [c["slug"] for t in TYPES for c in t["categories"] if _resolved_home(t, c)["workspace"] == workspace]


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

    capabilities = [dict(c) for c in type_config.get("capabilities") or []]
    if "capabilities" in category_config:  # the category names exactly which capabilities it starts with
        chosen = set(category_config["capabilities"])
        for c in capabilities:
            c["default"] = c["key"] in chosen

    return {
        "tagline": type_config.get("tagline", ""),
        "identity": {"individual": individual, **labels},
        "fields": fields,
        "location": {"service_area": False, "service_radius": False, **(type_config.get("location") or {})},
        "capabilities": capabilities,
        "documents": [dict(d) for d in type_config.get("documents") or []],
        "home": {**(type_config.get("home") or {"modules": []}), **(category_config.get("home") or {})},
    }


def default_capabilities(type_config: dict, category_config: dict) -> list[str]:
    return [c["key"] for c in resolve_configuration(type_config, category_config)["capabilities"] if c["default"]]


def apply_catalog(PartnerType, PartnerCategory, Partner=None) -> None:
    """
    Idempotently upsert the catalogue. Works with live or historical (migration) models.

    A category slug is unique across the catalogue, so a category that moved to another type (e.g. Venue from Hotels
    to Events) is updated in place rather than duplicated, and its partners follow it to the new type. Retired entries
    stay in the tables (partners may reference them) but are hidden from new partners.
    """
    for t_index, t in enumerate(TYPES):
        ptype, _ = PartnerType.objects.update_or_create(
            slug=t["slug"],
            defaults={
                "name": t["name"], "description": t["description"], "icon": t["icon"],
                "sort_order": t_index, "configuration": t["configuration"], "is_active": not t.get("retired", False),
            },
        )
        for c_index, c in enumerate(t["categories"]):
            values = {
                "partner_type": ptype, "name": c["name"], "description": c["description"], "icon": c.get("icon", ""),
                "sort_order": c_index, "configuration": c.get("configuration", {}), "is_active": not c.get("retired", False),
            }
            category = PartnerCategory.objects.filter(slug=c["slug"]).order_by("created_at").first()
            if category is None:
                category = PartnerCategory.objects.create(slug=c["slug"], **values)
            else:
                for k, v in values.items():
                    setattr(category, k, v)
                category.save()
            if Partner is not None:
                Partner.objects.filter(category=category).exclude(partner_type=ptype).update(partner_type=ptype)
