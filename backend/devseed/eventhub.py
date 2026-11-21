"""
DEVELOPMENT MOCK DATA: Click. Events registries, event teams, specialists and venues (all businesses fictional, Bengaluru).

* Event types and services are configuration Click operations would manage in the admin / Business OS.
* Providers are Partners in event categories (Event Planner, Decorator, Photographer, DJ / Entertainer, Makeup, Catering,
  Venue) with a Click. Events profile, service area, packages and terms. They have NO logos, covers or portfolio photos:
  the app shows a monogram until a provider uploads their own (no generated or borrowed images, no invented past work).
* Ratings and "events completed" are never typed in: `seed_event_history` creates completed bookings with reviews from
  the dev viewers and the test customer, and they are recomputed from those.
* "Available on a date" comes from the blocked dates below and real bookings — nothing else.
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import Decimal as D

from django.utils import timezone

from apps.partners.models import (
    Partner, PartnerAddress, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerProfile, PartnerVerification,
)
from apps.users.models import User

from . import locality_point
from .professionals import _code

# slug, name, group, icon, accent, summary, synonyms, suggested services, in planner
TYPES = [
    ("birthday", "Birthday", "personal", "cake", "#f472b6", "Kids’ and grown-up birthdays", ["bday", "birthday party", "turning"], ["decoration", "cake", "photography", "entertainment", "catering"], True),
    ("wedding", "Wedding", "wedding", "heart", "#f59e0b", "Ceremony, reception and everything around it", ["marriage", "shaadi", "reception", "sangeet"], ["planning", "venue", "decoration", "catering", "photography", "videography", "makeup", "dj"], True),
    ("engagement", "Engagement", "wedding", "gem", "#fb7185", "Ring ceremonies and roka", ["ring ceremony", "roka", "sagai"], ["venue", "decoration", "catering", "photography", "makeup"], True),
    ("anniversary", "Anniversary", "personal", "heart", "#e879f9", "Milestone anniversaries and vow renewals", ["wedding anniversary", "silver jubilee"], ["decoration", "catering", "photography", "music"], True),
    ("baby-shower", "Baby Shower", "personal", "baby", "#a78bfa", "Godh bharai and baby showers", ["godh bharai", "seemantham", "valaikappu"], ["decoration", "catering", "photography"], True),
    ("naming", "Naming Ceremony", "personal", "baby", "#c4b5fd", "Naamkaran and cradle ceremonies", ["naamkaran", "cradle ceremony", "namakarana"], ["decoration", "catering", "photography"], False),
    ("housewarming", "Housewarming", "personal", "home", "#fbbf24", "Griha pravesh and new-home parties", ["griha pravesh", "gruhapravesha", "new home"], ["decoration", "catering", "photography"], False),
    ("graduation", "Graduation Party", "personal", "book", "#60a5fa", "Celebrate the degree", ["convocation party"], ["decoration", "catering", "dj"], False),
    ("school", "School Event", "work", "book", "#34d399", "Annual days, sports days and fairs", ["annual day", "sports day", "school function"], ["stage", "sound", "lighting", "host", "photography"], False),
    ("college", "College Event", "work", "book", "#22d3ee", "Fests, freshers and farewells", ["fest", "freshers", "college fest"], ["stage", "sound", "lighting", "dj", "security"], True),
    ("corporate", "Corporate Event", "work", "briefcase", "#818cf8", "Offsites, town halls and parties", ["office party", "offsite", "team outing", "town hall", "company"], ["planning", "venue", "catering", "sound", "host", "photography"], True),
    ("conference", "Conference", "work", "briefcase", "#6366f1", "Conferences and summits", ["summit", "convention"], ["venue", "sound", "lighting", "stage", "catering", "staff"], False),
    ("seminar", "Seminar", "work", "book", "#7dd3fc", "Talks and seminars", ["talk", "lecture"], ["venue", "sound", "catering"], False),
    ("workshop", "Workshop", "work", "book", "#38bdf8", "Hands-on workshops and classes", ["masterclass", "training"], ["venue", "sound", "catering"], False),
    ("product-launch", "Product Launch", "work", "sparkle", "#f97316", "Launches and press events", ["launch event", "press event", "unveiling"], ["planning", "stage", "lighting", "sound", "host", "photography", "videography"], False),
    ("exhibition", "Exhibition", "community", "store", "#14b8a6", "Exhibitions and trade shows", ["expo", "trade show", "stall"], ["stage", "lighting", "security", "staff"], False),
    ("cultural", "Cultural Event", "community", "star", "#eab308", "Performances and cultural evenings", ["cultural programme", "dance show"], ["stage", "sound", "lighting", "host"], False),
    ("festival", "Festival Celebration", "community", "sparkle", "#f43f5e", "Diwali, Ganesha, Christmas and more", ["diwali party", "ganesh", "christmas party", "holi", "pongal"], ["decoration", "catering", "dj", "lighting"], False),
    ("religious", "Pooja & Religious Function", "community", "sparkle", "#f59e0b", "Poojas, homas and religious functions", ["pooja", "puja", "homa", "satyanarayan"], ["decoration", "catering"], False),
    ("private-party", "Private Party", "personal", "gift", "#c084fc", "House parties and get-togethers", ["house party", "get together", "party"], ["catering", "dj", "decoration"], True),
    ("surprise", "Surprise Party", "personal", "gift", "#f472b6", "Surprises, proposals and reveals", ["surprise", "proposal", "gender reveal"], ["decoration", "photography", "cake"], False),
    ("farewell", "Farewell Party", "personal", "gift", "#a3e635", "Send-offs and retirement parties", ["send off", "retirement"], ["catering", "decoration", "dj"], False),
    ("reunion", "Reunion", "personal", "team", "#4ade80", "School, college and family reunions", ["alumni meet", "get-together"], ["venue", "catering", "dj", "photography"], False),
    ("photo-shoot", "Photo / Video Shoot", "other", "camera", "#94a3b8", "Pre-wedding, maternity and portfolio shoots", ["pre wedding", "maternity shoot", "photoshoot"], ["photography", "videography", "makeup"], False),
    ("other", "Other Event", "other", "plus", "#a1a1aa", "Tell us what you’re planning", [], ["planning"], True),
]

# slug, name, group, icon, synonyms
SERVICES = [
    ("planning", "Event Planning", "planning", "sparkle", ["planner", "event planner", "coordination", "event management", "organiser"]),
    ("venue", "Venue", "venue", "hotel", ["hall", "banquet", "party hall", "lawn", "venue"]),
    ("decoration", "Decoration", "decor", "gift", ["decor", "decorator", "balloon", "flowers", "theme", "backdrop"]),
    ("catering", "Catering", "food", "food", ["caterer", "food", "buffet", "menu"]),
    ("cake", "Cake & Desserts", "food", "cake", ["cake", "desserts", "dessert table"]),
    ("photography", "Photography", "media", "camera", ["photographer", "photos", "candid"]),
    ("videography", "Videography", "media", "film", ["videographer", "video", "cinematic", "drone"]),
    ("dj", "DJ", "entertainment", "headphones", ["dj", "disc jockey"]),
    ("music", "Live Music", "entertainment", "play", ["band", "singer", "live band", "musician"]),
    ("sound", "Sound", "decor", "mic", ["sound system", "speakers", "pa system", "audio"]),
    ("lighting", "Lighting", "decor", "sparkle", ["lights", "fairy lights", "led"]),
    ("stage", "Stage Setup", "decor", "store", ["stage", "truss", "led wall", "setup"]),
    ("makeup", "Makeup", "beauty", "beauty", ["makeup artist", "bridal makeup", "hair"]),
    ("mehendi", "Mehendi", "beauty", "beauty", ["mehndi", "henna"]),
    ("host", "Host / Anchor", "entertainment", "mic", ["anchor", "emcee", "mc", "host"]),
    ("entertainment", "Entertainment", "entertainment", "star", ["magician", "games", "kids entertainment", "puppet", "clown"]),
    ("invitations", "Invitations", "decor", "send", ["invites", "invitation cards", "e-invite"]),
    ("security", "Security", "logistics", "shield", ["bouncers", "guards"]),
    ("transport", "Guest Transport", "logistics", "car", ["transport", "cars", "shuttle", "bus"]),
    ("cleaning", "Cleaning", "logistics", "spray", ["cleanup", "housekeeping"]),
    ("staff", "Event Staff", "logistics", "team", ["staff", "waiters", "ushers", "hostesses"]),
]

CHECKLIST = [("venue", "Choose the venue", "venue"), ("planner", "Pick your event team", "planning"), ("decor", "Confirm decoration", "decoration"),
             ("food", "Confirm catering and menu", "catering"), ("cake", "Order the cake", "cake"), ("photo", "Confirm photography", "photography"),
             ("video", "Confirm videography", "videography"), ("music", "Book music / DJ", "dj"), ("band", "Book live music", "music"),
             ("sound", "Confirm sound", "sound"), ("lights", "Confirm lighting", "lighting"), ("stage", "Confirm the stage setup", "stage"),
             ("fun", "Plan entertainment", "entertainment"), ("makeup", "Book makeup", "makeup"), ("mehendi", "Book mehendi", "mehendi"),
             ("host", "Book the host", "host"), ("invites", "Send invitations", "invitations"), ("security", "Arrange security", "security"),
             ("ride", "Arrange guest transport", "transport"), ("clean", "Arrange the clean-up", "cleaning"), ("staff", "Confirm event staff", "staff")]


def _faq(cancel_days):
    return [{"q": "Do you need an advance?", "a": "Bookings on Click. are paid through the Click. Wallet when you confirm (or before the pay-by date)."},
            {"q": "Can I change the guest count later?", "a": "Yes — message us from your plan. Big changes may need a revised quote."},
            {"q": "What is your cancellation policy?", "a": f"Free until {cancel_days} days before the event; after that part of the amount is kept, as shown at booking."}]


# name, kind, partner category, area, radius, years, team, services, event types, guests (min, max), accent, tagline, about, featured, verified,
# blocked offsets (days from today), packages: (name, types, services, includes, basis, price, min, max, hours, addons, terms)
PROVIDERS = [
    ("Kalpavruksha Celebrations", "team", "event-planner", "Jayanagar", 30, 14, 25, ["planning", "decoration", "catering", "photography", "dj", "stage", "lighting"],
     ["wedding", "engagement", "anniversary", "corporate", "birthday"], (50, 1200), "#f59e0b", "Weddings and big celebrations, end to end",
     "A full-service planning team for weddings, engagements and milestone celebrations across Bengaluru. One coordinator from the first call to the last guest.", True, True, [12, 13],
     [("Wedding Starter", ["wedding"], ["decoration", "stage", "lighting", "photography"], ["Mandap or stage decor", "Entrance and aisle flowers", "Stage lighting", "Candid photographer (8 hrs)"], "fixed", "185000", 100, 400, 10,
       [("Videography (cinematic film)", "45000", False), ("Mehendi artist (4 hrs)", "12000", False)], "Venue, food and permissions are not included."),
      ("Engagement Classic", ["engagement"], ["decoration", "stage", "photography"], ["Ring ceremony stage", "Floral backdrop", "Photographer (5 hrs)"], "fixed", "68000", 40, 200, 6,
       [("Live singer (2 hrs)", "18000", False)], ""),
      ("Celebration Dinner", ["anniversary", "birthday", "corporate"], ["catering", "decoration"], ["Buffet (2 starters, 4 mains, 2 desserts)", "Table decor", "Service staff"], "per_guest", "950", 40, 300, 5,
       [("Welcome drinks", "120", True), ("Live counter", "180", True)], "Prices per guest; minimum 40 guests.")]),
    ("Confetti & Co.", "team", "event-planner", "Koramangala", 20, 7, 12, ["planning", "decoration", "entertainment", "cake", "photography"],
     ["birthday", "baby-shower", "surprise", "naming", "private-party"], (10, 150), "#f472b6", "Theme birthdays and little celebrations",
     "Theme birthdays, baby showers and surprises. We bring the decor, the games and the photographer; you bring the guest of honour.", True, True, [5],
     [("Birthday Basic", ["birthday"], ["decoration", "cake", "photography"], ["Balloon backdrop and table decor", "1 kg theme cake", "Photographer (2 hrs)"], "fixed", "14999", 10, 40, 3,
       [("Magician (45 min)", "6500", False), ("Return gifts", "180", True)], "Venue not included."),
      ("Birthday Premium", ["birthday"], ["decoration", "photography", "entertainment", "cake"], ["Full theme decor with entry arch", "2 kg designer cake", "Photographer + short video", "Games host (2 hrs)"], "fixed", "38500", 20, 80, 4,
       [("DJ (3 hrs)", "12000", False), ("Snacks counter", "220", True)], ""),
      ("Baby Shower Blush", ["baby-shower"], ["decoration", "photography"], ["Floral swing and backdrop", "Seating decor", "Photographer (3 hrs)"], "fixed", "24999", 15, 80, 4, [], "")]),
    ("Brindavan Events Co.", "team", "event-planner", "Malleshwaram", 25, 18, 30, ["planning", "decoration", "catering", "stage", "sound", "lighting"],
     ["wedding", "religious", "housewarming", "naming", "festival"], (50, 1500), "#eab308", "Traditional functions, done properly",
     "Traditional weddings, griha pravesh, naamkaran and poojas — decor, food and arrangements by people who know the rituals.", False, True, [],
     [("Griha Pravesh Package", ["housewarming"], ["decoration", "catering"], ["Flower and mango-leaf decor", "Pooja arrangements", "South Indian lunch (banana leaf)"], "per_guest", "650", 30, 250, 6, [], ""),
      ("Traditional Wedding", ["wedding"], ["decoration", "catering", "stage", "sound"], ["Mandap and stage", "Nadaswaram arrangement", "Breakfast and lunch", "Sound system"], "per_guest", "1450", 150, 1200, 12,
       [("Videography", "40000", False)], "Hall booked separately.")]),
    ("Northstar Corporate Events", "team", "event-planner", "Whitefield", 35, 11, 40, ["planning", "venue", "stage", "sound", "lighting", "host", "staff", "catering"],
     ["corporate", "conference", "product-launch", "seminar", "workshop", "exhibition"], (30, 2000), "#818cf8", "Offsites, town halls and launches",
     "Corporate events with run-of-show discipline: AV, stage, anchors, registration desks and catering, delivered on schedule.", True, True, [],
     [("Town Hall Essentials", ["corporate", "conference"], ["stage", "sound", "lighting", "host"], ["Stage with LED backdrop", "Sound and 2 wireless mics", "Anchor", "AV technician"], "fixed", "95000", 50, 600, 6,
       [("Live streaming", "35000", False), ("Registration desk staff (per person)", "2500", False)], "Venue not included."),
      ("Team Offsite Day", ["corporate"], ["planning", "catering", "host"], ["Planning and run-of-show", "Breakfast, lunch and high tea", "Team activities host"], "per_guest", "1850", 25, 300, 9, [], "")]),
    ("Petal & Prop Decor", "vendor", "event-decorator", "HSR Layout", 20, 6, 8, ["decoration", "lighting"],
     ["birthday", "anniversary", "baby-shower", "surprise", "engagement"], (5, 200), "#fb7185", "Backdrops, balloons and florals",
     "Balloon and floral decor for homes and halls. Every design is planned with you first.", False, True, [6],
     [("Home Birthday Decor", ["birthday"], ["decoration"], ["Balloon arch", "Name banner", "Table setup"], "fixed", "6499", 1, 40, 2, [("Fairy-light canopy", "2500", False)], ""),
      ("Room Surprise", ["surprise", "anniversary"], ["decoration", "lighting"], ["Heart balloons", "Candles and petals", "Fairy lights"], "fixed", "4999", 1, 10, 2, [], "")]),
    ("Saffron Stage & Decor", "vendor", "event-decorator", "Basavanagudi", 30, 15, 20, ["decoration", "stage", "lighting"],
     ["wedding", "engagement", "religious", "cultural", "school"], (100, 2000), "#f97316", "Mandaps, stages and big-hall decor",
     "Large-format decor: mandaps, stages, entrances and lighting for halls and lawns.", False, True, [],
     [("Mandap & Stage", ["wedding", "engagement"], ["decoration", "stage", "lighting"], ["Mandap", "Stage backdrop", "Entrance decor", "Warm lighting"], "fixed", "120000", 100, 1500, 12, [], "")]),
    ("Lumière Lights & Sound", "vendor", "event-decorator", "Bellandur", 30, 9, 14, ["sound", "lighting", "stage", "dj"],
     ["corporate", "college", "cultural", "private-party", "wedding"], (20, 3000), "#38bdf8", "Sound, lights and stages",
     "Line arrays, wash lights, trusses and LED walls with technicians on site.", False, True, [],
     [("Party Sound & Lights", ["private-party", "birthday"], ["sound", "lighting", "dj"], ["2 tops + 1 sub", "Party lights", "DJ console with DJ (4 hrs)"], "fixed", "18000", 10, 150, 5, [], ""),
      ("Stage & AV Pro", ["corporate", "college", "cultural"], ["stage", "sound", "lighting"], ["24×16 ft stage", "Line array", "Moving heads", "2 technicians"], "fixed", "85000", 100, 3000, 8, [("LED wall 12×8 ft", "40000", False)], "")]),
    ("Frame Story Studio", "vendor", "event-photographer", "Indiranagar", 40, 10, 6, ["photography", "videography"],
     ["wedding", "engagement", "birthday", "photo-shoot", "corporate", "anniversary"], (1, 2000), "#a78bfa", "Candid photos and cinematic films",
     "Candid wedding and event photography with short cinematic films. Edited gallery in 3 weeks.", True, True, [12],
     [("Event Photography (4 hrs)", ["birthday", "corporate", "anniversary"], ["photography"], ["1 photographer", "300+ edited photos", "Online gallery"], "fixed", "18000", 1, 500, 4, [("Extra hour", "4000", False)], ""),
      ("Wedding Candid + Film", ["wedding", "engagement"], ["photography", "videography"], ["2 photographers", "1 videographer", "Highlight film (4 min)", "Album (40 sheets)"], "fixed", "145000", 50, 2000, 12, [("Drone", "15000", False)], "")]),
    ("Little Lens Kids Photography", "vendor", "event-photographer", "Jayanagar", 20, 5, 2, ["photography"],
     ["birthday", "baby-shower", "naming", "photo-shoot"], (1, 150), "#f9a8d4", "Kids’ parties and family moments",
     "Patient, playful photography for children’s birthdays, naming ceremonies and baby showers.", False, False, [],
     [("Kids Party Coverage", ["birthday", "naming"], ["photography"], ["Photographer (3 hrs)", "200 edited photos"], "fixed", "11500", 1, 120, 3, [], "")]),
    ("DJ Nikhil Rao", "vendor", "event-entertainer", "Koramangala", 35, 8, 2, ["dj", "sound", "lighting"],
     ["private-party", "college", "wedding", "birthday", "corporate", "farewell"], (20, 1500), "#22d3ee", "Bollywood, house and retro sets",
     "Open-format DJ for sangeets, college nights and house parties, with his own sound and lights.", False, True, [5, 6],
     [("House Party Set (4 hrs)", ["private-party", "birthday", "farewell"], ["dj", "sound"], ["DJ (4 hrs)", "Sound for up to 100 guests"], "fixed", "15000", 20, 100, 4, [], ""),
      ("Sangeet Night", ["wedding"], ["dj", "sound", "lighting"], ["DJ (5 hrs)", "Sound and dance-floor lights", "Song list planning call"], "fixed", "42000", 80, 600, 5, [], "")]),
    ("Raga Live Band", "vendor", "event-entertainer", "Malleshwaram", 40, 12, 6, ["music", "sound"],
     ["wedding", "anniversary", "corporate", "cultural", "reunion"], (50, 1000), "#fbbf24", "Live Bollywood and acoustic sets",
     "A six-piece band for receptions and evenings: Bollywood, retro and acoustic sets with their own sound.", False, True, [],
     [("Acoustic Evening (2 hrs)", ["anniversary", "corporate", "reunion"], ["music"], ["3 musicians", "2 hours", "Basic sound"], "fixed", "35000", 30, 300, 2, [], ""),
      ("Reception Band (3 hrs)", ["wedding"], ["music", "sound"], ["6 musicians", "3 hours", "Full sound"], "fixed", "85000", 100, 1000, 3, [], "")]),
    ("Funtastic Kids Entertainers", "vendor", "event-entertainer", "HSR Layout", 25, 6, 8, ["entertainment", "host"],
     ["birthday", "school", "festival"], (10, 300), "#4ade80", "Magic, games and puppet shows",
     "Magicians, game hosts, tattoo artists and puppet shows for children’s parties.", False, True, [],
     [("Party Games Host (2 hrs)", ["birthday"], ["entertainment", "host"], ["Games host", "Prizes for winners"], "fixed", "7500", 10, 60, 2, [("Magic show (45 min)", "6000", False), ("Tattoo artist", "4500", False)], "")]),
    ("Anchor Meera S", "vendor", "event-entertainer", "Indiranagar", 40, 9, 1, ["host"],
     ["corporate", "wedding", "college", "cultural", "product-launch", "conference"], (50, 5000), "#c084fc", "Bilingual anchor for every stage",
     "English, Kannada and Hindi anchoring for sangeets, award nights and conferences.", False, True, [],
     [("Event Anchoring (4 hrs)", ["corporate", "college", "wedding", "cultural"], ["host"], ["Script planning call", "Anchoring up to 4 hours"], "fixed", "25000", 50, 5000, 4, [], "")]),
    ("Glow by Divya", "vendor", "event-makeup", "Jayanagar", 30, 7, 3, ["makeup", "mehendi"],
     ["wedding", "engagement", "photo-shoot", "anniversary"], (1, 50), "#f472b6", "Bridal makeup and mehendi",
     "Bridal and party makeup with an assistant for hair and draping; mehendi artists on request.", False, True, [12, 13],
     [("Bridal Makeup", ["wedding"], ["makeup"], ["HD makeup", "Hairstyling", "Saree draping", "Trial session"], "fixed", "28000", 1, 1, 4, [("Family makeup (per person)", "3500", False)], ""),
      ("Mehendi (bride + 10 guests)", ["wedding", "engagement"], ["mehendi"], ["Bridal mehendi", "Mehendi for 10 guests"], "fixed", "14000", 1, 30, 5, [], "")]),
    ("Annapoorna Caterers", "vendor", "catering", "Basavanagudi", 30, 20, 45, ["catering", "staff"],
     ["wedding", "religious", "housewarming", "naming", "birthday", "corporate"], (50, 2000), "#84cc16", "Traditional vegetarian catering",
     "South Indian vegetarian catering — banana-leaf meals, buffets and live counters with service staff.", True, True, [],
     [("Banana-Leaf Lunch", ["wedding", "religious", "housewarming", "naming"], ["catering", "staff"], ["16-item traditional meal", "Service staff"], "per_guest", "520", 50, 2000, 3, [("Payasam counter", "40", True)], "Minimum 50 guests."),
      ("Party Buffet", ["birthday", "corporate"], ["catering", "staff"], ["2 starters, 3 mains, rice, 2 desserts", "Buffet setup and staff"], "per_guest", "690", 50, 800, 4, [], "")]),
    ("Spice Route Catering", "vendor", "catering", "Whitefield", 30, 9, 30, ["catering", "staff", "cake"],
     ["corporate", "birthday", "private-party", "wedding", "farewell"], (30, 1000), "#ef4444", "North Indian, continental and live counters",
     "Multi-cuisine buffets with live counters for parties and offices.", False, True, [],
     [("Office Lunch Buffet", ["corporate", "farewell"], ["catering", "staff"], ["Veg and non-veg buffet", "Disposables", "2 service staff"], "per_guest", "540", 30, 600, 3, [], ""),
      ("Cocktail Party Bites", ["private-party", "birthday"], ["catering", "staff"], ["6 passed starters", "Mocktail counter", "Service staff"], "per_guest", "820", 30, 300, 4, [("Dessert table", "150", True)], "")]),
    ("SafeHands Event Staff", "vendor", "event-service", "Yelahanka", 40, 8, 120, ["security", "staff", "cleaning"],
     ["corporate", "conference", "exhibition", "wedding", "college", "cultural"], (100, 10000), "#94a3b8", "Security, ushers and clean-up crews",
     "Trained security, ushers, registration staff and housekeeping crews for large events.", False, True, [],
     [("Event Staff Crew (8 hrs)", ["corporate", "conference", "exhibition", "college"], ["staff", "security"], ["4 security staff", "4 ushers", "Supervisor"], "fixed", "24000", 100, 3000, 8, [("Extra staff member", "2500", False)], "")]),
    ("CityHop Event Transport", "vendor", "event-service", "Malleshwaram", 50, 6, 30, ["transport"],
     ["wedding", "corporate", "reunion", "conference"], (20, 1000), "#64748b", "Guest shuttles and wedding cars",
     "Tempo travellers, coaches and decorated cars for guest pick-ups and baraat.", False, False, [],
     [("Guest Shuttle Day", ["wedding", "corporate", "conference"], ["transport"], ["2 tempo travellers (12 seats)", "10 hours / 100 km each"], "fixed", "16000", 20, 60, 10, [], "Tolls and parking extra.")]),
    ("Invite Atelier", "vendor", "event-decorator", "Indiranagar", 60, 5, 4, ["invitations"],
     ["wedding", "engagement", "birthday", "housewarming", "corporate"], (1, 3000), "#e879f9", "Printed and digital invitations",
     "Designed invitation suites: printed cards, e-invites and video invites.", False, True, [],
     [("E-Invite + Video Invite", ["wedding", "engagement", "birthday", "housewarming"], ["invitations"], ["Designed e-invite", "30-second video invite", "2 revisions"], "fixed", "4500", 1, 3000, 1, [], "")]),
    ("Sweet Sculpt Cakes", "vendor", "catering", "Koramangala", 20, 6, 5, ["cake"],
     ["birthday", "anniversary", "wedding", "baby-shower", "surprise"], (1, 500), "#fda4af", "Theme cakes and dessert tables",
     "Custom theme cakes and dessert tables, delivered and set up.", False, True, [],
     [("Theme Cake (2 kg)", ["birthday", "anniversary", "baby-shower"], ["cake"], ["2 kg custom theme cake", "Delivery and setup"], "fixed", "4800", 1, 60, 1, [], ""),
      ("Dessert Table", ["wedding", "birthday", "anniversary"], ["cake"], ["Cake + 6 dessert varieties", "Styled table"], "per_guest", "260", 40, 500, 4, [], "")]),
]

# name, area, space type, indoor, outdoor, seated, floating, amenities, rules, parking, catering, hours, types, accent, tagline, packages, featured
VENUES = [
    ("The Courtyard Banquet", "Jayanagar", "Banquet hall", True, False, 300, 500, ["Air-conditioned", "Stage", "Bridal room", "Power backup", "Lift"],
     ["Music until 10:30 PM", "No outside alcohol"], "Basement parking for 60 cars", "both", "8 AM – 11 PM", ["wedding", "engagement", "birthday", "corporate", "anniversary"], "#f59e0b",
     "A classic hall for receptions and big birthdays", [("Hall Hire (half day)", "fixed", "65000", 50, 500, 5), ("Hall + Veg Buffet", "per_guest", "1100", 150, 500, 6)], True),
    ("Skyline Terrace", "Koramangala", "Rooftop", False, True, 80, 150, ["City views", "Bar counter", "Fairy lights", "Washrooms"],
     ["Music until 10 PM", "No confetti"], "Valet for 20 cars", "in_house", "5 PM – 11 PM", ["birthday", "private-party", "anniversary", "farewell", "corporate"], "#38bdf8",
     "Open-air evenings above the city", [("Evening Takeover", "per_guest", "1450", 40, 150, 4)], True),
    ("Green Acres Lawn", "Yelahanka", "Garden lawn", False, True, 600, 1200, ["Lawn", "Changing rooms", "Generator", "Tent on request"],
     ["Sound limits after 10 PM"], "Open parking for 200 cars", "outside", "7 AM – 11 PM", ["wedding", "religious", "festival", "reunion", "corporate"], "#22c55e",
     "A big lawn for weddings and festivals", [("Lawn Hire (full day)", "fixed", "150000", 200, 1200, 14)], False),
    ("Whitefield Convention Hall", "Whitefield", "Conference hall", True, False, 450, 700, ["Projector and screens", "Wi-Fi", "Green rooms", "Registration foyer"],
     ["Corporate and private events only"], "Multi-level parking", "in_house", "7 AM – 10 PM", ["corporate", "conference", "seminar", "product-launch", "exhibition"], "#6366f1",
     "Conferences and launches with full AV", [("Conference Day", "per_guest", "1650", 100, 700, 9), ("Seminar Half-Day", "fixed", "48000", 30, 200, 4)], True),
    ("Little Nest Party Studio", "HSR Layout", "Party room", True, False, 40, 60, ["Play area", "Projector", "Kitchenette"],
     ["Kids’ parties until 9 PM"], "Street parking", "outside", "10 AM – 9 PM", ["birthday", "baby-shower", "naming", "surprise"], "#f472b6",
     "A cosy studio for kids’ birthdays", [("Party Room (3 hrs)", "fixed", "9000", 10, 60, 3)], False),
    ("Heritage Kalyana Mantapa", "Basavanagudi", "Kalyana mantapa", True, False, 500, 800, ["Dining hall", "Rooms for families", "Kitchen", "Lift"],
     ["Vegetarian only", "No alcohol"], "Parking for 50 cars", "outside", "5 AM – 11 PM", ["wedding", "engagement", "religious", "naming", "housewarming"], "#eab308",
     "Traditional weddings, the classic way", [("Mantapa (2 days)", "fixed", "220000", 200, 800, 36)], False),
    ("The Loft Indiranagar", "Indiranagar", "Lounge", True, False, 60, 120, ["Bar", "DJ console", "Sound system"],
     ["21+ for bar service"], "Valet", "in_house", "6 PM – 1 AM", ["private-party", "birthday", "farewell", "corporate", "reunion"], "#a855f7",
     "Lounge evenings and private parties", [("Lounge Buyout (3 hrs)", "per_guest", "1800", 30, 120, 3)], False),
    ("Bellandur Lakeside Pavilion", "Bellandur", "Pavilion", True, True, 200, 350, ["Lakeside deck", "Air-cooled hall", "Bridal room"],
     ["Music until 10 PM"], "Parking for 80 cars", "both", "8 AM – 11 PM", ["engagement", "anniversary", "birthday", "corporate", "wedding"], "#14b8a6",
     "Indoor hall with an outdoor deck", [("Pavilion Hire (half day)", "fixed", "78000", 50, 350, 5)], False),
    ("Malleshwaram Community Hall", "Malleshwaram", "Community hall", True, False, 150, 220, ["Stage", "Chairs and tables", "Kitchen"],
     ["Ends by 10 PM"], "Street parking", "outside", "7 AM – 10 PM", ["religious", "naming", "housewarming", "birthday", "cultural", "school"], "#fbbf24",
     "Simple and affordable for family functions", [("Hall Hire (half day)", "fixed", "18000", 30, 220, 5)], False),
    ("Cubbon Creative Space", "Indiranagar", "Studio / workshop space", True, False, 40, 70, ["Whiteboards", "Projector", "Wi-Fi", "Natural light"],
     ["No loud music"], "Paid parking nearby", "outside", "8 AM – 9 PM", ["workshop", "seminar", "photo-shoot", "corporate"], "#7dd3fc",
     "Bright space for workshops and shoots", [("Workshop Day", "fixed", "15000", 5, 70, 8)], False),
]


def _partner(name, cat_slug, area, radius, verified, now, email):
    user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=name, phone_verified=False)
    m = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
    category = PartnerCategory.objects.select_related("partner_type").get(slug=cat_slug)
    partner = m.partner if m else Partner.objects.create(partner_type=category.partner_type, category=category, business_name=name)
    if not m:
        PartnerMembership.objects.create(partner=partner, user=user, role="owner")
    partner.partner_code = partner.partner_code or _code()
    partner.status = Partner.Status.ACTIVE
    partner.is_available = True
    partner.profile_completed_at = partner.profile_completed_at or now
    partner.save()
    PartnerProfile.objects.update_or_create(partner=partner, defaults={"contact_name": name, "details": {}})
    lat, lng = locality_point(area, email)
    PartnerAddress.objects.update_or_create(partner=partner, is_primary=True, defaults={
        "line1": f"{area} studio", "city": "Bengaluru", "state": "Karnataka", "postal_code": "560001", "latitude": lat, "longitude": lng,
        "service_area": f"{area} and across Bengaluru", "service_radius_km": radius})
    if verified and not PartnerVerification.objects.filter(partner=partner, status="approved").exists():
        PartnerVerification.objects.create(partner=partner, status="approved", submitted_at=now - timedelta(days=90), reviewed_at=now - timedelta(days=85),
                                           reviewer_note="Development seed: business documents checked")
    if not partner.availability_events.exists():
        PartnerAvailabilityEvent.objects.create(partner=partner, is_available=True, note="Development seed")
    return partner, lat, lng


def seed_eventhub(log) -> None:
    from apps.eventhub.engine import today
    from apps.eventhub.models import EventPackage, EventProvider, EventService, EventType, PackageAddon, ProviderBlockedDate, VenueDetails
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType

    apply_catalog(PartnerType, PartnerCategory)  # event categories use the Events workspace
    svc = {}
    for pos, (slug, name, group, icon, syn) in enumerate(SERVICES):
        svc[slug], _ = EventService.objects.update_or_create(slug=slug, defaults=dict(name=name, group=group, icon=icon, synonyms=syn, position=pos, is_active=True))
    types = {}
    for pos, (slug, name, group, icon, accent, summary, syn, sugg, planner) in enumerate(TYPES):
        checklist = [{"key": k, "label": l, "service": s} for k, l, s in CHECKLIST if s in sugg or s == "venue"]
        types[slug], _ = EventType.objects.update_or_create(slug=slug, defaults=dict(
            name=name, group=group, icon=icon, accent=accent, summary=summary, synonyms=syn, suggested_services=sugg, checklist=checklist,
            position=pos, in_planner=planner, is_active=True))
    now = timezone.now()
    d0 = today()

    def make_packages(p, rows):
        keep = []
        for pos, (name, ptypes, psvc, includes, basis, price, lo, hi, hours, addons, terms) in enumerate(rows):
            pkg, _ = EventPackage.objects.update_or_create(provider=p, name=name, defaults=dict(
                description=", ".join(includes[:2]), includes=includes, basis=basis, price=D(price), min_guests=lo, max_guests=hi,
                duration_hours=D(str(hours)), terms=terms, position=pos, is_active=True))
            pkg.event_types.set([types[t] for t in ptypes])
            pkg.services.set([svc[s] for s in psvc])
            pkg.addons.all().delete()
            PackageAddon.objects.bulk_create([PackageAddon(package=pkg, name=a, price=D(pr), per_guest=pg, position=i) for i, (a, pr, pg) in enumerate(addons)])
            keep.append(pkg.pk)
        p.packages.exclude(pk__in=keep).update(is_active=False)

    for i, (name, kind, pcat, area, radius, years, team, services, etypes, (lo, hi), accent, tagline, about, featured, verified, blocked, packages) in enumerate(PROVIDERS):
        email = f"events.{name.lower().replace(' ', '.').replace('&', 'and').replace(',', '')}@click.local"
        partner, lat, lng = _partner(name, pcat, area, radius, verified, now, email)
        p, _ = EventProvider.objects.update_or_create(partner=partner, defaults=dict(
            kind=kind, tagline=tagline, about=about, accent=accent, experience_years=years, team_size=team, languages=["English", "Kannada", "Hindi"][: 2 + i % 2],
            city="Bengaluru", area=area, latitude=lat, longitude=lng, service_radius_km=radius, max_events_per_day=2 if team >= 20 else 1,
            min_notice_days=3 if kind == "team" else 2, min_guests=lo, max_guests=hi, faqs=_faq(10 if kind == "team" else 7),
            free_cancellation_days=10 if kind == "team" else 7, late_cancellation_fee_percent=30 if kind == "team" else 20,
            is_listed=True, is_featured=featured))
        p.services.set([svc[s] for s in services])
        p.event_types.set([types[t] for t in etypes])
        make_packages(p, packages)
        p.blocked_dates.filter(date__gte=d0).delete()
        ProviderBlockedDate.objects.bulk_create([ProviderBlockedDate(provider=p, date=d0 + timedelta(days=o), reason="Development seed: already committed")
                                                 for o in blocked])

    for i, (name, area, space, indoor, outdoor, seated, floating, amenities, rules, parking, catering, hours, etypes, accent, tagline, pkgs, featured) in enumerate(VENUES):
        email = f"venue.{name.lower().replace(' ', '.')}@click.local"
        partner, lat, lng = _partner(name, "venue", area, 30, True, now, email)
        p, _ = EventProvider.objects.update_or_create(partner=partner, defaults=dict(
            kind="venue", tagline=tagline, about=f"{space} in {area}. {tagline}.", accent=accent, experience_years=5 + i, team_size=None,
            city="Bengaluru", area=area, latitude=lat, longitude=lng, service_radius_km=30, max_events_per_day=1, min_notice_days=3,
            min_guests=None, max_guests=floating, faqs=_faq(14), free_cancellation_days=14, late_cancellation_fee_percent=25, is_listed=True, is_featured=featured))
        VenueDetails.objects.update_or_create(provider=p, defaults=dict(
            space_type=space, indoor=indoor, outdoor=outdoor, seated_capacity=seated, floating_capacity=floating, address=f"{area}, Bengaluru",
            amenities=amenities, rules=rules, parking=parking, catering_policy=catering, hours=hours))
        p.services.set([svc["venue"]] + ([svc["catering"]] if catering in ("in_house", "both") else []))
        p.event_types.set([types[t] for t in etypes])
        rows = [(pn, etypes, ["venue"] + (["catering"] if b == "per_guest" else []), [f"{space} for {hrs} hours", *amenities[:2]], b, pr, lo, hi, hrs, [], "Decor and outside vendors as per venue rules.")
                for pn, b, pr, lo, hi, hrs in pkgs]
        make_packages(p, rows)
        p.blocked_dates.filter(date__gte=d0).delete()
        ProviderBlockedDate.objects.bulk_create([ProviderBlockedDate(provider=p, date=d0 + timedelta(days=o), reason="Development seed: booked offline")
                                                 for o in ([(5 - d0.weekday()) % 7 + 7] if i % 3 == 0 else [])])
    log(f"events: {len(TYPES)} event types, {len(SERVICES)} services, {len(PROVIDERS)} event teams/specialists, {len(VENUES)} venues, "
        f"{EventPackage.objects.filter(is_active=True).count()} packages (no logos, covers or portfolio photos)")


# --- history: the only source of ratings and "events completed" ------------------------------------------------------

NS = uuid.UUID("3b6f0d2e-77a1-4c55-9e0a-ee7e5000e7e1")
COMMENTS = ["Everything was set up before the guests arrived. Lovely work.", "Responsive on the plan and great on the day.", "Good value for the price.", "",
            "The decor looked exactly like the reference photo.", "A few things were late, but they sorted it out quickly."]


def _past_booking(customer, provider, address, days_ago, key, review=None, status="completed", future=False):
    from apps.eventhub.engine import money, tax_on, today
    from apps.eventhub.lifecycle import _milestones
    from apps.eventhub.models import EventBooking, EventPlan, EventReview, StatusEvent
    from apps.payments.models import Payment

    if EventBooking.objects.filter(customer=customer, idempotency_key=str(key)).exists():
        return 0
    pkg = provider.packages.filter(is_active=True).first()
    if pkg is None or address is None:
        return 0
    etype = pkg.event_types.first() or provider.event_types.first()
    guests = max(pkg.min_guests, min(pkg.max_guests, 40))
    day = today() + timedelta(days=days_ago) if future else today() - timedelta(days=days_ago)
    plan = EventPlan.objects.create(customer=customer, event_type=etype, title="", date=day, address_ref=address, address=address.snapshot(),
                                    latitude=address.latitude, longitude=address.longitude, guests=guests, budget_flexible=True,
                                    requirements="Development seed event", status="done" if not future else "booked")
    plan.services.set(pkg.services.all())
    amount = money(pkg.price * guests if pkg.basis == "per_guest" else pkg.price)
    tax = tax_on(amount)
    b = EventBooking.objects.create(
        customer=customer, plan=plan, provider=provider, package=pkg, status=status, payment_status="paid", payment_method="wallet",
        event_date=day, start_time=time(18, 0), guests=guests, address=plan.address, title=f"{pkg.name} · {provider.partner.business_name}",
        lines=[{"label": pkg.name, "amount": f"{amount:.2f}"}], services=[s.name for s in pkg.services.all()], subtotal=amount, tax=tax,
        total=amount + tax, idempotency_key=str(key), confirmed_at=timezone.now() - timedelta(days=days_ago + 20 if not future else 3),
        completed_at=timezone.now() - timedelta(days=days_ago) if status == "completed" else None)
    Payment.objects.create(event_booking=b, method="wallet", amount=b.total, currency=b.currency, status=Payment.Status.CAPTURED)
    for st in (["payment_pending", "confirmed", "preparing", "in_progress", "completed"] if status == "completed" else ["payment_pending", "confirmed"]):
        StatusEvent.objects.create(booking=b, to=st, note="Development seed")
    _milestones(b, plan)
    if status == "completed":
        b.milestones.update(done_at=timezone.now() - timedelta(days=days_ago))
        if review:
            EventReview.objects.create(booking=b, customer=customer, provider=provider, overall=review[0], quality=review[0],
                                       communication=max(1, review[0] - days_ago % 2), value=review[0], comment=review[1])
    return 1


def seed_event_history(profile, log) -> None:
    from apps.eventhub import lifecycle
    from apps.eventhub.models import Enquiry, EventPlan, EventProvider, EventType
    from apps.wishlists.models import WishlistItem

    from .showtime import VIEWERS, _viewer

    provs = list(EventProvider.objects.select_related("partner").order_by("partner__business_name"))
    if not provs:
        return
    made = 0
    viewers = [_viewer(n, loc) for n, loc in VIEWERS]
    for v, (n, loc) in zip(viewers, VIEWERS):  # dev viewers need a place for their past events
        if not v.addresses.exists():
            from apps.customers.models import Address

            lat, lng = locality_point(loc, f"viewer-{n}")
            Address.objects.create(customer=v, label="home", recipient_name=n, phone="+91 90000 00000", line1=f"{n}’s home (dev)", line2=loc,
                                   city="Bengaluru", postal_code="560001", latitude=lat, longitude=lng)
    for k, p in enumerate(provs):
        for i in range(1 + (k * 5) % 6):  # 1..6 past events each, so counts and ratings differ
            v = viewers[(k + i) % len(viewers)]
            addr = v.addresses.first()
            rating = [5, 4, 5, 5, 4, 3, 5][(k + i) % 7]
            review = (rating, COMMENTS[(k + i) % len(COMMENTS)]) if i % 3 != 2 else None
            made += _past_booking(v, p, addr, 15 + i * 21 + k % 5, uuid.uuid5(NS, f"{p.partner.business_name}-{i}"), review)
    home = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
    by = {p.partner.business_name: p for p in provs}
    if home is not None:
        if (c := by.get("Confetti & Co.")):
            made += _past_booking(profile, c, home, 40, uuid.uuid5(NS, "test-past"), (5, "My daughter’s superhero party was perfect."))
            WishlistItem.objects.get_or_create(customer=profile, event_provider=c)
        if (f := by.get("Frame Story Studio")):
            made += _past_booking(profile, f, home, 24, uuid.uuid5(NS, "test-upcoming"), status="confirmed", future=True)
        # A plan still being organised: one quote waiting, one request not answered yet.
        anniv = EventType.objects.filter(slug="anniversary").first()
        if anniv and not EventPlan.objects.filter(customer=profile, requirements__startswith="25th anniversary").exists():
            from apps.eventhub.engine import today

            plan = lifecycle.create_plan(profile, {"event_type": "anniversary", "title": "Parents’ 25th anniversary", "date": today() + timedelta(days=45),
                                                   "address_id": home.id, "guests": 60, "budget_min": D("60000"), "budget_max": D("150000"),
                                                   "services": ["decoration", "catering", "photography", "music"],
                                                   "requirements": "25th anniversary dinner for my parents, about 60 guests. Warm, elegant decor and a short slideshow."})
            k1, k2 = by.get("Kalpavruksha Celebrations"), by.get("Raga Live Band")
            ids = [str(x.id) for x in (k1, k2) if x is not None]
            if ids:
                lifecycle.send_enquiries(plan, ids, message="Looking for decor, dinner and music for 60 guests.")
                e = Enquiry.objects.filter(plan=plan, provider=k1).first()
                if e is not None:
                    lifecycle.provider_quote(e, k1, {"items": [{"label": "Decor: stage backdrop, table florals, warm lighting", "amount": "48000"},
                                                              {"label": "Dinner buffet for 60 (₹950 × 60)", "amount": "57000"},
                                                              {"label": "Photographer (4 hrs)", "amount": "18000", "optional": True}],
                                                    "duration_hours": D("5"), "team_size": 12, "terms": "Venue not included. Final guest count 3 days before.",
                                                    "notes": "Happy to add a slideshow screen if the venue has none."})
    for p in provs:
        lifecycle.recompute(p)
    log(f"event history: {made} bookings (completed and reviewed, 1 upcoming for the test customer) and 1 open plan with a quote; "
        "ratings and counts recomputed from them")
