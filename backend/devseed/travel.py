"""
Development seed for Click. Travel (never loaded in production). Real cities with their real airports (IATA codes),
railway stations (station codes) and well-known bus boarding points, approximately located. Operators, airlines,
train names / numbers, timetables, fares and seat layouts are fictional samples in the same shape a provider API
returns; nothing here claims to be a real schedule. Operator ratings come from seeded completed trips rated by dev
viewers (recomputed like real ratings).
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import Decimal as D

from django.utils import timezone
from django.utils.text import slugify

CITIES = [  # slug, name, state, aliases, lat, lng
    ("hyderabad", "Hyderabad", "Telangana", "Secunderabad, HYD", 17.385, 78.4867),
    ("delhi", "Delhi", "Delhi", "New Delhi, NCR", 28.6139, 77.209),
    ("bengaluru", "Bengaluru", "Karnataka", "Bangalore, BLR", 12.9716, 77.5946),
    ("mumbai", "Mumbai", "Maharashtra", "Bombay", 19.076, 72.8777),
    ("chennai", "Chennai", "Tamil Nadu", "Madras", 13.0827, 80.2707),
    ("vijayawada", "Vijayawada", "Andhra Pradesh", "Bezawada", 16.5062, 80.648),
    ("visakhapatnam", "Visakhapatnam", "Andhra Pradesh", "Vizag, Vishakhapatnam", 17.6868, 83.2185),
    ("bhubaneswar", "Bhubaneswar", "Odisha", "Odisha, Orissa", 20.2961, 85.8245),
    ("tirupati", "Tirupati", "Andhra Pradesh", "Tirumala", 13.6288, 79.4192),
    ("goa", "Goa", "Goa", "Panaji, Panjim, Madgaon, Margao", 15.4909, 73.8278),
    ("pune", "Pune", "Maharashtra", "Poona", 18.5204, 73.8567),
    ("kolkata", "Kolkata", "West Bengal", "Calcutta, Howrah", 22.5726, 88.3639),
    ("nagpur", "Nagpur", "Maharashtra", "", 21.1458, 79.0882),
    ("bhopal", "Bhopal", "Madhya Pradesh", "", 23.2599, 77.4126),
    ("agra", "Agra", "Uttar Pradesh", "", 27.1767, 78.0081),
    ("warangal", "Warangal", "Telangana", "Kazipet", 17.9689, 79.5941),
]
AIRPORTS = [  # city, name, IATA, lat, lng
    ("hyderabad", "Rajiv Gandhi International Airport", "HYD", 17.2403, 78.4294), ("delhi", "Indira Gandhi International Airport", "DEL", 28.5562, 77.1),
    ("bengaluru", "Kempegowda International Airport", "BLR", 13.1986, 77.7066), ("mumbai", "Chhatrapati Shivaji Maharaj International Airport", "BOM", 19.0896, 72.8656),
    ("chennai", "Chennai International Airport", "MAA", 12.9941, 80.1709), ("vijayawada", "Vijayawada Airport", "VGA", 16.5304, 80.7968),
    ("visakhapatnam", "Visakhapatnam Airport", "VTZ", 17.7212, 83.2245), ("bhubaneswar", "Biju Patnaik International Airport", "BBI", 20.2444, 85.8178),
    ("tirupati", "Tirupati Airport", "TIR", 13.6325, 79.5433), ("goa", "Goa International Airport (Dabolim)", "GOI", 15.3808, 73.8314),
    ("pune", "Pune Airport", "PNQ", 18.5821, 73.9197), ("kolkata", "Netaji Subhas Chandra Bose International Airport", "CCU", 22.6547, 88.4467),
    ("nagpur", "Dr. Babasaheb Ambedkar International Airport", "NAG", 21.0922, 79.0472),
]
STATIONS = [  # city, name, code, lat, lng
    ("hyderabad", "Secunderabad Junction", "SC", 17.4337, 78.5016), ("hyderabad", "Hyderabad Deccan (Nampally)", "HYB", 17.3923, 78.4677),
    ("hyderabad", "Kacheguda", "KCG", 17.3891, 78.4994), ("delhi", "New Delhi", "NDLS", 28.6431, 77.2197), ("delhi", "Hazrat Nizamuddin", "NZM", 28.5887, 77.2536),
    ("bengaluru", "KSR Bengaluru City Junction", "SBC", 12.9781, 77.5695), ("bengaluru", "Yesvantpur Junction", "YPR", 13.0234, 77.5507),
    ("mumbai", "Mumbai CSMT", "CSMT", 18.9398, 72.8355), ("mumbai", "Lokmanya Tilak Terminus", "LTT", 19.0688, 72.89),
    ("chennai", "Chennai Central", "MAS", 13.0825, 80.2754), ("vijayawada", "Vijayawada Junction", "BZA", 16.5175, 80.6198),
    ("visakhapatnam", "Visakhapatnam Junction", "VSKP", 17.7215, 83.29), ("bhubaneswar", "Bhubaneswar", "BBS", 20.2662, 85.8435),
    ("tirupati", "Tirupati Main", "TPTY", 13.6276, 79.4199), ("goa", "Madgaon Junction", "MAO", 15.2666, 73.9667), ("pune", "Pune Junction", "PUNE", 18.5285, 73.8743),
    ("kolkata", "Howrah Junction", "HWH", 22.5839, 88.3426), ("nagpur", "Nagpur Junction", "NGP", 21.1522, 79.0882), ("bhopal", "Bhopal Junction", "BPL", 23.2667, 77.4128),
    ("agra", "Agra Cantt", "AGC", 27.1585, 77.9909), ("warangal", "Kazipet Junction", "KZJ", 17.9752, 79.5288),
]
BUS_POINTS = [  # city, name, landmark
    ("hyderabad", "Miyapur", "Miyapur X Roads"), ("hyderabad", "Ameerpet", "Ameerpet Metro Station"), ("hyderabad", "Lakdikapul", "Opp. Telangana DGP Office"),
    ("hyderabad", "LB Nagar", "LB Nagar Ring Road"), ("vijayawada", "Benz Circle", "Benz Circle Junction"),
    ("vijayawada", "Pandit Nehru Bus Station", "PNBS main gate"), ("bengaluru", "Majestic", "Kempegowda Bus Station"), ("bengaluru", "Madiwala", "Silk Board side"),
    ("bengaluru", "Electronic City", "Toll Plaza"), ("chennai", "Koyambedu", "CMBT"), ("chennai", "Guindy", "Kathipara Junction"),
    ("delhi", "Kashmere Gate ISBT", "Maharana Pratap ISBT"), ("delhi", "Anand Vihar ISBT", "Anand Vihar"), ("mumbai", "Borivali", "Borivali East, Western Express Hwy"),
    ("mumbai", "Dadar", "Dadar TT Circle"), ("pune", "Swargate", "Swargate Bus Stand"), ("pune", "Wakad", "Wakad Bridge"),
    ("goa", "Panaji", "Kadamba Bus Stand"), ("goa", "Mapusa", "Mapusa Bus Stand"), ("tirupati", "Tirupati Bus Station", "Central Bus Station"),
    ("tirupati", "Alipiri", "Alipiri Gate"), ("visakhapatnam", "Dwaraka Bus Station", "RTC Complex"), ("visakhapatnam", "Maddilapalem", "Maddilapalem Junction"),
]
BUS_OPS = [("Ridgeway Coaches", "#0ea5e9"), ("Bluebird Intercity", "#2563eb"), ("Kaveri Starliner", "#0d9488"), ("Nightjar Sleepers", "#6366f1"),
           ("Coastline Express", "#0891b2")]
AIRLINES = [("Skyline Air", "SK", "#0284c7"), ("Kestrel Airways", "KX", "#4f46e5"), ("Monsoon Air", "MN", "#0f766e")]
RAIL = ("Click. Rail Partner", "RL", "#1d4ed8")

BUS_CANCEL = [[{"hours": 48, "fee_percent": 10}, {"hours": 12, "fee_percent": 25}, {"hours": 4, "fee_percent": 50}],
              [{"hours": 24, "fee_percent": 0}, {"hours": 6, "fee_percent": 50}]]
TRAIN_CANCEL = [{"hours": 48, "fee_percent": 10}, {"hours": 12, "fee_percent": 25}, {"hours": 4, "fee_percent": 50}]
FLIGHT_CANCEL = [{"hours": 72, "fee_percent": 15}, {"hours": 3, "fee_percent": 40}]

# from, to, km, minutes, boarding (from city), dropping (to city), departures [(op index, "HH:MM", type, ac, premium)]
BUS_ROUTES = [
    ("hyderabad", "vijayawada", 275, 330, ["Miyapur", "Ameerpet", "LB Nagar"], ["Benz Circle", "Pandit Nehru Bus Station"],
     [(0, "06:30", "seater", True, False), (1, "14:00", "seater", False, False), (2, "22:30", "sleeper", True, False), (3, "23:15", "seater_sleeper", True, True)]),
    ("hyderabad", "bengaluru", 570, 600, ["Miyapur", "Ameerpet", "Lakdikapul"], ["Majestic", "Madiwala"],
     [(3, "20:30", "sleeper", True, True), (1, "21:15", "sleeper", True, False), (4, "22:00", "semi_sleeper", True, False)]),
    ("hyderabad", "chennai", 630, 690, ["Miyapur", "Ameerpet", "LB Nagar"], ["Koyambedu", "Guindy"], [(2, "19:45", "sleeper", True, False), (0, "21:00", "seater_sleeper", True, False)]),
    ("hyderabad", "tirupati", 560, 630, ["Ameerpet", "Lakdikapul", "LB Nagar"], ["Tirupati Bus Station", "Alipiri"],
     [(4, "20:00", "sleeper", True, False), (2, "21:30", "seater", False, False)]),
    ("hyderabad", "visakhapatnam", 620, 690, ["Miyapur", "Ameerpet", "LB Nagar"], ["Maddilapalem", "Dwaraka Bus Station"], [(3, "19:30", "sleeper", True, True)]),
    ("hyderabad", "delhi", 1550, 1680, ["Miyapur", "Ameerpet"], ["Kashmere Gate ISBT", "Anand Vihar ISBT"], [(1, "16:00", "sleeper", True, False)]),
    ("bengaluru", "chennai", 350, 390, ["Majestic", "Madiwala", "Electronic City"], ["Guindy", "Koyambedu"],
     [(4, "07:00", "seater", True, False), (0, "15:30", "seater", False, False), (2, "23:00", "sleeper", True, False)]),
    ("bengaluru", "goa", 560, 660, ["Majestic", "Madiwala"], ["Mapusa", "Panaji"], [(3, "19:00", "sleeper", True, True), (4, "20:30", "seater_sleeper", True, False)]),
    ("mumbai", "pune", 150, 210, ["Borivali", "Dadar"], ["Wakad", "Swargate"], [(0, "07:00", "seater", True, False), (4, "18:30", "seater", True, True)]),
    ("pune", "goa", 450, 600, ["Swargate", "Wakad"], ["Mapusa", "Panaji"], [(2, "21:00", "sleeper", True, False)]),
    ("vijayawada", "visakhapatnam", 350, 420, ["Pandit Nehru Bus Station", "Benz Circle"], ["Maddilapalem", "Dwaraka Bus Station"],
     [(1, "22:00", "sleeper", True, False), (0, "08:00", "seater", False, False)]),
]

# number, name, type, days, dep, [(station, minute offset, km)], classes
TRAINS = [
    ("12791", "Deccan Capital Superfast", "Superfast", [0, 1, 2, 3, 4, 5, 6], "06:00",
     [("SC", 0, 0), ("KZJ", 120, 132), ("NGP", 520, 581), ("BPL", 900, 971), ("AGC", 1290, 1471), ("NDLS", 1500, 1661)], ["SL", "3A", "2A", "1A"]),
    ("22691", "Twin Cities Rajdhani", "Rajdhani", [1, 3, 6], "15:45",
     [("SC", 0, 0), ("NGP", 470, 581), ("BPL", 830, 971), ("NZM", 1340, 1659)], ["3A", "2A", "1A"]),
    ("12839", "Coromandel Link Express", "Superfast", [0, 1, 2, 3, 4, 5, 6], "17:20",
     [("MAS", 0, 0), ("BZA", 400, 431), ("VSKP", 760, 781), ("BBS", 1210, 1224)], ["SL", "3A", "2A"]),
    ("12711", "Krishna Intercity", "Intercity", [0, 1, 2, 3, 4, 5], "07:10", [("SC", 0, 0), ("BZA", 330, 351)], ["CC", "EC"]),
    ("12715", "Godavari Night Mail", "Mail/Express", [0, 1, 2, 3, 4, 5, 6], "21:00", [("HYB", 0, 0), ("KZJ", 140, 132), ("BZA", 400, 351), ("VSKP", 760, 700)], ["SL", "3A", "2A"]),
    ("12027", "Garden City Shatabdi", "Shatabdi", [0, 1, 2, 3, 4, 5], "06:00", [("MAS", 0, 0), ("SBC", 300, 362)], ["CC", "EC"]),
    ("12123", "Sahyadri Deccan Queen", "Superfast", [0, 1, 2, 3, 4, 5, 6], "17:10", [("CSMT", 0, 0), ("PUNE", 195, 192)], ["CC", "EC"]),
    ("12733", "Venkatadri Express", "Mail/Express", [0, 1, 2, 3, 4, 5, 6], "18:00", [("KCG", 0, 0), ("BZA", 330, 351), ("TPTY", 760, 660)], ["SL", "3A", "2A"]),
    ("12785", "Kacheguda Bengaluru Superfast", "Superfast", [0, 1, 2, 3, 4, 5, 6], "19:05", [("KCG", 0, 0), ("YPR", 640, 610), ("SBC", 680, 618)], ["SL", "3A", "2A"]),
    ("12953", "Konkan Coast Express", "Superfast", [0, 2, 4], "11:00", [("LTT", 0, 0), ("MAO", 690, 765)], ["SL", "3A", "2A"]),
    ("12951", "Western Rajdhani", "Rajdhani", [0, 1, 2, 3, 4, 5, 6], "17:00", [("CSMT", 0, 0), ("NDLS", 960, 1384)], ["3A", "2A", "1A"]),
    ("12841", "Bay Coast Superfast", "Superfast", [0, 1, 2, 3, 4, 5, 6], "15:20", [("HWH", 0, 0), ("BBS", 380, 441), ("VSKP", 830, 879), ("MAS", 1610, 1661)], ["SL", "3A", "2A"]),
]
CLASS_INFO = {  # name, per km, min fare, reservation, superfast, capacity, rac, wl, gst
    "SL": ("Sleeper", D("0.45"), D("150"), D("20"), D("30"), 72, 10, 40, D("0")), "3A": ("AC 3 Tier", D("1.20"), D("500"), D("40"), D("45"), 64, 8, 30, D("5")),
    "2A": ("AC 2 Tier", D("1.75"), D("800"), D("50"), D("45"), 46, 4, 20, D("5")), "1A": ("First AC", D("2.95"), D("1300"), D("60"), D("75"), 24, 0, 10, D("5")),
    "CC": ("AC Chair Car", D("1.10"), D("250"), D("40"), D("45"), 78, 0, 30, D("5")), "EC": ("Executive Chair Car", D("2.30"), D("600"), D("60"), D("75"), 56, 0, 15, D("5")),
}
# from IATA, to IATA, minutes, km, [(airline index, number, "HH:MM")], via IATA (one stop, same flight)
FLIGHTS = [
    ("HYD", "DEL", 135, 1255, [(0, "SK 512", "06:20"), (1, "KX 221", "09:45"), (2, "MN 708", "13:10"), (0, "SK 518", "18:40"), (1, "KX 229", "21:15")], None),
    ("HYD", "DEL", 220, 1380, [(2, "MN 734", "07:30")], "NAG"),
    ("HYD", "BLR", 80, 500, [(0, "SK 301", "07:00"), (2, "MN 402", "12:30"), (1, "KX 118", "19:20")], None),
    ("HYD", "BOM", 90, 620, [(1, "KX 340", "08:15"), (0, "SK 344", "17:50")], None),
    ("HYD", "MAA", 75, 520, [(2, "MN 611", "06:50"), (0, "SK 615", "20:05")], None),
    ("HYD", "VTZ", 75, 520, [(0, "SK 233", "10:40")], None), ("HYD", "GOI", 85, 560, [(1, "KX 455", "11:15")], None),
    ("HYD", "TIR", 70, 480, [(2, "MN 288", "14:20")], None),
    ("BLR", "DEL", 165, 1740, [(1, "KX 101", "06:00"), (0, "SK 107", "11:30"), (2, "MN 109", "20:45")], None),
    ("BOM", "DEL", 130, 1150, [(0, "SK 801", "07:15"), (1, "KX 805", "16:30")], None),
    ("MAA", "BBI", 115, 1020, [(2, "MN 920", "09:05")], None), ("BLR", "GOI", 70, 460, [(0, "SK 640", "08:40")], None),
    ("DEL", "CCU", 135, 1300, [(1, "KX 710", "10:00")], None), ("VGA", "BLR", 80, 520, [(2, "MN 531", "16:10")], None),
]


def _place(kind, name, slug, city=None, code="", state="", aliases="", lat=None, lng=None, landmark="", address=""):
    from apps.travel.models import Place

    p, _ = Place.objects.update_or_create(slug=slug, defaults=dict(kind=kind, name=name, city=city, code=code, state=state, aliases=aliases,
                                                                   latitude=lat, longitude=lng, landmark=landmark, address=address, is_active=True))
    return p


def _hm(base: str, plus: int) -> tuple[time, int]:
    h, m = map(int, base.split(":"))
    total = h * 60 + m + plus
    return time((total // 60) % 24, total % 60), total // 1440


def _seater(rows=10, ladies=("1", "2")):
    decks, seats, n = [{"name": "Seats", "rows": []}], {}, 0
    for _ in range(rows):
        row = []
        for col in range(5):
            if col == 2:
                row.append(None)
                continue
            n += 1
            row.append(str(n))
            seats[str(n)] = {"class": "seater", "ladies": str(n) in ladies}
        decks[0]["rows"].append(row)
    return {"decks": decks, "seats": seats}


def _sleeper(lower_class="sleeper"):
    decks, seats = [], {}
    for deck, prefix in (("Lower deck", "L"), ("Upper deck", "U")):
        rows, n = [], 0
        for _ in range(6):
            n += 3
            row = [f"{prefix}{n - 2}", None, f"{prefix}{n - 1}", f"{prefix}{n}"]
            rows.append(row)
            for s in row:
                if s:
                    seats[s] = {"class": lower_class if prefix == "L" else "sleeper", "ladies": s in ("L1", "U1")}
        decks.append({"name": deck, "rows": rows})
    return {"decks": decks, "seats": seats}


def _seater_sleeper():
    decks, seats = [], {}
    rows, n = [], 0
    for _ in range(8):
        n += 3
        row = [f"S{n - 2}", None, f"S{n - 1}", f"S{n}"]
        rows.append(row)
        for s in row:
            if s:
                seats[s] = {"class": "seater", "ladies": s in ("S1", "S2")}
    decks.append({"name": "Lower deck · seats", "rows": rows})
    rows, n = [], 0
    for _ in range(5):
        n += 3
        row = [f"U{n - 2}", None, f"U{n - 1}", f"U{n}"]
        rows.append(row)
        for s in row:
            if s:
                seats[s] = {"class": "sleeper", "ladies": s == "U1"}
    decks.append({"name": "Upper deck · sleepers", "rows": rows})
    return {"decks": decks, "seats": seats}


VEHICLES = {"seater": "AC Seater (2+2)", "semi_sleeper": "AC Semi-sleeper (2+2)", "sleeper": "AC Sleeper (2+1)", "seater_sleeper": "AC Seater / Sleeper"}
AMENITIES = {"seater": ["Charging point", "Water bottle"], "semi_sleeper": ["Charging point", "Water bottle", "Reading light"],
             "sleeper": ["Charging point", "Water bottle", "Blanket", "Reading light"], "seater_sleeper": ["Charging point", "Water bottle", "Blanket"]}


def _service(op, mode, number, name, vehicle, stops, classes, **kw):
    from apps.travel.models import FareClass, Service, Stop

    s, _ = Service.objects.update_or_create(operator=op, number=number, defaults=dict(mode=mode, name=name, vehicle=vehicle, is_active=True, **kw))
    for i, (place, arrive, depart, day, km, boarding, dropping, note) in enumerate(stops):  # updated in place: tickets reference stops
        Stop.objects.update_or_create(service=s, seq=i + 1, defaults=dict(place=place, arrive=arrive, depart=depart, day=day, km=km,
                                                                          boarding=boarding, dropping=dropping, note=note))
    s.stops.filter(seq__gt=len(stops)).delete()
    keep = []
    for i, c in enumerate(classes):
        code = c.pop("code")
        FareClass.objects.update_or_create(service=s, code=code, defaults={**c, "position": i})
        keep.append(code)
    s.classes.exclude(code__in=keep).delete()
    return s


def seed_travel(log) -> None:
    from apps.travel.models import Operator, Place, TravelOffer

    cities = {}
    for slug, name, state, aliases, lat, lng in CITIES:
        cities[slug] = _place("city", name, slug, state=state, aliases=aliases, lat=lat, lng=lng)
    air, stn, bus = {}, {}, {}
    for city, name, code, lat, lng in AIRPORTS:
        air[code] = _place("airport", name, f"{city}-airport-{code.lower()}", cities[city], code, cities[city].state, lat=lat, lng=lng)
    for city, name, code, lat, lng in STATIONS:
        stn[code] = _place("station", name, f"{city}-station-{code.lower()}", cities[city], code, cities[city].state, lat=lat, lng=lng)
    for city, name, landmark in BUS_POINTS:
        bus[(city, name)] = _place("bus_stop", name, f"{city}-bus-{slugify(name)}", cities[city], "", cities[city].state, landmark=landmark,
                                   address=f"{landmark}, {cities[city].name}")
    ops = [Operator.objects.update_or_create(mode="bus", name=n, defaults=dict(accent=a, contact_phone="+91 40 0000 0000", status="active"))[0] for n, a in BUS_OPS]
    lines = [Operator.objects.update_or_create(mode="flight", name=n, defaults=dict(code=c, accent=a, status="active"))[0] for n, c, a in AIRLINES]
    rail = Operator.objects.update_or_create(mode="train", name=RAIL[0], defaults=dict(code=RAIL[1], accent=RAIL[2], status="active"))[0]
    n_services = 0

    # buses, both directions
    for frm, to, km, minutes, board, drop, deps in BUS_ROUTES:
        for direction in (0, 1):
            a, b = (frm, to) if direction == 0 else (to, frm)
            bpts, dpts = (board, drop) if direction == 0 else (drop, board)
            for k, (op_i, dep, kind, ac, premium) in enumerate(deps):
                dep_t = dep if direction == 0 else f"{(int(dep[:2]) + 1) % 24:02d}{dep[2:]}"
                stops = []
                for i, nm in enumerate(bpts):
                    t, day = _hm(dep_t, i * 20)
                    stops.append((bus[(a, nm)], None, t, day, i * 6, True, False, "Board 15 min early"))
                for i, nm in enumerate(dpts):
                    t, day = _hm(dep_t, minutes - (len(dpts) - 1 - i) * 15)
                    stops.append((bus[(b, nm)], t, None, day, km - (len(dpts) - 1 - i) * 6, False, True, ""))
                rate_seat = D("1.55") if ac else D("1.15")
                rate_sleep = D("2.15") if ac else D("1.65")
                mult = D("1.2") if premium else D("1")
                if kind in ("seater", "semi_sleeper"):
                    layout = _seater(10)
                    classes = [{"code": "seater", "name": "Semi-sleeper seat" if kind == "semi_sleeper" else "Seat", "capacity": 40,
                                "base_fare": (D(km) * rate_seat * mult * (D("1.15") if kind == "semi_sleeper" else 1)).quantize(D("1")), "min_fare": D("200")}]
                elif kind == "sleeper":
                    layout = _sleeper()
                    classes = [{"code": "sleeper", "name": "Sleeper berth", "capacity": 36, "base_fare": (D(km) * rate_sleep * mult).quantize(D("1")), "min_fare": D("300")}]
                else:
                    layout = _seater_sleeper()
                    classes = [{"code": "seater", "name": "Seat", "capacity": 24, "base_fare": (D(km) * rate_seat * mult).quantize(D("1")), "min_fare": D("200")},
                               {"code": "sleeper", "name": "Sleeper berth", "capacity": 15, "base_fare": (D(km) * rate_sleep * mult).quantize(D("1")), "min_fare": D("300")}]
                for c in classes:
                    c.update(tax_percent=D("5") if ac else D("0"), refundable=True)
                vehicle = (("Multi-axle " if premium else "") + VEHICLES[kind]) if ac else VEHICLES[kind].replace("AC ", "Non-AC ")
                number = f"{ops[op_i].name.split()[0][:3].upper()}-{cities[a].name[:3].upper()}{cities[b].name[:3].upper()}-{k + 1}"
                _service(ops[op_i], "bus", number, f"{cities[a].name} – {cities[b].name}", vehicle, stops, classes,
                         bus_type=kind, ac=ac, premium=premium, running_days=list(range(7)),
                         amenities=AMENITIES[kind] + (["Wi-Fi", "Entertainment", "Washroom"] if premium else []) + (["Live tracking by operator"] if k % 2 == 0 else []),
                         seat_layout=layout, cancellation=BUS_CANCEL[(op_i + k) % 2], booking_window_days=30)
                n_services += 1

    # trains, both directions
    for number, name, kind, days, dep, route, codes in TRAINS:
        total_min, total_km = route[-1][1], route[-1][2]
        for direction in (0, 1):
            seq = route if direction == 0 else [(c, total_min - m, total_km - k) for c, m, k in reversed(route)]
            num = number if direction == 0 else str(int(number) + 1)
            dep_t = dep if direction == 0 else f"{(int(dep[:2]) + 2) % 24:02d}{dep[2:]}"
            stops = []
            for i, (code, off, km) in enumerate(seq):
                at, day = _hm(dep_t, off)
                first, last = i == 0, i == len(seq) - 1
                dep_at, _ = _hm(dep_t, off if first else off + 5)
                stops.append((stn[code], None if first else at, None if last else dep_at, day if not first else 0, km, not last, not first,
                              f"Platform {1 + (i + len(code)) % 6}" if first else ""))
            classes = []
            for c in codes:
                nm, per_km, minf, res, sf, cap, rac, wl, gst = CLASS_INFO[c]
                rajdhani = kind in ("Rajdhani", "Shatabdi")
                classes.append({"code": c, "name": nm, "capacity": cap, "rac_capacity": rac, "waitlist_limit": wl, "per_km": per_km * (D("1.25") if rajdhani else 1),
                                "min_fare": minf, "reservation_charge": res, "superfast_charge": sf if kind != "Mail/Express" else D("0"), "tax_percent": gst,
                                "refundable": True, "meal": "Meals included" if rajdhani else ""})
            run = days if direction == 0 else [(d + 1) % 7 for d in days]
            _service(rail, "train", num, name, kind, stops, classes, running_days=run, amenities=["Pantry car"] if kind != "Intercity" else [],
                     cancellation=TRAIN_CANCEL, booking_window_days=60, ac=True)
            n_services += 1

    # flights, both directions
    for frm, to, minutes, km, deps, via in FLIGHTS:
        for direction in (0, 1):
            a, b = (frm, to) if direction == 0 else (to, frm)
            for line_i, number, dep in deps:
                num = number if direction == 0 else f"{number[:-1]}{(int(number[-1]) + 1) % 10}"
                dep_t = dep if direction == 0 else f"{(int(dep[:2]) + 3) % 24:02d}{dep[2:]}"
                arr, aday = _hm(dep_t, minutes)
                stops = [(air[a], None, _hm(dep_t, 0)[0], 0, 0, True, False, f"Terminal {1 + len(num) % 2}")]
                if via:
                    vt, vday = _hm(dep_t, minutes // 2)
                    vd, _ = _hm(dep_t, minutes // 2 + 35)
                    stops.append((air[via], vt, vd, vday, km // 2, False, False, ""))
                stops.append((air[b], arr, None, aday, km, False, True, ""))
                base = max(D("2499"), (D(km) * D("3.6")).quantize(D("1")))
                classes = [{"code": "economy", "name": "Economy", "fare_type": "Saver", "capacity": 156, "base_fare": base, "min_fare": D("1999"),
                            "infant_fare": D("1500"), "tax_percent": D("5"), "refundable": True, "change_fee": D("2250"), "meal": "Snacks for purchase"}]
                if line_i != 2:
                    classes.append({"code": "business", "name": "Business", "fare_type": "Flexi", "capacity": 12, "base_fare": (base * D("3.2")).quantize(D("1")),
                                    "min_fare": D("8999"), "infant_fare": D("1500"), "tax_percent": D("12"), "refundable": True, "change_fee": D("0"),
                                    "meal": "Meal included"})
                _service(lines[line_i], "flight", num, f"{a} → {b}", "Airbus A320neo" if line_i != 1 else "Boeing 737-8", stops, classes,
                         running_days=list(range(7)), baggage={"cabin": "7 kg", "check_in": "15 kg"}, cancellation=FLIGHT_CANCEL, booking_window_days=330,
                         amenities=["Window and aisle seats at check-in"])
                n_services += 1
    now = timezone.now()
    for title, mode, code, pct, cap, minf in [("Bus fares: 10% off up to ₹150", "bus", "", 10, D("150"), D("600")),
                                              ("FLYCLICK: 8% off flights, up to ₹600", "flight", "FLYCLICK", 8, D("600"), D("3000"))]:
        TravelOffer.objects.update_or_create(title=title, defaults=dict(mode=mode, code=code, percent=pct, max_discount=cap, min_fare=minf,
                                                                        starts_at=now - timedelta(days=5), ends_at=now + timedelta(days=120), is_active=True))
    log(f"travel: {len(CITIES)} cities, {len(AIRPORTS)} airports, {len(STATIONS)} stations, {len(BUS_POINTS)} boarding points; "
        f"{n_services} fictional timetabled services (bus, train, flight); 2 offers")


NS = uuid.UUID("7d2a4b1e-3c5f-4e8a-9b0d-1a2b3c4d5e6f")
TRIP_COMMENTS = ["On time and clean.", "Comfortable, staff were helpful.", "Left a little late but made up time.", "Smooth trip, would book again.",
                 "Seats could be cleaner.", "Good value for the fare."]


def _ticket(customer, service, days, key, status="confirmed", seat_pick=0, rating=None, passengers=None):
    """A ticket on `service` leaving its first stop `days` from today (negative = past)."""
    from apps.payments.models import Payment
    from apps.travel import engine
    from apps.travel.models import Journey, Passenger, StatusEvent, TravelBooking, TripRating, pnr

    if TravelBooking.objects.filter(customer=customer, idempotency_key=str(key)).exists():
        return 0
    j, _ = Journey.objects.get_or_create(service=service, date=engine.today() + timedelta(days=days))
    stops = list(service.stops.order_by("seq"))
    a = next(s for s in stops if s.boarding and s.depart)
    b = [s for s in stops if s.dropping and s.arrive][-1]
    fc = service.classes.order_by("position").first()
    pax = passengers or [(customer.user.full_name.split(" (")[0] or "Guest", 32, "female")]
    q = engine.quote(fc, j, a, b, len(pax))
    bk = TravelBooking.objects.create(
        customer=customer, mode=service.mode, journey=j, fare_class=fc, from_stop=a, to_stop=b, departs_at=engine.at(j.date, a, "depart"),
        arrives_at=engine.at(j.date, b, "arrive"), adults=len(pax), contact_phone="+91 90000 00000", status=status, payment_status="paid",
        operator_name=service.operator.name, service_label=f"{service.number} {service.name}".strip(), class_name=fc.name, from_label=a.place.label,
        to_label=b.place.label, refundable=fc.refundable, cancellation_rules=service.cancellation, base_fare=q.base, fees=q.fees, tax=q.tax, total=q.total,
        idempotency_key=str(key), pnr=pnr(), confirmed_at=timezone.now() - timedelta(days=max(1, -days + 5)))
    used = engine.sold_seats(j)
    free_seats = [s for s in engine.bus_seats(service, fc.code) if s not in used]
    for i, (name, age, gender) in enumerate(pax):
        seat, st = "", "CNF"
        if service.mode == "bus":
            seat = free_seats[(seat_pick + i) % len(free_seats)]
        elif service.mode == "train":
            from apps.travel.booking import _train_plan

            plan = _train_plan(fc, j, [{"age": age}])[0]
            seat, st = plan["seat"], plan["status"]
        Passenger.objects.create(booking=bk, journey=j, fare_class=fc, position=i + 1, name=name, age=age, gender=gender, seat=seat, seat_status=st,
                                 fare=q.unit, holds_seat=status in ("confirmed", "pending_payment"))
    Payment.objects.create(travel_booking=bk, method="wallet", amount=bk.total, currency=bk.currency, status=Payment.Status.CAPTURED)
    for st in (["pending_payment", "confirmed"] + (["completed"] if status == "completed" else [])):
        StatusEvent.objects.create(booking=bk, to=st, note="Development seed")
    if rating:
        TripRating.objects.create(booking=bk, customer=customer, operator=service.operator, rating=rating[0], comment=rating[1])
    return 1


def seed_travel_history(profile, log) -> None:
    from django.db.models import Avg, Count

    from apps.travel.models import Operator, Place, RecentSearch, Route, SavedTraveller, Service, TripRating
    from apps.wishlists.models import WishlistItem

    from .showtime import VIEWERS, _viewer

    if not Service.objects.exists():
        return
    viewers = [_viewer(n, loc) for n, loc in VIEWERS]
    made = 0
    for k, op in enumerate(Operator.objects.order_by("name")):
        services = list(Service.objects.filter(operator=op).order_by("number")[:6])
        for i in range(3 + k % 4):
            s = services[i % len(services)]
            v = viewers[(k + i) % len(viewers)]
            score = max(2, min(5, [5, 4, 4, 5, 3, 4][(k + i) % 6] - (1 if k % 5 == 3 and i % 2 else 0)))
            made += _ticket(v, s, -(6 + i * 4 + k), uuid.uuid5(NS, f"{op.name}-{i}"), "completed", seat_pick=i * 3,
                            rating=(score, TRIP_COMMENTS[(k + i) % len(TRIP_COMMENTS)]), passengers=[(v.user.full_name.split(" (")[0], 30 + i, "male" if i % 2 else "female")])
    for op in Operator.objects.all():
        agg = TripRating.objects.filter(operator=op).aggregate(a=Avg("rating"), n=Count("id"))
        Operator.objects.filter(pk=op.pk).update(rating_average=D(str(round(agg["a"] or 0, 1))), rating_count=agg["n"])
    name = profile.user.full_name or "Test Customer"
    bus = Service.objects.filter(mode="bus", stops__place__slug="hyderabad-bus-miyapur").filter(stops__place__slug="vijayawada-bus-benz-circle").order_by("number").first()
    if bus:
        made += _ticket(profile, bus, 6, uuid.uuid5(NS, "test-upcoming-bus"), "confirmed", seat_pick=7, passengers=[(name, 29, "male")])
    flight = Service.objects.filter(mode="flight", number="SK 301").first()
    if flight:
        made += _ticket(profile, flight, -20, uuid.uuid5(NS, "test-past-flight"), "completed", passengers=[(name, 29, "male")])
    for t_name, age, gender, berth in [(name, 29, "male", "LB"), ("Priya Sharma", 27, "female", "UB")]:
        SavedTraveller.objects.update_or_create(customer=profile, name=t_name, defaults={"age": age, "gender": gender, "berth_preference": berth})
    hyd, dl = Place.objects.get(slug="hyderabad"), Place.objects.get(slug="delhi")
    route, _ = Route.objects.get_or_create(origin=hyd, destination=dl)
    WishlistItem.objects.get_or_create(customer=profile, travel_route=route)
    from apps.travel import engine

    RecentSearch.objects.update_or_create(customer=profile, mode="bus", origin=hyd, destination=Place.objects.get(slug="vijayawada"),
                                          defaults={"date": engine.today() + timedelta(days=3), "adults": 1})
    log(f"travel history: {made} tickets (dev viewers' rated completed trips; the test customer has 1 upcoming bus and 1 past flight), "
        "2 saved travellers, 1 saved route, 1 recent search")
