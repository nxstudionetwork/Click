"""
DEVELOPMENT MOCK DATA: the documented test customer and their activity.

History is created through the real domain services (cart, order placement,
status transitions, bookings, wallet, rewards, notifications), so every
relationship is exactly what production would produce. Each section runs only
once per customer; re-running the seed never duplicates history.
"""

import uuid
from datetime import timedelta
from decimal import Decimal as D

from django.db import transaction
from django.utils import timezone

from apps.bookings import services as booking_services
from apps.bookings.models import Booking
from apps.carts import services as cart_services
from apps.catalog.models import Product
from apps.core.api.exceptions import DomainError
from apps.customers.models import Address, CustomerProfile
from apps.notifications.models import Notification
from apps.orders import services as order_services
from apps.orders.models import Order, OrderStatus, OrderStatusEvent
from apps.stores.models import Store
from apps.support.models import SupportTicket
from apps.users.models import User
from apps.wallet.models import WalletTransaction
from apps.wishlists.models import WishlistItem

TEST_CUSTOMER = {
    "email": "test.customer@click.local",  # reserved .local domain: can never be a real inbox
    "full_name": "Click Test User",
    # US 555-01xx numbers are reserved for fiction. Add this number + a code of your choice as a
    # *test phone number* in Firebase Console → Authentication → Sign-in method → Phone.
    "phone": "+16505550101",
    "customer_code": "CLK-CS-TEST001",
    "password": "ClickDev@2026",  # development-only password; also usable via the normal login form
}
NS = uuid.UUID("6f1c2a52-6b4e-4c1e-9d43-0c11c0de5eed")  # deterministic idempotency keys for seeded actions

ADDRESSES = [
    ("home", "Click Test User", "+91 00000 00001", "Flat 4B, Test Residency, 12th Cross", "Indiranagar 2nd Stage", "Opposite the (fictional) Blue Door Cafe", "560038", True),
    ("work", "Click Test User", "+91 00000 00002", "Floor 7, Example Tech Park, Tower C", "Outer Ring Road, Bellandur", "", "560103", False),
    ("other", "Asha Test (Mum)", "+91 00000 00003", "No. 21, Sample Street", "Jayanagar 4th Block", "Near the park with the very long name used to test how landmarks wrap across multiple lines", "560011", False),
    ("other", "Test Friend", "+91 00000 00004", "Villa 9, Demo Gardens", "Whitefield", "", "560066", False),
]

# store slug, [(product, qty)], payment, final status, days ago, note
ORDERS = [
    ("saffron-smoke-biryani-house", [("Hyderabadi Chicken Biryani", 2), ("Paneer Tikka Biryani", 1)], "cash_on_delivery", "delivered", 41, ""),
    ("dosa-district", [("Ghee Roast Dosa", 2), ("Idli Vada Combo", 1)], "wallet", "delivered", 38, "Extra sambar please"),
    ("freshcart-daily", [("Bananas (Robusta)", 2), ("Toned Milk", 4), ("Greek Yogurt", 2)], "cash_on_delivery", "delivered", 35, ""),
    ("crust-coal-pizzeria", [("Margherita Classica", 1), ("Smoked Chicken Pesto", 1)], "cash_on_delivery", "cancelled", 33, ""),
    ("volt-electronics", [("Braided USB-C Cable 1.5m", 2), ("65W USB-C Charger", 1)], "wallet", "delivered", 30, ""),
    ("momo-mantra", [("Steamed Veg Momos (8)", 2), ("Chicken Jhol Momos (8)", 1)], "cash_on_delivery", "delivered", 27, "Less spicy"),
    ("pantry-point", [("Toor Dal", 2), ("Masala Peanuts", 3)], "cash_on_delivery", "delivered", 24, ""),
    ("butter-crumb-bakehouse", [("Sourdough Loaf", 1), ("Cinnamon Roll", 4)], "wallet", "cancelled", 21, ""),
    ("thread-loom", [("Linen Shirt — Sage", 1)], "cash_on_delivery", "delivered", 19, "Size L"),
    ("udupi-upahara", [("Mysore Masala Dosa", 2), ("Idli Vada Combo", 2)], "cash_on_delivery", "delivered", 16, ""),
    ("basil-lime-thai-kitchen", [("Green Curry with Jasmine Rice", 1), ("Tom Yum Soup", 1)], "wallet", "delivered", 13, ""),
    ("hearth-home-store", [("Glass Storage Jars (Set of 3)", 1)], "cash_on_delivery", "cancelled", 11, ""),
    ("stack-burger-lab", [("The Classic Stack", 2), ("Crispy Paneer Burger", 1)], "cash_on_delivery", "delivered", 8, ""),
    ("corner-kirana-express", [("Atta (Whole Wheat)", 1), ("Paneer", 2), ("Salted Butter", 1)], "cash_on_delivery", "delivered", 5, ""),
    ("taco-tierra", [("Loaded Bean Burrito", 1), ("Nachos Grande", 1)], "wallet", "out_for_delivery", 0, "Ring the bell twice"),
    ("stride-sports-co", [("Steel Water Bottle 1L", 1), ("Dri-fit Running Tee", 2)], "cash_on_delivery", "out_for_delivery", 0, ""),
    ("royal-rasoi", [("Butter Chicken", 1), ("Garlic Naan", 4)], "cash_on_delivery", "preparing", 0, ""),
    ("green-bowl-kitchen", [("Quinoa Power Bowl", 2)], "cash_on_delivery", "ready", 0, ""),
    ("midnight-mithai", [("Kesar Rasmalai (2 pc)", 2), ("Gulab Jamun Cheesecake", 1)], "wallet", "confirmed", 0, ""),
    ("brew-ritual-cafe", [("Cold Brew Tonic", 2), ("Almond Croissant", 2)], "cash_on_delivery", "placed", 0, ""),
]
PATH = [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]

TICKETS = [
    ("order", "Missing raita with biryani", "The raita wasn’t in the bag.", "resolved"),
    ("order", "Pizza order cancelled by mistake", "Can you restore it?", "closed"),
    ("payment", "Wallet refund not visible", "Refund for my bakery order — where is it?", "resolved"),
    ("delivery", "Delivery partner couldn’t find my gate", "Please add a note for next time.", "resolved"),
    ("account", "How do I change my phone number?", "My number will change next month.", "awaiting_customer"),
    ("order", "Received the wrong size shirt", "Ordered L, got M.", "in_progress"),
    ("payment", "Charged twice?", "I see two entries for one order (test ticket).", "resolved"),
    ("service", "When will rides launch in Whitefield?", "Excited to try it.", "closed"),
    ("order", "Momos were cold", "Arrived lukewarm.", "resolved"),
    ("delivery", "Order is late", "It’s past the estimated time.", "open"),
    ("other", "Feature request: dark mode", "Would love a dark theme.", "open"),
    ("account", "Delete my old work address", "Done it myself, ignore.", "closed"),
    ("order", "Taco order — please add extra salsa", "Sorry, forgot to add a note.", "open"),
    ("payment", "Can I pay with UPI online?", "Cash is inconvenient sometimes.", "awaiting_customer"),
    ("ride", "Ride booking question", "Will scheduled rides be supported?", "closed"),
    ("delivery", "Leave at the door", "Please don’t ring the bell after 10 PM.", "in_progress"),
    ("order", "Grocery item expiry date", "The yogurt expires tomorrow.", "resolved"),
    ("service", "Home cleaning availability", "Looking for weekend slots.", "open"),
    ("other", "A really long subject line to test how support request titles wrap in the list on small phones", "Testing long content.", "open"),
    ("order", "Thank you!", "Just wanted to say the dosa was amazing.", "closed"),
]

WISHLIST_STORES = ["dosa-district", "sushi-sakura-bar", "butter-crumb-bakehouse", "freshcart-daily", "volt-electronics",
                   "thread-loom", "basil-lime-thai-kitchen", "paperback-lane", "night-owl-shawarma", "stride-sports-co"]
WISHLIST_PRODUCTS = [("volt-electronics", "Wireless Earbuds Pro"), ("volt-electronics", "Bluetooth Speaker Mini"), ("thread-loom", "Block-print Kurta"),
                     ("hearth-home-store", "Cast Iron Skillet 10\""), ("paperback-lane", "The Startup Playbook"), ("stride-sports-co", "Featherlight Running Shoes"),
                     ("stride-sports-co", "Adjustable Dumbbells (Pair)"), ("freshcart-daily", "Alphonso Mangoes"), ("orchard-co-organics", "Hass Avocado"),
                     ("sushi-sakura-bar", "Salmon Nigiri (6)")]


def _key(label: str) -> uuid.UUID:
    return uuid.uuid5(NS, label)


def ensure_test_customer(log) -> CustomerProfile:
    user = User.objects.filter(email=TEST_CUSTOMER["email"]).first()
    if not user:
        user = User.objects.create_user(TEST_CUSTOMER["email"], TEST_CUSTOMER["password"], full_name=TEST_CUSTOMER["full_name"],
                                        phone=TEST_CUSTOMER["phone"], phone_verified=True)
    else:
        user.full_name, user.phone, user.phone_verified, user.is_active = TEST_CUSTOMER["full_name"], TEST_CUSTOMER["phone"], True, True
        user.set_password(TEST_CUSTOMER["password"])
        user.save()
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    if profile.customer_code != TEST_CUSTOMER["customer_code"]:
        CustomerProfile.objects.filter(pk=profile.pk).update(customer_code=TEST_CUSTOMER["customer_code"])
        profile.refresh_from_db()
    for label, name, phone, line1, line2, landmark, pin, default in ADDRESSES:
        Address.objects.get_or_create(customer=profile, line1=line1, defaults=dict(
            label=label, recipient_name=name, phone=phone, line2=line2, landmark=landmark, city="Bengaluru",
            state="Karnataka", postal_code=pin, country="IN", is_default=default and not profile.addresses.filter(is_default=True).exists()))
    log(f"test customer: {user.email} ({profile.customer_code}), {profile.addresses.count()} addresses")
    return profile


def _shift(order: Order, days: int) -> None:
    if days <= 0:
        return
    at = timezone.now() - timedelta(days=days, hours=len(order.number) % 5)
    Order.objects.filter(pk=order.pk).update(created_at=at, estimated_delivery_at=at + timedelta(minutes=45),
                                             delivered_at=at + timedelta(minutes=40) if order.delivered_at else None,
                                             cancelled_at=at + timedelta(minutes=6) if order.cancelled_at else None)
    for i, ev in enumerate(OrderStatusEvent.objects.filter(order=order).order_by("created_at")):
        OrderStatusEvent.objects.filter(pk=ev.pk).update(created_at=at + timedelta(minutes=8 * i))
    order.payments.update(created_at=at)


def seed_wallet(profile, log) -> None:
    if WalletTransaction.objects.filter(customer=profile).exists():
        return
    for amount, desc in [("10000.00", "Development test credit (DEVELOPMENT MOCK DATA)"), ("250.00", "Welcome to Click credit"), ("100.00", "Sorry-for-the-delay credit")]:
        WalletTransaction.objects.create(customer=profile, kind=WalletTransaction.Kind.PROMO, amount=D(amount), description=desc)
    log("wallet: 3 promotional credits")


def seed_orders(profile, log) -> None:
    if profile.orders.exists():
        return
    address = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
    cart = cart_services.get_or_create_cart(profile)
    made = 0
    for i, (slug, items, method, final, days, note) in enumerate(ORDERS):
        store = Store.objects.get(slug=slug)
        with transaction.atomic():
            cart_services.clear_cart(cart)
            for name, qty in items:
                cart_services.add_item(profile, Product.objects.get(store=store, name=name).id, qty)
            order, _ = order_services.place_order(customer=profile, address_id=address.id, payment_method=method,
                                                  idempotency_key=_key(f"order-{i}"), customer_note=note)
            if final == "cancelled":
                order_services.cancel_by_customer(order, user=profile.user, reason="Changed my mind (seed)")
            elif final != "placed":
                for step in PATH[: PATH.index(final) + 1]:
                    order = order_services.transition_order(order, step)
            order.refresh_from_db()
            _shift(order, days)
            made += 1
    cart_services.clear_cart(cart)
    log(f"orders: {made} orders placed through the real checkout service")


def seed_bookings(profile, log) -> None:
    if profile.bookings.exists():
        return
    shows, seen = [], set()
    for show in booking_services.bookable_shows().filter(starts_at__gte=timezone.now() + timedelta(hours=3)).order_by("starts_at"):
        if show.event_id in seen:
            continue
        seen.add(show.event_id)
        shows.append(show)
        if len(shows) == 20:
            break
    made = 0
    for i, show in enumerate(shows):
        seats = [f"{'DEFG'[i % 4]}{3 + (i % 8)}", f"{'DEFG'[i % 4]}{4 + (i % 8)}"][: 1 + (i % 3 != 0)]
        try:
            booking, _ = booking_services.create_booking(customer=profile, show_id=show.id, seats=seats,
                                                         payment_method="wallet" if i % 3 == 0 else "pay_at_venue", idempotency_key=_key(f"booking-{i}"))
            if i in (4, 9, 14, 18):
                booking_services.cancel_booking(booking)
            Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(hours=6 + i * 7))
            made += 1
        except DomainError as e:  # e.g. seats taken by another dev user: skip, never fake
            log(f"  skipped booking {i}: {e.detail}")
    log(f"bookings: {made} bookings created through the real booking service")


def seed_cart(profile, log) -> None:
    cart = cart_services.get_or_create_cart(profile)
    if cart.items.exists():
        return
    store = Store.objects.get(slug="momo-mantra")
    for name, qty in [("Pan-fried Paneer Momos (8)", 1), ("Chilli Garlic Noodles", 1)]:
        cart_services.add_item(profile, Product.objects.get(store=store, name=name).id, qty)
    log("cart: 2 items from Momo Mantra")


def seed_wishlist(profile, log) -> None:
    for slug in WISHLIST_STORES:
        WishlistItem.objects.get_or_create(customer=profile, store=Store.objects.get(slug=slug))
    for slug, name in WISHLIST_PRODUCTS:
        WishlistItem.objects.get_or_create(customer=profile, product=Product.objects.get(store__slug=slug, name=name))
    log(f"wishlist: {WishlistItem.objects.filter(customer=profile).count()} saved items")


def seed_support(profile, log) -> None:
    if SupportTicket.objects.filter(customer=profile).exists():
        return
    orders = list(profile.orders.order_by("created_at"))
    for i, (category, subject, message, status) in enumerate(TICKETS):
        t = SupportTicket.objects.create(customer=profile, category=category, subject=subject, message=message, status=status,
                                         order=orders[i % len(orders)] if category == "order" and orders else None,
                                         resolved_at=timezone.now() - timedelta(days=i) if status in ("resolved", "closed") else None)
        SupportTicket.objects.filter(pk=t.pk).update(created_at=timezone.now() - timedelta(days=i * 2, hours=i))
    log(f"support: {len(TICKETS)} tickets")


def finalize_notifications(profile, log) -> None:
    qs = Notification.objects.filter(customer=profile).order_by("-created_at")
    ids = list(qs.values_list("id", flat=True))
    # Keep the newest 8 unread so the badge and unread styles are testable; older ones read.
    Notification.objects.filter(id__in=ids[8:], read_at__isnull=True).update(read_at=timezone.now())
    log(f"notifications: {len(ids)} (8 newest unread)")


def seed_test_customer(log) -> CustomerProfile:
    profile = ensure_test_customer(log)
    seed_wallet(profile, log)
    seed_orders(profile, log)
    seed_bookings(profile, log)
    seed_cart(profile, log)
    seed_wishlist(profile, log)
    seed_support(profile, log)
    finalize_notifications(profile, log)
    return profile
