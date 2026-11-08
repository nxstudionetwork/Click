"""Profile summary: counts and balances for the signed-in customer's Profile page (no full lists)."""

from apps.rewards import services as rewards


def profile_summary(customer) -> dict:
    orders = customer.orders.count()
    bookings = customer.bookings.count()
    return {
        "activity": {"orders": orders, "bookings": bookings, "total": orders + bookings},
        "wishlist": customer.wishlist_items.count(),
        "addresses": customer.addresses.count(),
        "unread_notifications": customer.notifications.filter(read_at__isnull=True).count(),
        "rewards_balance": rewards.balance(customer)["balance"],
    }
