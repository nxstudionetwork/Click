"""A customer's saved stores, products, professionals, event teams/venues and event packages. Rows always belong to one customer."""

from django.db import models
from django.db.models import Q

from apps.catalog.models import Product
from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile
from apps.stores.models import Store


TARGETS = ("store", "product", "provider", "event_provider", "event_package")


def _exactly_one(fields) -> Q:
    out = Q()
    for f in fields:
        q = Q(**{f"{f}__isnull": False})
        for o in fields:
            if o != f:
                q &= Q(**{f"{o}__isnull": True})
        out |= q
    return out


class WishlistItem(BaseModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="wishlist_items")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    # Services: a saved professional ("My Professionals").
    provider = models.ForeignKey("professionals.ProviderProfile", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    # Events: a saved event team / venue, or a saved package.
    event_provider = models.ForeignKey("eventhub.EventProvider", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    event_package = models.ForeignKey("eventhub.EventPackage", on_delete=models.CASCADE, null=True, blank=True, related_name="+")


    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Exactly one target per row (new saveable entities add a column + extend this check).
            models.CheckConstraint(condition=_exactly_one(TARGETS), name="wishlists_exactly_one_target_v3"),
            models.UniqueConstraint(fields=["customer", "store"], condition=Q(store__isnull=False), name="wishlists_unique_store"),
            models.UniqueConstraint(fields=["customer", "product"], condition=Q(product__isnull=False), name="wishlists_unique_product"),
            models.UniqueConstraint(fields=["customer", "provider"], condition=Q(provider__isnull=False), name="wishlists_unique_provider"),
            models.UniqueConstraint(fields=["customer", "event_provider"], condition=Q(event_provider__isnull=False), name="wishlists_unique_event_provider"),
            models.UniqueConstraint(fields=["customer", "event_package"], condition=Q(event_package__isnull=False), name="wishlists_unique_event_package"),
        ]
