from .models import Notification


def notify(customer, category: str, title: str, body: str = "", link_path: str = "") -> Notification:
    if link_path and not link_path.startswith("/"):
        raise ValueError("link_path must be an in-app path")
    return Notification.objects.create(customer=customer, category=category, title=title, body=body, link_path=link_path)
