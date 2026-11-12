from .models import MUTABLE, Notification, NotificationPreference

IMPORTANT = {"payments", "wallet", "support"}


def notify(customer, category: str, title: str, body: str = "", link_path: str = "", priority: str = "") -> Notification | None:
    """Creates an in-app notification from a real backend event. Respects the customer's muted categories (never for
    payments, wallet, support or account/security notices)."""
    if link_path and not link_path.startswith("/"):
        raise ValueError("link_path must be an in-app path")
    if category in MUTABLE:
        pref = NotificationPreference.objects.filter(customer=customer).only("muted").first()
        if pref and category in pref.muted:
            return None
    priority = priority or ("important" if category in IMPORTANT and any(w in title.lower() for w in ("fail", "didn", "suspicious", "restricted")) else "normal")
    return Notification.objects.create(customer=customer, category=category, title=title[:120], body=body[:300], link_path=link_path,
                                       priority=priority)
