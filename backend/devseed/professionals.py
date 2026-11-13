"""
DEVELOPMENT MOCK DATA: Click. Services catalog and professionals (all people fictional, Bengaluru).

* The catalog (categories, common jobs, pricing models, prices) is configuration Click operations would manage in
  the admin / Business OS.
* Professionals are Partners in Manpower & Services categories with a Services profile, base address and radius,
  weekly hours, skills and languages. They have NO profile photos: the app shows a neutral placeholder until a
  professional uploads their own photo (no AI-generated or borrowed faces), and no portfolio until they upload work.
* Ratings and "jobs completed" are never typed in: they are computed from the delivered-and-paid job history and the
  reviews created by `seed_service_history` (dev viewers and the test customer).
"""

from __future__ import annotations

import uuid
from datetime import time, timedelta
from decimal import Decimal as D

from django.db import connection
from django.utils import timezone

from apps.partners.models import (
    Partner, PartnerAddress, PartnerAvailabilityEvent, PartnerCategory, PartnerMembership, PartnerProfile, PartnerVerification,
)
from apps.partners.services import PARTNER_CODE_PREFIX, PARTNER_CODE_SEQUENCE
from apps.users.models import User

from . import locality_point

# slug, name, profession, group, icon, accent, summary, synonyms, partner categories,
#   [(job slug, name, description, pricing, price, min hours, inspection fee, minutes, instant, schedulable, includes, excludes)]
CATALOG = [
    ("plumbing", "Plumbing", "Plumber", "home", "wrench", "#0ea5e9", "Leaks, taps, pipes, toilets and fittings.",
     "leak, leaking, tap, pipe, sink, toilet, flush, drain, blocked, water, geyser, shower, plumber", "plumber,home-service", [
         ("tap-repair", "Tap repair or replacement", "Fix a dripping tap or fit a new one you've bought.", "fixed", "199", 1, "0", 45, True, True,
          ["Fixing or replacing one tap", "Checking the connection for leaks"], ["Cost of a new tap", "Wall or tile repair"]),
         ("leak", "Pipe leakage", "Find and fix a leaking pipe or joint.", "starting", "299", 1, "0", 60, True, True,
          ["Visit and inspection", "Sealing or fixing small leaks"], ["Pipes and fittings", "Concealed pipe work (quoted on site)"]),
         ("toilet", "Toilet & flush repair", "Flush, cistern or seat problems.", "starting", "349", 1, "0", 60, True, True,
          ["Flush tank repair", "Seat fitting"], ["Spare parts"]),
         ("blockage", "Drain blockage", "Clear a blocked sink, basin or floor drain.", "fixed", "399", 1, "0", 60, True, True,
          ["Clearing one blocked drain"], ["Sewer line work"]),
         ("plumbing-work", "Other plumbing work", "Describe the job; the plumber quotes after seeing it.", "quote", None, 1, "99", 60, True, True,
          ["Visit and quote"], []),
     ]),
    ("electrical", "Electrical", "Electrician", "home", "sparkle", "#f59e0b", "Power issues, switches, fans, lights and wiring.",
     "power, electric, electrical, switch, socket, fan, light, wiring, mcb, short circuit, inverter, no power, electrician", "electrician,home-service", [
         ("fan-install", "Ceiling fan installation", "Fit and connect a ceiling fan.", "fixed", "249", 1, "0", 45, True, True,
          ["Installing one fan", "Testing"], ["Fan, wiring or hook if missing"]),
         ("switch", "Switch or socket repair", "Replace or fix switches and sockets.", "fixed", "149", 1, "0", 30, True, True, ["Up to 2 points"], ["New switches"]),
         ("power-issue", "Power failure / tripping", "Find why the power trips or a room has no power.", "starting", "299", 1, "0", 60, True, True,
          ["Diagnosis", "Small fixes"], ["Parts, new wiring (quoted on site)"]),
         ("light-fitting", "Light fitting", "Fit tube lights, panels or decorative lights.", "fixed", "199", 1, "0", 45, True, True, ["Up to 2 lights"], ["Lights"]),
         ("wiring", "Wiring work", "New points or rewiring; quoted after inspection.", "quote", None, 1, "149", 90, False, True, ["Visit and quote"], []),
     ]),
    ("carpentry", "Carpentry", "Carpenter", "home", "home", "#b45309", "Furniture repair, doors, shelves and assembly.",
     "carpenter, furniture, door, wood, shelf, cupboard, wardrobe, bed, assembly, hinge, lock, drawer", "carpenter,home-service", [
         ("furniture-repair", "Furniture repair", "Fix loose joints, hinges, drawers.", "starting", "299", 1, "0", 60, True, True, ["Inspection", "Small repairs"], ["Wood, hardware"]),
         ("door", "Door repair", "Doors that stick, hinges, locks.", "starting", "249", 1, "0", 60, True, True, ["Hinge/lock fixing"], ["New lock"]),
         ("shelf", "Shelf installation", "Fit wall shelves.", "fixed", "349", 1, "0", 60, True, True, ["Up to 2 shelves"], ["Shelves"]),
         ("assembly", "Furniture assembly", "Assemble flat-pack furniture; hourly.", "hourly", "299", 1, "0", 120, True, True, ["Assembly", "Clean-up"], []),
         ("custom", "Custom furniture", "Made-to-measure work; quoted after measuring.", "quote", None, 1, "199", 60, False, True, ["Visit, measuring and quote"], []),
     ]),
    ("painting", "Painting", "Painter", "home", "edit", "#8b5cf6", "Rooms, walls, touch-ups and waterproofing.",
     "paint, painting, painter, wall, room, colour, color, waterproofing, putty, damp", "home-service", [
         ("touch-up", "Wall touch-up", "Patch and touch up small areas.", "starting", "499", 1, "0", 120, False, True, ["Up to 2 patches"], ["Paint"]),
         ("room", "Room painting", "Full room repaint; quoted after measuring.", "quote", None, 1, "199", 60, False, True, ["Visit, measuring and quote"], []),
     ]),
    ("cleaning", "Home Cleaning", "Cleaner", "home", "sparkle", "#10b981", "Home, bathroom, kitchen and deep cleaning.",
     "clean, cleaning, cleaner, house, home, bathroom, kitchen, deep, sofa, maid, dust, mop", "cleaning-service,home-service", [
         ("bathroom", "Bathroom cleaning", "One bathroom, tiles to fittings.", "fixed", "449", 1, "0", 90, True, True, ["Tiles, fittings, mirror"], ["Hard-water stain removal"]),
         ("kitchen", "Kitchen cleaning", "Counters, sink, stove and cabinets (outside).", "fixed", "699", 1, "0", 120, True, True, ["Counters, stove, sink"], ["Chimney inside"]),
         ("home-hourly", "Home cleaning (hourly)", "General cleaning by the hour.", "hourly", "249", 2, "0", 120, True, True, ["Dusting, mopping, tidying"], ["Cleaning supplies"]),
         ("deep", "Full home deep cleaning", "Whole home; priced by size after a look.", "quote", None, 1, "0", 240, False, True, ["Quote for your home size"], []),
     ]),
    ("laundry", "Laundry", "Laundry", "personal", "shirt", "#06b6d4", "Wash & fold, ironing, pickup and drop.",
     "laundry, wash, washing clothes, iron, ironing, dry clean, clothes", "home-service", [
         ("wash-fold", "Wash & fold pickup", "Pickup, wash, fold and drop (up to 6 kg).", "fixed", "349", 1, "0", 30, True, True, ["Pickup and drop", "Up to 6 kg"], ["Dry cleaning"]),
         ("ironing", "Ironing pickup", "Up to 20 garments.", "fixed", "199", 1, "0", 30, True, True, ["Up to 20 garments"], []),
     ]),
    ("cook", "Cook", "Cook", "personal", "food", "#ef4444", "Home cooking for meals, parties or daily help.",
     "cook, cooking, chef, meal, food, kitchen help, party cook", "home-service", [
         ("meal", "Cook for a meal", "Cooks one meal with your ingredients (hourly).", "hourly", "299", 2, "0", 120, True, True, ["Cooking", "Kitchen clean-up after"], ["Groceries"]),
         ("party", "Party cooking", "Menu and quote for your guests.", "quote", None, 1, "0", 60, False, True, ["Menu discussion and quote"], []),
     ]),
    ("ac", "AC Service & Repair", "AC Technician", "repair", "drop", "#3b82f6", "AC service, gas, repairs and installation.",
     "ac, air conditioner, aircon, cooling, not cooling, gas, ac service, split, window ac", "technician,home-service", [
         ("ac-service", "AC service (split / window)", "Filter and coil cleaning, check-up.", "fixed", "499", 1, "0", 60, True, True, ["Cleaning", "Performance check"], ["Gas refill", "Parts"]),
         ("ac-repair", "AC not cooling / repair", "Diagnose and repair.", "starting", "399", 1, "0", 60, True, True, ["Diagnosis"], ["Gas, parts (quoted on site)"]),
         ("ac-install", "AC installation", "Install a split AC.", "fixed", "1499", 1, "0", 120, False, True, ["Indoor and outdoor unit fitting"], ["Copper pipe beyond 3 m", "Stand"]),
     ]),
    ("appliance", "Appliance Repair", "Appliance Technician", "repair", "appliance", "#6366f1",
     "Washing machines, refrigerators, TVs, RO purifiers and more.",
     "appliance, washing machine, fridge, refrigerator, tv, television, ro, water purifier, microwave, oven, geyser, repair", "technician", [
         ("washing-machine", "Washing machine repair", "Not spinning, draining or starting.", "starting", "349", 1, "0", 60, True, True, ["Diagnosis"], ["Parts"]),
         ("fridge", "Refrigerator repair", "Not cooling, noise, leaks.", "starting", "349", 1, "0", 60, True, True, ["Diagnosis"], ["Gas, parts"]),
         ("tv", "TV repair", "No picture, sound or power.", "starting", "399", 1, "0", 60, False, True, ["Diagnosis"], ["Panels, boards"]),
         ("ro", "RO / water purifier service", "Filter change and service.", "fixed", "449", 1, "0", 45, True, True, ["Service and check"], ["Filters and membranes"]),
     ]),
    ("device", "Mobile & Laptop Repair", "Device Technician", "repair", "device", "#64748b", "Screens, batteries, slow laptops.",
     "mobile, phone, laptop, computer, pc, screen, battery, slow, virus, keyboard", "technician", [
         ("laptop-checkup", "Laptop or PC check-up", "Diagnosis and software fixes.", "starting", "399", 1, "0", 60, False, True, ["Diagnosis", "Software clean-up"], ["Parts"]),
         ("phone-screen", "Phone screen replacement", "Quoted for your model.", "quote", None, 1, "0", 60, False, True, ["Quote for your model"], []),
     ]),
    ("pest", "Pest Control", "Pest Control Expert", "home", "alert", "#84cc16", "Cockroaches, ants, termites and bedbugs.",
     "pest, cockroach, ants, termite, bedbug, mosquito, rats, insects", "home-service", [
         ("general", "General pest control", "Cockroaches and ants, 1–2 BHK.", "fixed", "999", 1, "0", 90, False, True, ["Gel and spray treatment"], ["Termite treatment"]),
         ("termite", "Termite treatment", "Quoted after inspection.", "quote", None, 1, "0", 60, False, True, ["Inspection and quote"], []),
     ]),
    ("beauty", "Beauty at Home", "Beautician", "personal", "beauty", "#ec4899", "Salon services at home.",
     "beauty, salon, haircut, facial, waxing, manicure, pedicure, makeup, threading, grooming", "home-service", [
         ("facial", "Facial", "Cleanup or facial at home.", "fixed", "799", 1, "0", 60, False, True, ["Facial with your choice of product"], []),
         ("waxing", "Waxing", "Arms and legs.", "fixed", "599", 1, "0", 60, False, True, ["Full arms and legs"], []),
     ]),
    ("moving", "Movers & Packers", "Movers", "moving", "parcel", "#f97316", "Shifting, packing and loading help.",
     "move, moving, movers, packers, shifting, relocation, loading, unloading, pack", "manpower-provider,home-service", [
         ("helpers", "Loading / unloading helpers", "Two helpers, by the hour.", "hourly", "399", 2, "0", 120, True, True, ["2 helpers"], ["Vehicle (book a Parcel mini truck)"]),
         ("house-shift", "House shifting", "Packing and moving; quoted after a survey.", "quote", None, 1, "0", 60, False, True, ["Survey and quote"], []),
     ]),
    ("gardening", "Gardening", "Gardener", "home", "leaf", "#22c55e", "Garden upkeep, plants and lawns.",
     "garden, gardener, plants, lawn, mowing, pots, trimming", "home-service", [
         ("upkeep", "Garden upkeep", "Weeding, trimming, watering (hourly).", "hourly", "249", 2, "0", 120, False, True, ["Weeding, trimming"], ["Plants, soil"]),
     ]),
    ("handyman", "Handyman", "Handyman", "home", "wrench", "#a855f7", "Small jobs around the house.",
     "handyman, odd jobs, hang, mount, curtain, tv mount, drill, small repair", "home-service,carpenter", [
         ("mounting", "Mounting & hanging", "Curtain rods, frames, TV wall mounts.", "hourly", "249", 1, "0", 60, True, True, ["Drilling and fixing"], ["Brackets, rods"]),
     ]),
]

# name, phone, category slug (main), extra categories, partner category, locality, radius, exp, skills, languages, about,
#   available now, hours preset, own prices {job slug: price}, verified
PROS = [
    ("Ramesh Kumar", "+91 90010 00001", "plumbing", [], "plumber", "Indiranagar", 8, 12, ["Leak detection", "Bathroom fittings", "Geyser connections"], ["Kannada", "Hindi", "English"],
     "Plumbing in Indiranagar and nearby since 2014; mostly leaks and bathroom fittings.", True, "long", {}, True),
    ("Shabbir Ahmed", "+91 90010 00002", "plumbing", ["handyman"], "plumber", "Koramangala", 7, 6, ["Drain cleaning", "Tap replacement"], ["Urdu", "Hindi", "Kannada"],
     "Quick fixes for taps, drains and toilets.", True, "day", {"tap-repair": "179"}, True),
    ("Venkatesh B", "+91 90010 00003", "plumbing", [], "plumber", "Jayanagar", 6, 18, ["Concealed piping", "Water tanks"], ["Kannada", "Tamil"],
     "18 years in residential plumbing.", False, "day", {}, True),
    ("Suresh Naik", "+91 90010 00004", "electrical", [], "electrician", "Indiranagar", 8, 9, ["Fan & light fitting", "MCB and wiring"], ["Kannada", "English"],
     "Licensed wireman; fans, lights and fault finding.", True, "long", {}, True),
    ("Arun Prakash", "+91 90010 00005", "electrical", ["handyman"], "electrician", "HSR Layout", 10, 4, ["Smart switches", "Inverter wiring"], ["Tamil", "English"],
     "Installs smart switches and inverters.", True, "day", {"fan-install": "229"}, False),
    ("Mohan Das", "+91 90010 00006", "carpentry", ["handyman"], "carpenter", "Koramangala", 8, 15, ["Modular furniture", "Door repair", "Assembly"], ["Hindi", "Kannada"],
     "Furniture repair and modular fitting.", True, "day", {}, True),
    ("Joseph Thomas", "+91 90010 00007", "carpentry", [], "carpenter", "Jayanagar", 7, 22, ["Custom wardrobes", "Polishing"], ["Malayalam", "English"],
     "Custom woodwork and wardrobes.", False, "weekdays", {}, True),
    ("Lakshmi R", "+91 90010 00008", "cleaning", [], "cleaning-service", "Indiranagar", 6, 7, ["Deep cleaning", "Kitchen degreasing"], ["Kannada", "Telugu"],
     "Home and kitchen cleaning with my own supplies.", True, "day", {}, True),
    ("Meena Pillai", "+91 90010 00009", "cleaning", ["laundry"], "cleaning-service", "Bellandur", 8, 5, ["Bathroom cleaning", "Sofa shampoo"], ["Malayalam", "Hindi", "English"],
     "Bathrooms and sofas a speciality.", True, "long", {"bathroom": "429"}, True),
    ("Kavya S", "+91 90010 00010", "laundry", [], "home-service", "HSR Layout", 6, 3, ["Wash & fold", "Steam ironing"], ["Kannada", "English"],
     "Laundry pickup in HSR and Koramangala.", True, "day", {}, True),
    ("Anita Sharma", "+91 90010 00011", "cook", [], "home-service", "Indiranagar", 6, 11, ["North Indian", "Party cooking"], ["Hindi", "English"],
     "North Indian home cooking; parties up to 30 guests.", False, "day", {}, True),
    ("Selvi M", "+91 90010 00012", "cook", [], "home-service", "Jayanagar", 5, 8, ["South Indian", "Tiffin"], ["Tamil", "Kannada"],
     "South Indian meals and tiffin.", True, "day", {}, False),
    ("Imran Khan", "+91 90010 00013", "ac", ["appliance"], "technician", "Koramangala", 10, 10, ["Split AC", "Gas charging", "Installation"], ["Hindi", "Urdu", "English"],
     "All brands of split and window ACs.", True, "long", {"ac-service": "449"}, True),
    ("Prakash Hegde", "+91 90010 00014", "appliance", ["ac"], "technician", "Indiranagar", 9, 14, ["Washing machines", "Refrigerators", "RO"], ["Kannada", "English"],
     "Washing machines, fridges and RO purifiers.", True, "day", {}, True),
    ("Rahul Jain", "+91 90010 00015", "device", [], "technician", "HSR Layout", 8, 6, ["Laptops", "Data recovery"], ["Hindi", "English"],
     "Laptop and desktop repairs at your place.", False, "day", {}, True),
    ("Gopal Reddy", "+91 90010 00016", "pest", [], "home-service", "Bellandur", 12, 9, ["Cockroach gel", "Termite"], ["Telugu", "Kannada"],
     "Odourless gel treatments; safe around kids and pets.", False, "weekdays", {}, True),
    ("Priya Nair", "+91 90010 00017", "beauty", [], "home-service", "Koramangala", 7, 8, ["Facials", "Waxing", "Bridal"], ["Malayalam", "English", "Hindi"],
     "Certified beautician; I bring my own kit.", True, "day", {}, True),
    ("Vikram Singh", "+91 90010 00018", "moving", [], "manpower-provider", "Bellandur", 15, 7, ["Packing", "Loading"], ["Hindi", "Kannada"],
     "Team of 4 for packing and shifting.", True, "long", {}, True),
    ("Basavaraj K", "+91 90010 00019", "gardening", [], "home-service", "Jayanagar", 8, 20, ["Lawns", "Terrace gardens"], ["Kannada"],
     "Terrace gardens and lawns.", False, "weekdays", {}, True),
    ("Naveen Rao", "+91 90010 00020", "painting", ["handyman"], "home-service", "Indiranagar", 10, 13, ["Interior painting", "Waterproofing"], ["Kannada", "Telugu", "English"],
     "Interior painting and damp proofing.", False, "day", {}, True),
    ("Farhan Qureshi", "+91 90010 00021", "handyman", ["electrical"], "home-service", "Koramangala", 8, 5, ["TV mounting", "Curtains", "Drilling"], ["Hindi", "English"],
     "Mounting, hanging and small fixes.", True, "long", {}, False),
]
HOURS = {
    "day": [(d, time(9), time(19)) for d in range(6)],
    "long": [(d, time(7), time(22)) for d in range(7)],
    "weekdays": [(d, time(9), time(18)) for d in range(5)],
}
# code, title, description, category slug or None, kind, value, max, min amount, first booking only, days left (negative = ended)
OFFERS = [
    ("First service: 15% off", "Up to ₹150 off your first Click. service.", None, "percent", "15", "150", "0", True, 30),
    ("AC service week: ₹100 off", "On AC jobs over ₹499.", "ac", "flat", "100", None, "499", False, 7),
    ("Cleaning: 10% off over ₹600", "Bathroom, kitchen and hourly cleaning.", "cleaning", "percent", "10", "120", "600", False, 14),
    ("Monsoon plumbing offer (ended)", "Ended offer kept for testing.", "plumbing", "flat", "50", None, "0", False, -5),
]


def _code() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [PARTNER_CODE_SEQUENCE])
        return f"{PARTNER_CODE_PREFIX}{cursor.fetchone()[0]:06d}"


def seed_professionals(log) -> None:
    from apps.partners.catalog import apply_catalog
    from apps.partners.models import PartnerType
    from apps.professionals.models import (
        ProviderAvailability, ProviderJobPrice, ProviderProfile, ProviderService, ServiceCategory, ServiceJob, ServiceOffer,
    )

    apply_catalog(PartnerType, PartnerCategory)  # Manpower & Services partners use the Services workspace
    cats, jobs = {}, {}
    for pos, (slug, name, prof, group, icon, accent, summary, syn, pcats, job_rows) in enumerate(CATALOG):
        cats[slug], _ = ServiceCategory.objects.update_or_create(slug=slug, defaults=dict(
            name=name, profession=prof, group=group, icon=icon, accent=accent, summary=summary, synonyms=syn, partner_categories=pcats,
            position=(pos + 1) * 10, is_active=True))
        for jpos, (js, jn, jd, pricing, price, min_h, insp, mins, inst, sched, inc, exc) in enumerate(job_rows):
            jobs[(slug, js)], _ = ServiceJob.objects.update_or_create(category=cats[slug], slug=js, defaults=dict(
                name=jn, description=jd, pricing=pricing, price=D(price) if price else None, min_hours=min_h, inspection_fee=D(insp),
                duration_minutes=mins, instant=inst, schedulable=sched, includes=inc, excludes=exc, position=jpos, is_active=True))
    now = timezone.now()
    for title, desc, cslug, kind, value, cap, minimum, first, days in OFFERS:
        ServiceOffer.objects.update_or_create(title=title, defaults=dict(
            description=desc, category=cats.get(cslug) if cslug else None, kind=kind, value=D(value), max_discount=D(cap) if cap else None,
            min_amount=D(minimum), first_booking_only=first, starts_at=now - timedelta(days=30), ends_at=now + timedelta(days=days), is_active=True))

    for i, (name, phone, main, extra, pcat, loc, radius, exp, skills, langs, about, avail, hours, prices, verified) in enumerate(PROS):
        email = f"pro.{name.lower().replace(' ', '.')}@click.local"
        user = User.objects.filter(email=email).first() or User.objects.create_user(email, None, full_name=name, phone=phone, phone_verified=True)
        m = PartnerMembership.objects.filter(user=user, role="owner").select_related("partner").first()
        category = PartnerCategory.objects.select_related("partner_type").get(slug=pcat)
        partner = m.partner if m else Partner.objects.create(partner_type=category.partner_type, category=category, business_name=name)
        if not m:
            PartnerMembership.objects.create(partner=partner, user=user, role="owner")
        partner.partner_code = partner.partner_code or _code()
        partner.status = Partner.Status.ACTIVE
        partner.is_available = avail
        partner.profile_completed_at = partner.profile_completed_at or now
        partner.save()
        PartnerProfile.objects.update_or_create(partner=partner, defaults={"contact_name": name, "details": {
            "service_types": [main], "experience_years": exp, "availability": "all_days" if hours == "long" else "weekdays"}})
        lat, lng = locality_point(loc, email)
        PartnerAddress.objects.update_or_create(partner=partner, is_primary=True, defaults={
            "line1": f"{loc} base", "city": "Bengaluru", "state": "Karnataka", "postal_code": "560001", "latitude": lat, "longitude": lng,
            "service_area": f"{loc} and nearby", "service_radius_km": radius})
        if verified and not PartnerVerification.objects.filter(partner=partner, status="approved").exists():
            PartnerVerification.objects.create(partner=partner, status="approved", submitted_at=now - timedelta(days=60), reviewed_at=now - timedelta(days=55),
                                               reviewer_note="Development seed: ID and address checked")
        if not partner.availability_events.exists():
            PartnerAvailabilityEvent.objects.create(partner=partner, is_available=avail, note="Development seed")
        pro, _ = ProviderProfile.objects.update_or_create(partner=partner, defaults=dict(
            category=cats[main], about=about, experience_years=exp, skills=skills, languages=langs, is_listed=True))
        for c in [main, *extra]:
            ProviderService.objects.get_or_create(provider=pro, category=cats[c])
        pro.hours.all().delete()
        ProviderAvailability.objects.bulk_create([ProviderAvailability(provider=pro, weekday=d, starts_at=a, ends_at=b) for d, a, b in HOURS[hours]])
        for js, price in prices.items():
            ProviderJobPrice.objects.update_or_create(provider=pro, job=jobs[(main, js)], defaults={"price": D(price)})
    log(f"services: {len(CATALOG)} categories, {sum(len(c[-1]) for c in CATALOG)} jobs, {len(PROS)} professionals (no photos: placeholders), "
        f"{len(OFFERS)} offers (1 ended)")


# --- job history: the only source of ratings and completed-job counts ----------------------------------------------------

NS = uuid.UUID("7a1d5e44-91b2-4f0e-b4c0-5e2d0c0de999")
COMMENTS = ["Fixed it quickly and explained what was wrong.", "On time and very neat.", "Good work, fair price.", "",
            "Polite and careful. Will book again.", "Took a bit longer than expected but did a proper job."]


def _history_booking(customer, pro, job, address, days, key, review=None, status="paid"):
    from apps.payments.models import Payment
    from apps.professionals.models import ServiceBooking, ServiceReview, ServiceStatusEvent

    if ServiceBooking.objects.filter(customer=customer, idempotency_key=key).exists():
        return 0
    at = timezone.now() - timedelta(days=days, hours=3)
    price = pro.prices.filter(job=job).values_list("price", flat=True).first() or job.price or D("800")
    hours = job.min_hours if job.pricing == "hourly" else None
    agreed = price * hours if hours else price
    tax = (agreed * D("0.18")).quantize(D("0.01"))
    b = ServiceBooking.objects.create(
        customer=customer, provider=pro, requested_provider=pro, category=job.category, job=job, mode="scheduled",
        scheduled_start=at, scheduled_end=at + timedelta(minutes=job.duration_minutes), status=status,
        address=address, lat=D(str(address.get("lat", "12.97"))), lng=D(str(address.get("lng", "77.64"))),
        description="Development seed job", pricing=job.pricing, unit_price=price if job.pricing != "quote" else None, hours=hours,
        agreed_amount=agreed, billed_hours=D(hours) if hours else None, tax=tax if status == "paid" else D("0"),
        total=(agreed + tax) if status == "paid" else None, payment_method="wallet" if status == "paid" else "",
        accepted_at=at - timedelta(days=1) if status != "cancelled" else None, started_at=at if status == "paid" else None,
        completed_at=at + timedelta(minutes=job.duration_minutes) if status == "paid" else None,
        paid_at=at + timedelta(minutes=job.duration_minutes + 5) if status == "paid" else None,
        cancelled_at=at - timedelta(hours=20) if status == "cancelled" else None, cancel_reason="Plans changed" if status == "cancelled" else "",
        idempotency_key=key)
    ServiceBooking.objects.filter(pk=b.pk).update(created_at=at - timedelta(days=2))
    path = {"paid": ["requested", "confirmed", "on_the_way", "arrived", "in_progress", "completed", "paid"],
            "cancelled": ["requested", "confirmed", "cancelled"], "confirmed": ["requested", "confirmed"]}[status]
    prev = ""
    for i, st in enumerate(path):
        ev = ServiceStatusEvent.objects.create(booking=b, from_status=prev, to_status=st, note="Development seed")
        ServiceStatusEvent.objects.filter(pk=ev.pk).update(created_at=at - timedelta(days=1) + timedelta(minutes=30 * i))
        prev = st
    if status == "paid":
        Payment.objects.create(service_booking=b, method="wallet", amount=b.total, currency=b.currency, status=Payment.Status.CAPTURED)
        if review:
            ServiceReview.objects.create(booking=b, customer=customer, provider=pro, overall=review[0], quality=review[0],
                                         behaviour=review[0], timeliness=max(1, review[0] - (days % 2)), comment=review[1])
    return 1


def seed_service_history(profile, log) -> None:
    from apps.professionals import lifecycle
    from apps.professionals.models import ProviderProfile, ServiceBooking, ServiceJob
    from apps.wishlists.models import WishlistItem

    from .showtime import VIEWERS, _viewer

    pros = {p.partner.business_name: p for p in ProviderProfile.objects.select_related("partner", "category")}
    if not pros:
        return
    made = 0
    viewers = [_viewer(n, loc) for n, loc in VIEWERS]
    jobs_by_cat = {}
    for j in ServiceJob.objects.filter(is_active=True).exclude(pricing="quote").select_related("category"):
        jobs_by_cat.setdefault(j.category_id, []).append(j)
    for k, (name, pro) in enumerate(sorted(pros.items())):
        n = 2 + (k * 7) % 9  # 2..10 past jobs, so counts and ratings differ
        for i in range(n):
            v = viewers[(k + i) % len(viewers)]
            job = jobs_by_cat[pro.category_id][i % len(jobs_by_cat[pro.category_id])]
            rating = [5, 5, 4, 5, 4, 3, 5][(k + i) % 7]
            review = (rating, COMMENTS[(k + i) % len(COMMENTS)]) if i % 3 != 2 else None
            made += _history_booking(v, pro, job, {"label": "home", "line1": "Dev address", "line2": "", "city": "Bengaluru"}, 3 + i * 4 + k % 3,
                                     uuid.uuid5(NS, f"{name}-{i}"), review)
    home = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
    snap = {**home.snapshot(), "lat": str(home.latitude), "lng": str(home.longitude)}
    plumb, clean, elec = pros.get("Ramesh Kumar"), pros.get("Lakshmi R"), pros.get("Suresh Naik")
    if plumb:
        made += _history_booking(profile, plumb, plumb.category.jobs.get(slug="tap-repair"), snap, 20, uuid.uuid5(NS, "test-1"),
                                 (5, "Fixed the kitchen tap in 20 minutes."))
        WishlistItem.objects.get_or_create(customer=profile, provider=plumb)
    if clean:
        made += _history_booking(profile, clean, clean.category.jobs.get(slug="bathroom"), snap, 9, uuid.uuid5(NS, "test-2"))
    if elec:
        made += _history_booking(profile, elec, elec.category.jobs.get(slug="switch"), snap, 4, uuid.uuid5(NS, "test-3"), status="cancelled")
    for p in pros.values():
        lifecycle.recompute(p.id)
    ServiceBooking.objects.filter(customer=profile, address_ref__isnull=True).update(address_ref=home)
    log(f"service history: {made} past jobs (paid, reviewed, cancelled); ratings and job counts recomputed from them")

