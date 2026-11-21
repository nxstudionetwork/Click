"""Shopping API shapes (camelCased by the API renderer). Mirrored in packages/api/src/types.ts (Shop* types)."""

from collections import OrderedDict

from apps.catalog.images import image_urls
from apps.catalog.pricing import attach_deals, price_of

from .listings import badges_for, best_seller_ids, trending_scores


def money(v) -> str | None:
    return None if v is None else f"{v:.2f}"


def seller_brief(store) -> dict:
    return {"id": str(store.id), "slug": store.slug, "name": store.name, "is_verified": store.verified_at is not None,
            "rating": float(store.rating_average) if store.rating_count else None, "rating_count": store.rating_count,
            "city": store.city, "is_open": store.is_open}


def deal_brief(deal) -> dict | None:
    if deal is None:
        return None
    return {"kind": deal.kind, "label": deal.get_kind_display(), "percent_off": deal.percent_off, "ends_at": deal.ends_at.isoformat(),
            "remaining": deal.remaining}


def _image(p, request=None) -> dict | None:
    imgs = list(p.images.all())
    if imgs:
        return image_urls(imgs[0], request)
    if p.image_url:
        return {"src": p.image_url, "src_set": "", "width": None, "height": None, "alt": p.name}
    return None


def cards(products, request=None, reasons: dict | None = None) -> list[dict]:
    """Product cards for any list. Loads deals and badge signals once for the whole list."""
    products = list(products)
    attach_deals(products)
    trending, best = trending_scores(), best_seller_ids()
    out = []
    for p in products:
        variants = [v for v in p.variants.all() if v.is_active]
        price = price_of(p)
        in_stock = any(v.in_stock for v in variants) if variants else p.in_stock
        prices = {v.price for v in variants}
        out.append({
            "id": str(p.id), "name": p.name, "brand": p.brand_ref.name if p.brand_ref_id else p.brand,
            "brand_slug": p.brand_ref.slug if p.brand_ref_id else None,
            "category": p.shop_category.name if p.shop_category_id else None,
            "category_slug": p.shop_category.slug if p.shop_category_id else None,
            "category_icon": (p.shop_category.icon or (p.shop_category.parent.icon if p.shop_category.parent_id else "")) if p.shop_category_id else "",
            "image": _image(p, request),
            "price": money(price.price), "reference_price": money(price.reference), "discount_percent": price.discount_percent,
            "from_price": len(prices) > 1,
            "rating": float(p.rating_average) if p.rating_count else None, "rating_count": p.rating_count,
            "badges": badges_for(p, trending=trending, best=best),
            "deal": deal_brief(price.deal),
            "in_stock": in_stock and p.is_available, "has_variants": bool(variants),
            "seller": {"name": p.store.name, "slug": p.store.slug, "is_verified": p.store.verified_at is not None},
            "free_delivery_above": money(p.store.free_delivery_above), "cod_available": p.is_cod_available and p.store.cod_enabled,
            "reason": (reasons or {}).get(p.id),
        })
    return out


def campaign(c) -> dict:
    return {"id": str(c.id), "kind": c.kind, "eyebrow": c.eyebrow, "title": c.title, "subtitle": c.subtitle, "image_url": c.image_url,
            "cta_label": c.cta_label, "cta_path": c.cta_path, "ends_at": c.ends_at.isoformat()}


def category(c, count: int | None = None) -> dict:
    return {"id": str(c.id), "slug": c.slug, "name": c.name, "description": c.description, "image_url": c.image_url,
            "icon": c.icon or (c.parent.icon if c.parent_id else ""), "parent_slug": c.parent.slug if c.parent_id else None,
            "product_count": count}


def review(r) -> dict:
    first = (r.customer.user.full_name or "Click customer").split()[0]
    return {"id": str(r.id), "rating": r.rating, "title": r.title, "body": r.body, "variant_label": r.variant_label,
            "verified_purchase": r.verified_purchase, "author": first, "created_at": r.created_at.isoformat(),
            "edited": (r.updated_at - r.created_at).total_seconds() > 60}


def variant_axes(variants) -> list[dict]:
    """[{name: "Color", values: ["Black", "White"]}] in the order the seller listed them."""
    from apps.catalog.models import ProductVariant

    axes: OrderedDict = OrderedDict()
    for v in sorted(variants, key=lambda v: v.position):
        for k, val in (v.options or {}).items():
            axes.setdefault(k, [])
            if val not in axes[k]:
                axes[k].append(val)
    return [{"name": k, "values": axes[k]} for k in ProductVariant.ordered_axes(axes)]


def variant(v, product) -> dict:
    p = price_of(product, v)
    return {"id": str(v.id), "options": v.options, "label": v.label, "price": money(p.price), "reference_price": money(p.reference),
            "discount_percent": p.discount_percent, "in_stock": v.in_stock,
            "low_stock": v.stock_quantity is not None and 0 < v.stock_quantity <= 5}
