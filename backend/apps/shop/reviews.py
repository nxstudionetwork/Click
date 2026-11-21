"""
Product reviews. Only customers with a delivered order containing the product can review it (verified purchase),
once per product; they can edit or delete their own review. Moderation hides a review without deleting it.
The product's rating is always recomputed from published reviews in the same transaction.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count

from apps.activity.services import record
from apps.catalog.models import Product
from apps.core.api.exceptions import ConflictError, DomainError
from apps.orders.models import OrderItem, OrderStatus

from .models import ProductReview


def purchase_of(customer, product):
    return (OrderItem.objects.filter(order__customer=customer, order__status=OrderStatus.DELIVERED, product=product)
            .select_related("order").order_by("-order__delivered_at").first())


def review_problem(customer, product) -> str | None:
    if purchase_of(customer, product) is None:
        return "You can review products you've bought and received on Click."
    return None


def recompute(product_id) -> None:
    agg = ProductReview.objects.filter(product_id=product_id, status=ProductReview.Status.PUBLISHED).aggregate(a=Avg("rating"), n=Count("id"))
    avg = Decimal(agg["a"] or 0).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    Product.objects.filter(pk=product_id).update(rating_average=avg, rating_count=agg["n"])


@transaction.atomic
def save_review(customer, product, *, rating: int, title: str = "", body: str = "", create: bool) -> ProductReview:
    Product.objects.select_for_update().filter(pk=product.pk).first()
    existing = ProductReview.objects.filter(product=product, customer=customer).first()
    if create:
        if existing:
            raise ConflictError("You've already reviewed this product. Edit your review instead.", code="review_exists")
        item = purchase_of(customer, product)
        if item is None:
            raise DomainError(review_problem(customer, product), code="review_not_allowed", status_code=403)
        review = ProductReview.objects.create(product=product, customer=customer, order_item=item, rating=rating,
                                              title=title.strip(), body=body.strip(), variant_label=item.options_summary[:120])
        record(customer, "product.reviewed", {"rating": rating}, obj=product)
    else:
        if existing is None:
            raise DomainError("You haven't reviewed this product yet.", code="review_not_found", status_code=404)
        existing.rating, existing.title, existing.body = rating, title.strip(), body.strip()
        existing.save(update_fields=["rating", "title", "body", "updated_at"])
        review = existing
    recompute(product.pk)
    return review


@transaction.atomic
def delete_review(customer, product) -> None:
    deleted, _ = ProductReview.objects.filter(product=product, customer=customer).delete()
    if not deleted:
        raise DomainError("You haven't reviewed this product.", code="review_not_found", status_code=404)
    recompute(product.pk)
