"""
Development seed for Click. Bookings (never loaded in production).

  information only   real, well-known temples and landmarks with brief, general descriptions; no prices, slots or
                     timings are claimed and Click. doesn't sell them (`official_source` says where they're booked)
  bookable           fictional providers (temples, museums, parks, tours, workshops) onboarded as Click. partners, with
                     ticket types, slots, capacity and policies in the same shape the real API returns
  history            completed visits by dev viewers with verified reviews (ratings are recomputed from them); the test
                     customer has one upcoming darshan, one past museum visit and one saved place
No images are seeded (no generated imagery); the UI shows a designed placeholder.
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import Decimal as D

from django.utils import timezone
from django.utils.text import slugify

ALL = [0, 1, 2, 3, 4, 5, 6]
WEEKEND = [5, 6]

INFO = [  # name, kind, city, region, area, lat, lng, deity, tagline, description, official source
    ("Sri Venkateswara Swamy Temple, Tirumala", "temple", "Tirupati", "Andhra Pradesh", "Tirumala hills", 13.6833, 79.3474, "Sri Venkateswara",
     "One of India’s most visited temples", "The hill shrine of Lord Venkateswara on the Tirumala hills above Tirupati.",
     "Darshan, sevas and accommodation are booked only through the temple trust’s (TTD) official channels."),
    ("Sri Kanaka Durga Temple", "temple", "Vijayawada", "Andhra Pradesh", "Indrakeeladri", 16.5175, 80.6047, "Goddess Kanaka Durga",
     "The hill temple above the Krishna", "The temple of Goddess Kanaka Durga on Indrakeeladri hill, overlooking the Krishna river.",
     "Darshan tickets and sevas are booked through the temple devasthanam’s official channels."),
    ("Birla Mandir", "temple", "Hyderabad", "Telangana", "Naubat Pahad", 17.4062, 78.469, "Sri Venkateswara",
     "White-marble temple with city views", "A white-marble temple on Naubat Pahad hill, with views over Hussain Sagar.",
     "Entry is at the temple; Click. doesn’t sell tickets for it."),
    ("Chilkur Balaji Temple", "temple", "Hyderabad", "Telangana", "Chilkur", 17.3563, 78.3017, "Sri Balaji",
     "Popularly called the ‘Visa Balaji’ temple", "A temple of Lord Balaji on the outskirts of Hyderabad near Osman Sagar.",
     "Visits are walk-in; there’s nothing to book through Click."),
    ("Sri Ranganathaswamy Temple, Srirangam", "temple", "Tiruchirappalli", "Tamil Nadu", "Srirangam", 10.8622, 78.6896, "Sri Ranganatha",
     "A vast temple complex on a river island", "A large temple complex dedicated to Lord Ranganatha on Srirangam island.",
     "Sevas and special darshan are arranged through the temple’s official channels."),
    ("Meenakshi Amman Temple", "temple", "Madurai", "Tamil Nadu", "Madurai city centre", 9.9195, 78.1193, "Goddess Meenakshi and Lord Sundareswarar",
     "Towering, sculpted gopurams", "A historic temple in the heart of Madurai known for its sculpted gateway towers.",
     "Special darshan is arranged through the temple’s official channels."),
    ("Simhachalam Temple", "temple", "Visakhapatnam", "Andhra Pradesh", "Simhachalam hill", 17.7665, 83.2508, "Sri Varaha Lakshmi Narasimha",
     "Hill temple near Visakhapatnam", "The temple of Sri Varaha Lakshmi Narasimha on Simhachalam hill.",
     "Darshan and sevas are booked through the temple devasthanam’s official channels."),
    ("Charminar", "monument", "Hyderabad", "Telangana", "Old City", 17.3616, 78.4747, "", "Hyderabad’s 16th-century landmark",
     "The four-minaret monument built in 1591 under Muhammad Quli Qutb Shah, at the heart of the Old City.",
     "Entry tickets are sold by the Archaeological Survey of India; Click. doesn’t sell them."),
    ("Golconda Fort", "fort", "Hyderabad", "Telangana", "Ibrahim Bagh", 17.3833, 78.4011, "", "The Qutb Shahi hill fort",
     "A hill fort and former capital of the Qutb Shahi dynasty, west of Hyderabad.", "Entry tickets are sold by the Archaeological Survey of India."),
    ("Salar Jung Museum", "museum", "Hyderabad", "Telangana", "Darulshifa", 17.3713, 78.4804, "", "One of India’s national museums",
     "A large collection of art and artefacts on the banks of the Musi river.", "Tickets are sold at the museum and on its official site."),
    ("Mysuru Palace", "palace", "Mysuru", "Karnataka", "Mysuru city centre", 12.3052, 76.6552, "", "The illuminated royal palace",
     "The royal palace of the Wadiyar dynasty in the centre of Mysuru.", "Entry tickets are sold at the palace and through its official channels."),
    ("Undavalli Caves", "heritage", "Vijayawada", "Andhra Pradesh", "Undavalli", 16.4964, 80.5807, "", "Rock-cut cave temples by the Krishna",
     "Rock-cut cave temples carved into a hillside on the south bank of the Krishna.", "Entry tickets are sold at the site."),
    ("Ramakrishna Beach", "beach", "Visakhapatnam", "Andhra Pradesh", "Beach Road", 17.7142, 83.3236, "", "Visakhapatnam’s city beach",
     "The long city beach along Beach Road in Visakhapatnam.", "Open public beach — nothing to book."),
    ("Gateway of India", "monument", "Mumbai", "Maharashtra", "Apollo Bunder", 18.922, 72.8347, "", "The arch on Mumbai’s waterfront",
     "The basalt arch on the Apollo Bunder waterfront, completed in 1924.", "Open public monument — nothing to book."),
    ("Nehru Zoological Park", "zoo", "Hyderabad", "Telangana", "Bahadurpura", 17.3507, 78.4513, "", "Hyderabad’s large city zoo",
     "A large zoological park near Mir Alam Tank.", "Tickets are sold at the zoo gates."),
    ("Lalbagh Botanical Garden", "garden", "Bengaluru", "Karnataka", "Lalbagh", 12.9507, 77.5848, "", "Historic gardens and glasshouse",
     "Historic botanical gardens in south Bengaluru, known for the glasshouse flower shows.", "Tickets are sold at the garden gates."),
]

# provider, name, kind, city, region, area, lat, lng, extras, offerings
BOOKABLE = [
    ("Sri Lakshmi Narasimha Devasthanam Trust", "Sri Lakshmi Narasimha Devasthanam, Kokapet", "temple", "Hyderabad", "Telangana", "Kokapet", 17.3921, 78.3376,
     dict(deity="Sri Lakshmi Narasimha", tagline="Darshan and sevas you can book ahead", accent="#b45309",
          description="A neighbourhood hill temple of Sri Lakshmi Narasimha. Book darshan slots and sevas ahead; free darshan needs a slot too, so queues stay short.",
          dress_code="Traditional attire is expected for darshan and sevas.", prohibited=["Mobile phones inside the sanctum", "Footwear beyond the shoe stand", "Leather items"],
          rules=["Reach 20 minutes before your slot.", "Carry the photo ID used for the booking.", "Prasadam counter closes at 8 PM."],
          facilities=["Shoe stand", "Drinking water", "Prasadam counter", "Wheelchair ramp", "Parking"], accessibility=["Wheelchair ramp to the main hall"],
          opening={"days": ALL, "open": "05:30", "close": "20:30", "note": "Closed 1–4 PM"}, duration_minutes=60, free_cancel_hours=12, cancel_fee_percent=100,
          faqs=[{"q": "Is free darshan really free?", "a": "Yes. You still choose a slot so the temple can manage the queue."},
                {"q": "Can I change my slot?", "a": "Cancel (free up to 12 hours before) and book a new slot."}]),
     "temple"),
    ("Sri Mahalakshmi Kshetram Trust", "Sri Mahalakshmi Kshetram, Patamata", "temple", "Vijayawada", "Andhra Pradesh", "Patamata", 16.4973, 80.6619,
     dict(deity="Goddess Mahalakshmi", tagline="Kumkumarchana and Friday special darshan", accent="#be185d",
          description="A temple of Goddess Mahalakshmi in Patamata. Friday evenings are busiest; book a slot to skip the general queue.",
          dress_code="Traditional attire is expected.", prohibited=["Photography inside the temple"], rules=["Reach 15 minutes before your slot."],
          facilities=["Shoe stand", "Drinking water", "Prasadam counter"], opening={"days": ALL, "open": "06:00", "close": "20:00"}, duration_minutes=45),
     "temple"),
    ("Sri Ganapathi Devasthanam Trust", "Sri Siddhi Vinayaka Devasthanam, Indiranagar", "temple", "Bengaluru", "Karnataka", "Indiranagar", 12.9784, 77.6408,
     dict(deity="Lord Ganesha", tagline="Morning abhishekam you can book", accent="#c2410c",
          description="A Ganesha temple in Indiranagar with daily abhishekam and evening aarti.", dress_code="Modest clothing, shoulders covered.",
          facilities=["Shoe stand", "Drinking water"], opening={"days": ALL, "open": "06:00", "close": "21:00"}, duration_minutes=40),
     "temple"),
    ("Sri Shiva Panchakshari Trust", "Sri Panchakshari Shiva Kshetram, Tirupati", "temple", "Tirupati", "Andhra Pradesh", "Renigunta Road", 13.6355, 79.4386,
     dict(deity="Lord Shiva", tagline="Rudrabhishekam and Monday special darshan", accent="#7c3aed",
          description="A Shiva temple on Renigunta Road in Tirupati town. (This is not the Tirumala hill temple.)",
          dress_code="Traditional attire is expected.", facilities=["Shoe stand", "Drinking water", "Parking"],
          opening={"days": ALL, "open": "05:30", "close": "20:00"}, duration_minutes=45), "temple"),
    ("Sri Murugan Devasthanam Trust", "Sri Subramanya Swamy Devasthanam, Velachery", "temple", "Chennai", "Tamil Nadu", "Velachery", 12.9815, 80.218,
     dict(deity="Lord Murugan", tagline="Shashti archana you can book", accent="#b91c1c", description="A Murugan temple in Velachery with daily archana and evening aarti.",
          dress_code="Traditional attire is expected.", facilities=["Shoe stand", "Drinking water"], opening={"days": ALL, "open": "06:00", "close": "20:30"},
          duration_minutes=40), "temple"),
    ("Deccan Heritage Foundation", "Deccan Heritage Museum", "museum", "Hyderabad", "Telangana", "Basheerbagh", 17.4011, 78.4772,
     dict(tagline="Coins, textiles and crafts of the Deccan", accent="#0f766e", setting="indoor", family_friendly=True,
          description="Five galleries of Deccan coins, textiles, arms and crafts, with an audio guide on your phone.",
          highlights=["Bidriware gallery", "Kalamkari textiles", "Qutb Shahi coin room"], facilities=["Cloakroom", "Café", "Lift", "Wheelchairs on request"],
          accessibility=["Step-free entrance", "Lift to all floors", "Accessible toilets"], rules=["Bags larger than 30 × 20 cm go to the cloakroom."],
          prohibited=["Flash photography", "Food inside galleries"], opening={"days": [0, 1, 2, 3, 5, 6], "open": "10:00", "close": "17:00", "note": "Closed on Fridays"},
          duration_minutes=120, free_cancel_hours=24, cancel_fee_percent=100), "museum"),
    ("Stellar Science Trust", "Stellar Science Centre & Planetarium", "planetarium", "Bengaluru", "Karnataka", "Sankey Road", 12.9906, 77.5773,
     dict(tagline="Hands-on science and dome shows", accent="#4338ca", setting="indoor", family_friendly=True, kids_friendly=True,
          description="Interactive science halls and a full-dome planetarium. Shows run at fixed times; entry is valid all day.",
          facilities=["Cloakroom", "Café", "Lift"], accessibility=["Step-free entrance", "Lift"], opening={"days": [1, 2, 3, 4, 5, 6], "open": "10:00", "close": "18:00", "note": "Closed on Mondays"},
          duration_minutes=180, age_note="Shows suit ages 5+."), "planetarium"),
    ("Bay City Science Society", "Bay City Science Centre", "science_centre", "Visakhapatnam", "Andhra Pradesh", "Beach Road", 17.7235, 83.3381,
     dict(tagline="Ocean and space galleries by the beach", accent="#0369a1", setting="indoor", family_friendly=True, kids_friendly=True,
          description="Ocean science, ships and space galleries on Beach Road.", facilities=["Café", "Lift"], opening={"days": [1, 2, 3, 4, 5, 6], "open": "10:00", "close": "18:00"},
          duration_minutes=150), "museum"),
    ("Riverfront Arts Collective", "Krishna Riverfront Art Gallery", "gallery", "Vijayawada", "Andhra Pradesh", "Bhavanipuram", 16.5329, 80.5923,
     dict(tagline="Contemporary Andhra art by the river", accent="#9333ea", setting="indoor", description="Rotating exhibitions of contemporary art from Andhra Pradesh.",
          facilities=["Café", "Gift shop"], opening={"days": [1, 2, 3, 4, 5, 6], "open": "11:00", "close": "19:00"}, duration_minutes=90), "museum"),
    ("Aqua Bay Leisure Pvt Ltd", "Aqua Bay Water Park", "water_park", "Hyderabad", "Telangana", "Shamshabad", 17.2543, 78.3995,
     dict(tagline="Wave pool, lazy river and 18 slides", accent="#0891b2", family_friendly=True, kids_friendly=True,
          description="A full-day water park with a wave pool, a lazy river, a kids’ splash zone and 18 slides.",
          highlights=["Wave pool", "Lazy river", "Kids’ splash zone", "18 slides"], facilities=["Lockers", "Changing rooms", "Food court", "First aid", "Parking"],
          accessibility=["Accessible changing room", "Wheelchair-friendly paths (dry areas)"],
          rules=["Nylon / swimwear only in pools.", "Children under 130 cm must be with an adult."], prohibited=["Outside food", "Glass bottles"],
          age_note="Child tickets: 90–130 cm. Under 90 cm enter free.", opening={"days": ALL, "open": "10:30", "close": "18:00"}, duration_minutes=360,
          free_cancel_hours=24, cancel_fee_percent=50), "water_park"),
    ("Thrill Valley Parks", "Thrill Valley Theme Park", "theme_park", "Bengaluru", "Karnataka", "Bidadi", 12.8008, 77.3893,
     dict(tagline="Coasters, dark rides and a 4D theatre", accent="#db2777", family_friendly=True, kids_friendly=True,
          description="A theme park with roller coasters, family rides, a 4D theatre and live shows.", facilities=["Lockers", "Food court", "First aid", "Parking"],
          rules=["Height limits apply on some rides."], prohibited=["Outside food"], opening={"days": ALL, "open": "11:00", "close": "19:00"}, duration_minutes=420,
          free_cancel_hours=48, cancel_fee_percent=50), "water_park"),
    ("Coral Cove Aquaria", "Coral Cove Aquarium", "aquarium", "Chennai", "Tamil Nadu", "ECR, Neelankarai", 12.9496, 80.2581,
     dict(tagline="A walk-through ocean tunnel", accent="#0e7490", setting="indoor", family_friendly=True, kids_friendly=True,
          description="Timed-entry aquarium with a walk-through tunnel, reef tanks and a touch pool.", facilities=["Café", "Cloakroom", "Lift"],
          accessibility=["Step-free throughout"], opening={"days": ALL, "open": "10:00", "close": "20:00"}, duration_minutes=90), "aquarium"),
    ("Green Canopy Adventures", "Green Canopy Adventure Park", "adventure_park", "Hyderabad", "Telangana", "Gandipet", 17.3802, 78.3134,
     dict(tagline="Zipline, sky cycling and rope courses", accent="#15803d", family_friendly=True,
          description="Outdoor adventure park with a 300 m zipline, sky cycling and high and low rope courses.", facilities=["Lockers", "Café", "First aid", "Parking"],
          rules=["Closed shoes required.", "Weight limit 110 kg on the zipline."], age_note="Minimum age 10 for the combo.",
          opening={"days": ALL, "open": "09:00", "close": "18:00"}, duration_minutes=150), "adventure"),
    ("Krishna Hills Ropeways", "Krishna Hills Ropeway", "ropeway", "Vijayawada", "Andhra Pradesh", "Gunadala hill", 16.5226, 80.6627,
     dict(tagline="A cable-car ride over the city", accent="#0d9488", family_friendly=True, kids_friendly=True,
          description="A short cable-car ride up Gunadala hill with views across Vijayawada.", opening={"days": ALL, "open": "09:00", "close": "19:00"},
          duration_minutes=40), "ropeway"),
    ("Deccan Trails", "Old City Heritage Walk", "walking_tour", "Hyderabad", "Telangana", "Old City", 17.3616, 78.4747,
     dict(tagline="Charminar to Chowmahalla on foot, with breakfast", accent="#a16207",
          description="A 2.5-hour guided walk through the Old City’s bazaars and monuments, ending with Irani chai and breakfast. Monument entry fees are paid on the day.",
          highlights=["Laad Bazaar", "Mecca Masjid exterior", "Irani chai and breakfast"], rules=["Comfortable shoes; it’s about 3 km."],
          free_cancel_hours=24, cancel_fee_percent=100, duration_minutes=150), "walk"),
    ("Lakeside Cruises", "Hussain Sagar Sunset Boat Ride", "boat_ride", "Hyderabad", "Telangana", "Lumbini Park jetty", 17.4103, 78.4719,
     dict(tagline="45 minutes around the Buddha statue", accent="#0284c7", family_friendly=True, kids_friendly=True,
          description="A 45-minute ride on Hussain Sagar around the Buddha statue at sunset. Life jackets provided.",
          rules=["Board 10 minutes before departure.", "Life jackets are mandatory."], duration_minutes=45), "boat"),
    ("Deccan Trails", "Hyderabad City Highlights Tour", "city_tour", "Hyderabad", "Telangana", "City-wide", 17.385, 78.4867,
     dict(tagline="A full day: fort, museum, lake, with pickup", accent="#b45309", family_friendly=True,
          description="An air-conditioned coach tour with a guide: Golconda Fort, Salar Jung Museum (exterior), Charminar and Hussain Sagar. Monument entry fees are paid on the day.",
          free_cancel_hours=24, cancel_fee_percent=100, duration_minutes=540), "city_tour"),
    ("Krishna River Cruises", "Krishna River Sunset Cruise", "cruise", "Vijayawada", "Andhra Pradesh", "Bhavani Island jetty", 16.5302, 80.5872,
     dict(tagline="Sunset on the Krishna with dinner", accent="#0f766e", family_friendly=True, description="A 2-hour evening cruise on the Krishna with live music and a buffet dinner.",
          duration_minutes=120), "cruise"),
    ("Clay & Kiln Studio", "Pottery Workshop at Clay & Kiln", "workshop", "Bengaluru", "Karnataka", "Jayanagar", 12.925, 77.5938,
     dict(tagline="Throw your first pot on the wheel", accent="#9a3412", setting="indoor", description="A 2-hour beginner wheel-throwing session. Your pot is fired and ready to collect in 2 weeks.",
          age_note="Ages 8+; under 14 with an adult.", duration_minutes=120, free_cancel_hours=48, cancel_fee_percent=100), "workshop"),
    ("Pedal Out Adventures", "Nandi Hills Sunrise Cycling", "adventure", "Bengaluru", "Karnataka", "Nandi Hills", 13.3702, 77.6835,
     dict(tagline="Sunrise ride with pickup and breakfast", accent="#16a34a", description="Pickup at 4 AM, a guided 25 km ride around Nandi Hills at sunrise, and breakfast. Bikes and helmets included.",
          age_note="Ages 14+, comfortable on a bicycle.", duration_minutes=360), "cycling"),
    ("Mandovi Waterways", "Mandovi Evening Cruise", "cruise", "Goa", "Goa", "Panaji jetty", 15.4989, 73.8278,
     dict(tagline="Folk dance on the river at dusk", accent="#0369a1", family_friendly=True, description="A one-hour evening cruise on the Mandovi with Goan folk performances.",
          duration_minutes=60), "cruise"),
    ("Goa Food Trails", "Goan Food Trail, Fontainhas", "food", "Goa", "Goa", "Fontainhas, Panaji", 15.4986, 73.8336,
     dict(tagline="Six tastings in the Latin Quarter", accent="#ca8a04", description="A 3-hour evening walk through Fontainhas with six tastings of Goan dishes.",
          rules=["Tell us about allergies when you book."], duration_minutes=180), "food"),
    ("Coastal Paddlers", "Rushikonda Kayak & Snorkel", "adventure", "Visakhapatnam", "Andhra Pradesh", "Rushikonda", 17.7826, 83.3851,
     dict(tagline="Sea kayaking and a guided snorkel", accent="#0e7490", description="A guided 2-hour session: sea kayaking and a shallow-reef snorkel, with safety briefing and gear.",
          age_note="Ages 12+, swimming not required (life jackets).", duration_minutes=120, free_cancel_hours=24, cancel_fee_percent=50), "kayak"),
    ("Madras Walks Collective", "Mylapore Heritage & Food Walk", "walking_tour", "Chennai", "Tamil Nadu", "Mylapore", 13.0339, 80.2697,
     dict(tagline="Temple streets, filter coffee and tiffin", accent="#b45309", description="A morning walk through Mylapore’s temple streets and markets, ending with filter coffee and tiffin.",
          duration_minutes=150), "walk"),
    ("Temple Town Tours", "Tirupati Temple Town Day Tour", "tour", "Tirupati", "Andhra Pradesh", "Tirupati", 13.6288, 79.4192,
     dict(tagline="Local temples by AC car, with pickup", accent="#a16207", family_friendly=True,
          description="An air-conditioned car tour of temples in and around Tirupati town with a driver-guide. Tirumala darshan is not included (book it with TTD).",
          duration_minutes=420), "city_tour"),
]


def _prices(*rows):
    return [{"visitor": v, "label": lbl, "note": note, "amount": D(str(a)), "units": u} for v, lbl, note, a, u in rows]


ADULT_CHILD = lambda a, c, note="5–12 years": _prices(("adult", "Adult", "", a, 1), ("child", "Child", note, c, 1))  # noqa: E731

OFFERINGS = {  # template → [(kind, model, name, description, slots, days, capacity, max, min_age, pickup, requirements, tax, prices, includes, duration)]
    "temple": [
        ("darshan", "slot", "Sarva darshan (free)", "General darshan with a time slot.", ["06:00", "08:00", "10:00", "16:00", "18:00"], ALL, 200, 6, None, [],
         "Photo ID of each devotee at entry.", 0, _prices(("devotee", "Devotee", "", 0, 1)), [], 45),
        ("darshan", "slot", "Special entry darshan", "Separate queue with a shorter wait.", ["06:30", "09:00", "11:00", "17:00", "19:00"], ALL, 60, 6, None, [],
         "Photo ID of each devotee at entry.", 0, _prices(("devotee", "Devotee", "", 150, 1)), ["Laddu prasadam (1 per devotee)"], 30),
        ("seva", "slot", "Abhishekam", "Morning abhishekam; up to 2 people per ticket.", ["05:30"], ALL, 20, 4, None, [], "Traditional attire is required for sevas.",
         0, _prices(("devotee", "Seva ticket (up to 2 people)", "", 500, 1)), ["Prasadam", "Kumkum and flowers"], 60),
        ("pooja", "ticket", "Archana", "Archana in your name, any time the temple is open.", [], ALL, 300, 4, None, [], "", 0,
         _prices(("devotee", "Archana", "", 50, 1)), [], 15),
    ],
    "museum": [
        ("entry", "ticket", "Entry ticket", "Valid all day; includes the audio guide.", [], None, 800, 10, None, [], "Student ID for student tickets.", 0,
         _prices(("adult", "Adult", "", 60, 1), ("child", "Child", "5–12 years", 25, 1), ("student", "Student", "With ID", 30, 1), ("senior", "Senior", "60+", 30, 1)),
         ["Audio guide"], 120),
    ],
    "planetarium": [
        ("entry", "ticket", "Science halls entry", "Valid all day.", [], None, 900, 10, None, [], "", 0, ADULT_CHILD(80, 40, "3–12 years"), [], 120),
        ("entry", "slot", "Planetarium dome show", "35-minute full-dome show; arrive 10 minutes early.", ["11:00", "13:00", "15:00", "17:00"], None, 120, 10, 5, [], "",
         18, ADULT_CHILD(120, 70, "5–12 years"), [], 35),
    ],
    "water_park": [
        ("entry", "ticket", "Day pass", "Full day, all rides and pools.", [], ALL, 1500, 10, None, [], "Child tickets need the child’s height checked at entry.", 18,
         _prices(("adult", "Adult", "Above 130 cm", 1199, 1), ("child", "Child", "90–130 cm", 899, 1), ("senior", "Senior", "60+", 699, 1),
                 ("family", "Family (2 adults + 2 children)", "", 3799, 4)), ["Locker key (deposit at entry)"], 360),
    ],
    "aquarium": [
        ("entry", "slot", "Timed entry", "Enter within your hour; stay as long as you like.", ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
         ALL, 80, 10, None, [], "", 18, ADULT_CHILD(450, 300, "3–12 years"), [], 90),
    ],
    "adventure": [
        ("activity", "slot", "Zipline + sky cycle combo", "Briefing, harness, one zipline run and a sky-cycle loop.", ["09:30", "11:00", "12:30", "14:30", "16:00"], ALL, 24, 6, 10, [],
         "Closed shoes; weight limit 110 kg.", 18, _prices(("participant", "Participant", "Ages 10+", 799, 1)), ["Safety gear", "Instructor"], 90),
        ("activity", "slot", "Rope course", "High and low rope course with an instructor.", ["10:00", "13:00", "15:30"], ALL, 16, 6, 8, [], "Closed shoes.", 18,
         _prices(("participant", "Participant", "Ages 8+", 599, 1)), ["Safety gear", "Instructor"], 60),
    ],
    "ropeway": [
        ("entry", "ticket", "Return ride", "Up and down, any time that day.", [], ALL, 600, 10, None, [], "", 18, ADULT_CHILD(150, 80, "3–12 years"), [], 40),
    ],
    "walk": [
        ("tour", "slot", "Morning walk", "Meet at the start point; small group.", ["07:00"], WEEKEND, 15, 6, None, [], "", 5,
         _prices(("participant", "Participant", "", 899, 1)), ["Guide", "Breakfast", "Water"], 150),
    ],
    "boat": [
        ("activity", "slot", "Sunset ride", "45 minutes on the lake.", ["16:30", "17:30", "18:30"], ALL, 40, 10, None, [], "", 5, ADULT_CHILD(350, 200, "3–12 years"),
         ["Life jacket"], 45),
    ],
    "city_tour": [
        ("tour", "slot", "Full-day tour", "Coach with a guide; pickup from your chosen point.", ["08:30"], ALL, 30, 8, None,
         ["Hotel pickup — central area", "Metro station (main)", "Railway station"], "Entry fees at monuments are paid on the day.", 5,
         ADULT_CHILD(1499, 999, "5–12 years"), ["AC transport", "Guide", "Water"], 540),
    ],
    "cruise": [
        ("activity", "slot", "Evening cruise", "Board 15 minutes before departure.", ["18:00", "19:30"], ALL, 60, 10, None, [], "", 5, ADULT_CHILD(1200, 800, "5–12 years"),
         ["Live music", "Dinner / snacks as listed"], 90),
    ],
    "workshop": [
        ("activity", "slot", "Beginner wheel session", "All materials; one fired pot to take home.", ["11:00", "15:00"], WEEKEND, 12, 4, 8, [], "", 18,
         _prices(("participant", "Participant", "Ages 8+", 1800, 1)), ["Clay and tools", "Firing and glazing"], 120),
    ],
    "cycling": [
        ("activity", "slot", "Sunrise ride", "Pickup at 4 AM from your chosen point.", ["04:00"], WEEKEND, 20, 4, 14, ["Hebbal flyover", "Yelahanka", "MG Road Metro"], "", 5,
         _prices(("participant", "Rider", "Ages 14+", 1899, 1)), ["Bike and helmet", "Breakfast", "Support vehicle"], 360),
    ],
    "food": [
        ("tour", "slot", "Evening trail", "Small-group walk with six tastings.", ["18:30"], [1, 2, 3, 4, 5, 6], 12, 6, None, [], "", 5,
         _prices(("participant", "Participant", "", 1500, 1)), ["Six tastings", "Guide"], 180),
    ],
    "kayak": [
        ("activity", "slot", "Kayak & snorkel session", "Safety briefing, kayaking and snorkel.", ["07:00", "09:00", "15:30"], ALL, 12, 4, 12, [], "", 18,
         _prices(("participant", "Participant", "Ages 12+", 1499, 1)), ["Kayak and paddle", "Snorkel gear", "Life jacket", "Instructor"], 120),
    ],
}


def _provider(name, category_slug, city, now):
    from apps.partners.models import Partner, PartnerCategory, PartnerMembership, PartnerProfile
    from apps.users.models import User

    from .partners import _code

    email = f"exp.{slugify(name)[:40]}@click.local"
    user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=name, phone_verified=False)
    m = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
    category = PartnerCategory.objects.select_related("partner_type").get(slug=category_slug)
    partner = m.partner if m else Partner.objects.create(partner_type=category.partner_type, category=category, business_name=name)
    if not m:
        PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    partner.partner_code = partner.partner_code or _code()
    partner.status = Partner.Status.ACTIVE
    partner.is_available = True
    partner.profile_completed_at = partner.profile_completed_at or now
    partner.save()
    PartnerProfile.objects.update_or_create(partner=partner, defaults={"contact_name": name, "details": {"city": city}})
    return partner


def seed_experiences(log) -> None:
    from apps.experiences.models import Attraction, Closure, ExperienceOffer, Offering, Price

    now = timezone.now()
    for name, kind, city, region, area, lat, lng, deity, tagline, desc, source in INFO:
        Attraction.objects.update_or_create(slug=slugify(name)[:140], defaults=dict(
            name=name, kind=kind, city=city, region=region, area=area, latitude=lat, longitude=lng, deity=deity, tagline=tagline, description=desc,
            official_source=source, bookable=False, provider=None, is_listed=True, setting="outdoor",
            family_friendly=kind in ("zoo", "garden", "beach"), kids_friendly=kind in ("zoo", "garden"), accent="#57534e"))
    made = 0
    for prov, name, kind, city, region, area, lat, lng, extras, template in BOOKABLE:
        cat = "activity-provider" if kind in ("walking_tour", "boat_ride", "city_tour", "cruise", "workshop", "adventure", "food", "tour") else "ticketing-venue"
        partner = _provider(prov, cat, city, now)
        a, _ = Attraction.objects.update_or_create(slug=slugify(name)[:140], defaults=dict(
            name=name, kind=kind, city=city, region=region, area=area, latitude=lat, longitude=lng, address=f"{area}, {city}, {region}", provider=partner,
            bookable=True, verified_provider=True, instant_confirmation=True, is_listed=True, refundable=True, official_source="",
            **{"free_cancel_hours": 24, "cancel_fee_percent": 100, **extras}))
        keep = []
        for pos, (okind, model, oname, odesc, slots, days, cap, mx, min_age, pickup, req, tax, prices, includes, dur) in enumerate(OFFERINGS[template]):
            o, _ = Offering.objects.update_or_create(attraction=a, name=oname, defaults=dict(
                kind=okind, booking_model=model, description=odesc, slot_times=slots, days=days if days is not None else (a.opening or {}).get("days", ALL),
                capacity=cap, max_per_booking=mx, min_age=min_age, pickup_points=pickup, requirements=req, tax_percent=D(str(tax)), includes=includes,
                duration_minutes=dur, position=pos, is_active=True, book_ahead_days=30))
            keep.append(o.id)
            vis = []
            for i, p in enumerate(prices):
                Price.objects.update_or_create(offering=o, visitor=p["visitor"], defaults={**{k: v for k, v in p.items() if k != "visitor"}, "position": i})
                vis.append(p["visitor"])
            o.prices.exclude(visitor__in=vis).delete()
        a.offerings.exclude(id__in=keep).update(is_active=False)
        made += 1
    if (park := Attraction.objects.filter(slug="aqua-bay-water-park").first()):
        from apps.experiences.booking import today

        Closure.objects.update_or_create(attraction=park, date=today() + timedelta(days=9), defaults={"reason": "Closed for annual maintenance"})
    for title, group, code, pct, cap, minimum in [("Weekend family fun: 10% off parks, up to ₹500", "parks", "", 10, D("500"), D("2000")),
                                                  ("EXPLORE15: 15% off experiences, up to ₹300", "experiences", "EXPLORE15", 15, D("300"), D("800"))]:
        ExperienceOffer.objects.update_or_create(title=title, defaults=dict(group=group, code=code, percent=pct, max_discount=cap, min_amount=minimum,
                                                                           starts_at=now - timedelta(days=5), ends_at=now + timedelta(days=120), is_active=True))
    log(f"bookings: {len(INFO)} real places (information only, no prices or slots), {made} fictional bookable providers with "
        f"{Offering.objects.filter(is_active=True).count()} offerings; 2 offers (no images)")


NS = uuid.UUID("2b7c9d3e-6f1a-4b8c-9e2d-3f4a5b6c7d8e")
REVIEWS = ["Well organised, short queue.", "Staff were helpful and the timing was exact.", "Great for the kids.", "Worth it — book the early slot.",
           "Good, though it got crowded later.", "Lovely experience, would do it again."]


def _visit(customer, o, days, key, status="completed", review=None, qty=None):
    from apps.experiences import booking
    from apps.experiences.models import ExperienceBooking, ExperienceReview, StatusEvent, entry_code
    from apps.payments.models import Payment

    if ExperienceBooking.objects.filter(customer=customer, idempotency_key=str(key)).exists():
        return 0
    d = booking.today() + timedelta(days=days)
    slot = time(*map(int, o.slot_times[0].split(":"))) if o.slot_times else None
    q = booking.quote(o, qty or {o.prices.first().visitor: 2})
    a = o.attraction
    b = ExperienceBooking.objects.create(
        customer=customer, attraction=a, offering=o, visit_date=d, slot_time=slot, lines=q.lines, visitors=q.visitors, units=q.units,
        lead_name=customer.user.full_name.split(" (")[0] or "Guest", lead_phone="+91 90000 00000", status=status,
        payment_status="free" if q.total == 0 else "paid", title=f"{o.name} · {a.name}", refundable=a.refundable,
        free_cancel_until=booking.free_cancel_until(a, booking.starts_at(d, slot, a)) if days > 0 else None, cancel_fee_percent=a.cancel_fee_percent,
        subtotal=q.subtotal, discount=q.discount, tax=q.tax, total=q.total, idempotency_key=str(key), entry_code=entry_code(),
        confirmed_at=timezone.now() - timedelta(days=max(1, -days + 3)),
        checked_in_at=timezone.now() + timedelta(days=days) if status == "completed" else None)
    if q.total:
        Payment.objects.create(experience_booking=b, method="wallet", amount=b.total, currency=b.currency, status=Payment.Status.CAPTURED)
    for st in (["pending_payment", "confirmed"] + (["completed"] if status == "completed" else [])):
        StatusEvent.objects.create(booking=b, to=st, note="Development seed")
    if review:
        ExperienceReview.objects.create(booking=b, customer=customer, attraction=a, rating=review[0], comment=review[1])
    return 1


def seed_experience_history(profile, log) -> None:
    from django.db.models import Avg, Count

    from apps.experiences.models import Attraction, ExperienceReview, Offering
    from apps.wishlists.models import WishlistItem

    from .showtime import VIEWERS, _viewer

    bookable = list(Attraction.objects.filter(bookable=True).order_by("name"))
    if not bookable:
        return
    viewers = [_viewer(n, loc) for n, loc in VIEWERS]
    made = 0
    for k, a in enumerate(bookable):
        o = a.offerings.filter(is_active=True).order_by("position").first()
        for i in range(2 + (k * 5) % 5):  # 2..6 past visits each
            v = viewers[(k + i) % len(viewers)]
            score = max(2, min(5, [5, 4, 5, 4, 3, 5][(k + i) % 6] - (1 if k % 4 == 3 and i % 2 else 0)))
            made += _visit(v, o, -(3 + i * 6 + k % 5), uuid.uuid5(NS, f"{a.slug}-{i}"), review=(score, REVIEWS[(k + i) % len(REVIEWS)]) if i % 3 != 2 else None)
    for a in bookable:
        agg = ExperienceReview.objects.filter(attraction=a, is_published=True).aggregate(m=Avg("rating"), n=Count("id"))
        Attraction.objects.filter(pk=a.pk).update(rating_average=D(str(round(agg["m"] or 0, 1))), rating_count=agg["n"])
    darshan = Offering.objects.filter(attraction__slug="sri-lakshmi-narasimha-devasthanam-kokapet", name="Special entry darshan").first()
    if darshan:
        made += _visit(profile, darshan, 4, uuid.uuid5(NS, "test-upcoming-darshan"), "confirmed", qty={"devotee": 2})
    museum = Offering.objects.filter(attraction__slug="deccan-heritage-museum").first()
    if museum:
        made += _visit(profile, museum, -10, uuid.uuid5(NS, "test-past-museum"), "completed", qty={"adult": 2, "child": 1})
    if (park := Attraction.objects.filter(slug="aqua-bay-water-park").first()):
        WishlistItem.objects.get_or_create(customer=profile, attraction=park)
    log(f"bookings history: {made} visits (dev viewers’ reviewed visits; the test customer has 1 upcoming darshan, 1 past museum visit, 1 saved place)")
