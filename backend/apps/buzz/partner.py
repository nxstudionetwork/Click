"""
Click. Buzz for partners: create, review, schedule, pause, archive and measure promotional posts.

Rules enforced here (never only in the app):
- A post's action leads to one of the partner's *own* live Click listings (`listings`). Optional product and offer
  must belong to that listing's store. Nothing links outside Click, so customers still order/book through Click.
- Every post is reviewed by Click before customers see it; editing a reviewed post sends it back to review.
- Media is validated and re-encoded (photos → WebP renditions) and kept in media storage, never in the database.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from apps.core.api.exceptions import ConflictError, DomainError
from apps.partners.models import Partner

from .models import BuzzEvent, BuzzMedia, BuzzPost

MAX_MEDIA = 4
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_PENDING_UPLOADS = 20
MAX_RUN = timedelta(days=90)
IMAGE_WIDTHS = (480, 1080)
VIDEO_TYPES = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
CTA_LABEL = {
    "order": "Order now", "view_menu": "View menu", "shop": "Shop now", "book": "Book now", "book_service": "Book service",
    "book_tickets": "Book tickets", "book_ride": "Book a ride", "send_parcel": "Send a parcel", "explore": "Explore",
    "view": "View", "get_offer": "Get offer",
}
THEME = {"restaurant": "food", "store": "shopping", "pharmacy": "shopping", "hotel": "hotels", "services": "services",
         "events": "events", "cinema": "movies", "driver": "ride", "parcel": "parcel", "travel": "travel",
         "experiences": "events"}


def partner_mode(partner: Partner) -> str:
    from apps.partners.services import configuration_for

    return configuration_for(partner.category)["home"].get("mode", "upcoming")


def can_publish(partner: Partner) -> bool:
    return partner.status in (Partner.Status.VERIFIED, Partner.Status.ACTIVE)


# --- what a post can link to -------------------------------------------------------------------------------------

def listings(partner: Partner) -> list[dict]:
    """The partner's own customer-facing Click listings, each with the actions a post may use. Only live ones."""
    from apps.stores.models import Store, StoreType

    out: list[dict] = []
    stores = Store.objects.filter(partner_link__partner=partner, status=Store.Status.ACTIVE)
    for s in stores:
        if s.store_type == StoreType.RESTAURANT:
            link, ctas = f"/stores/{s.slug}", ["order", "view_menu", "get_offer"]
        elif s.store_type == StoreType.GROCERY:
            link, ctas = f"/groceries/store/{s.slug}", ["shop", "get_offer"]
        elif s.store_type == StoreType.PHARMACY:
            link, ctas = "/pharma", ["shop"]
        else:
            link, ctas = f"/stores/{s.slug}", ["shop", "get_offer"]
        out.append({"type": "store", "id": str(s.id), "title": s.name, "link": link, "ctas": ctas, "handle": s.slug,
                    "store_type": s.store_type})
    for attr, typ, path, ctas in (("hotel", "hotel", "/hotels/{}", ["book", "view"]),
                                  ("event_provider", "event_provider", "/events/providers/{}", ["book", "view"]),
                                  ("pro", "professional", "/services/pro/{}", ["book_service", "view"])):
        obj = getattr(partner, attr, None)  # reverse one-to-one: None when the partner has no such listing
        if obj is not None and obj.is_listed:
            out.append({"type": typ, "id": str(obj.id), "title": partner.business_name, "link": path.format(obj.id), "ctas": ctas})
    if partner.venue_links.exists():
        out.append({"type": "showtime", "id": "", "title": f"{partner.business_name} shows", "link": "/showtime", "ctas": ["book_tickets"]})
    mode = partner_mode(partner)
    if mode == "driver":
        out.append({"type": "ride", "id": "", "title": "Click rides", "link": "/rides", "ctas": ["book_ride"]})
    elif mode == "parcel":
        out.append({"type": "parcel", "id": "", "title": "Click parcels", "link": "/parcels", "ctas": ["send_parcel"]})
    elif mode == "travel" and partner.travel_operators.exists():
        out.append({"type": "travel", "id": "", "title": "Click travel", "link": "/travel", "ctas": ["explore"]})
    for x in out:
        x.setdefault("handle", slugify(partner.business_name)[:40] or partner.partner_code.lower())
    return out


def _find_listing(partner: Partner, typ: str, pk: str) -> dict | None:
    return next((x for x in listings(partner) if x["type"] == typ and x["id"] == (pk or "")), None)


def attachables(partner: Partner) -> dict:
    """Products and live offers of the partner's own stores, for the composer."""
    from apps.catalog.models import Product
    from apps.stores.models import StoreType
    from apps.stores.views import active_offers

    stores = [x for x in listings(partner) if x["type"] == "store" and x["store_type"] in (StoreType.RESTAURANT, StoreType.RETAIL)]
    ids = [x["id"] for x in stores]
    products = Product.objects.filter(store_id__in=ids, is_active=True).order_by("name")[:500]
    offers = active_offers().filter(store__partner_link__partner=partner)
    return {
        "products": [{"id": str(p.id), "store_id": str(p.store_id), "name": p.name, "price": f"{p.price:.2f}", "available": p.is_available}
                     for p in products],
        "offers": [{"id": str(o.id), "store_id": str(o.store_id), "title": o.title,
                    "ends_at": o.ends_at.isoformat() if o.ends_at else None} for o in offers],
    }


# --- status ------------------------------------------------------------------------------------------------------

def display_status(p: BuzzPost, now=None) -> str:
    now = now or timezone.now()
    if p.status != BuzzPost.Status.APPROVED:
        return p.status
    if p.expires_at and p.expires_at <= now:
        return "expired"
    if p.publish_at and p.publish_at > now:
        return "scheduled"
    return "live"


STATUS_LABEL = {"draft": "Draft", "in_review": "In review", "live": "Live", "scheduled": "Scheduled", "expired": "Expired",
                "paused": "Paused", "rejected": "Not approved", "removed": "Removed by Click", "archived": "Archived"}
ACTIONS = {
    "draft": ["edit", "submit", "delete"],
    "in_review": ["edit", "withdraw", "delete"],
    "live": ["edit", "pause", "archive", "delete"],
    "scheduled": ["edit", "pause", "archive", "delete"],
    "paused": ["edit", "resume", "archive", "delete"],
    "expired": ["edit", "archive", "delete"],
    "rejected": ["edit", "delete"],
    "removed": ["delete"],
    "archived": ["restore", "delete"],
}


def live_posts(audience: str | None = BuzzPost.Audience.PUBLIC):
    now = timezone.now()
    qs = BuzzPost.objects.filter(
        status=BuzzPost.Status.APPROVED, partner__status__in=(Partner.Status.VERIFIED, Partner.Status.ACTIVE),
    ).filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now), Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    if audience:
        qs = qs.filter(audience=audience)
    return qs.select_related("partner", "product", "store_offer").prefetch_related("media")


# --- media -------------------------------------------------------------------------------------------------------

def media_url(m: BuzzMedia, width: int | None = None) -> str:
    if m.kind == BuzzMedia.Kind.VIDEO:
        return default_storage.url(m.file) if m.file else ""
    r = m.renditions or {}
    if not r:
        return ""
    key = str(width) if width and str(width) in r else str(max(int(k) for k in r))
    return default_storage.url(r[key])


def media_dict(m: BuzzMedia) -> dict:
    return {"id": str(m.id), "kind": m.kind, "url": media_url(m), "thumb": media_url(m, IMAGE_WIDTHS[0]),
            "width": m.width, "height": m.height, "bytes": m.bytes}


def _video_type(head: bytes) -> str:
    if head[4:8] == b"ftyp":
        return "video/quicktime" if head[8:10] == b"qt" else "video/mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return ""


def upload_media(partner: Partner, upload) -> BuzzMedia:
    from apps.catalog.images import encode_renditions

    if upload is None:
        raise DomainError("Choose a photo or video to upload.", code="file_required")
    if BuzzMedia.objects.filter(partner=partner, post__isnull=True).count() >= MAX_PENDING_UPLOADS:
        raise ConflictError("Finish or discard your current drafts before uploading more.", code="too_many_uploads")
    head = upload.read(16)
    upload.seek(0)
    vtype = _video_type(head)
    stem = f"buzz/{partner.id}/{uuid.uuid4().hex}"
    if vtype:
        if upload.size > MAX_VIDEO_BYTES:
            raise DomainError("Videos must be 25 MB or smaller. Keep it short (under a minute).", code="video_too_large")
        path = default_storage.save(f"{stem}.{VIDEO_TYPES[vtype]}", upload)
        return BuzzMedia.objects.create(partner=partner, kind=BuzzMedia.Kind.VIDEO, file=path, content_type=vtype, bytes=upload.size)
    renditions, w, h = encode_renditions(upload, stem, widths=IMAGE_WIDTHS)
    total = sum(default_storage.size(p) for p in renditions.values())
    return BuzzMedia.objects.create(partner=partner, kind=BuzzMedia.Kind.IMAGE, renditions=renditions, content_type="image/webp",
                                    width=w, height=h, bytes=total)


def delete_media_files(m: BuzzMedia) -> None:
    for path in [*(m.renditions or {}).values(), m.file]:
        if path:
            default_storage.delete(path)


def discard_media(partner: Partner, media_id) -> None:
    m = BuzzMedia.objects.filter(partner=partner, pk=media_id).first()
    if m is None:
        raise DomainError("That file wasn't found.", code="not_found", status_code=404)
    if m.post_id and m.post.status not in (BuzzPost.Status.DRAFT, BuzzPost.Status.REJECTED):
        raise ConflictError("Edit the post to change its media.", code="media_in_use")
    delete_media_files(m)
    m.delete()


def cleanup_unused_media(older_than=timedelta(days=1)) -> int:
    """Uploads never attached to a post (abandoned composer). Run by click_jobs."""
    n = 0
    for m in BuzzMedia.objects.filter(post__isnull=True, created_at__lt=timezone.now() - older_than):
        delete_media_files(m)
        m.delete()
        n += 1
    return n


# --- posts -------------------------------------------------------------------------------------------------------

def _dt(value, field: str):
    if value in (None, ""):
        return None
    d = parse_datetime(str(value))
    if d is None:
        raise DomainError("Use a valid date and time.", code="invalid", details={field: ["Use a valid date and time."]})
    return d if timezone.is_aware(d) else timezone.make_aware(d)


def _clean(partner: Partner, data: dict, post: BuzzPost | None) -> dict:
    """Validate the editable fields. Partial updates keep the post's current values."""
    from apps.catalog.models import Product
    from apps.stores.views import active_offers

    def val(key, default=""):
        if key in data:
            return data[key]
        return getattr(post, key) if post is not None else default

    errors: dict[str, list[str]] = {}
    headline = str(val("headline") or "").strip()
    caption = str(val("caption") or "").strip()
    kind = val("kind", BuzzPost.Kind.UPDATE)
    audience = val("audience", BuzzPost.Audience.PUBLIC)
    if not headline:
        errors["headline"] = ["Add a short headline."]
    elif len(headline) > 80:
        errors["headline"] = ["Keep the headline to 80 characters."]
    if len(caption) > 600:
        errors["caption"] = ["Keep the caption to 600 characters."]
    if kind not in BuzzPost.Kind.values:
        errors["kind"] = ["Choose what this post is about."]
    if audience not in BuzzPost.Audience.values:
        errors["audience"] = ["Choose who can see it."]

    target_type, target_id, cta = str(val("target_type") or ""), str(val("target_id") or ""), str(val("cta") or "")
    listing = _find_listing(partner, target_type, target_id) if target_type else None
    if target_type and listing is None:
        errors["target_type"] = ["Choose one of your live Click listings."]
    if audience == BuzzPost.Audience.PUBLIC and not target_type:
        errors["target_type"] = ["Choose where the button takes customers."]
    if listing and cta not in listing["ctas"]:
        errors["cta"] = ["Choose a button for this listing."]

    product_id = data["product_id"] if "product_id" in data else (post.product_id if post else None)
    product = None
    if product_id:
        product = Product.objects.filter(pk=product_id, store__partner_link__partner=partner, is_active=True).first()
        if product is None or not listing or listing["type"] != "store" or str(product.store_id) != listing["id"]:
            errors["product_id"] = ["Choose an item from the store this post links to."]
    offer = None
    offer_id = data.get("offer_id") if "offer_id" in data else (post.store_offer_id if post else None)
    if offer_id:
        offer = active_offers().filter(pk=offer_id, store__partner_link__partner=partner).first()
        if offer is None or not listing or str(offer.store_id) != listing["id"]:
            errors["offer_id"] = ["Choose a live offer from the store this post links to."]
    if kind == BuzzPost.Kind.OFFER and not offer:
        errors.setdefault("offer_id", ["An offer post needs one of your live offers. Create the offer first."])
    if cta == "get_offer" and not offer:
        errors.setdefault("offer_id", ["Attach the offer this button leads to."])

    now = timezone.now()
    publish_at = _dt(data["publish_at"], "publish_at") if "publish_at" in data else (post.publish_at if post else None)
    expires_at = _dt(data["expires_at"], "expires_at") if "expires_at" in data else (post.expires_at if post else None)
    start = max(publish_at or now, now)
    if expires_at is None:
        errors["expires_at"] = ["Choose how long the post runs."]
    elif expires_at <= start:
        errors["expires_at"] = ["The end must be after the start."]
    elif expires_at - start > MAX_RUN:
        errors["expires_at"] = ["A post can run for up to 90 days."]
    if offer and offer.ends_at and expires_at and expires_at > offer.ends_at:
        errors.setdefault("expires_at", [f"The offer ends {timezone.localtime(offer.ends_at):%d %b, %I:%M %p}; end the post by then."])

    media_ids = data.get("media_ids")
    media: list[BuzzMedia] | None = None
    if media_ids is not None:
        if not isinstance(media_ids, list) or len(media_ids) > MAX_MEDIA:
            errors["media_ids"] = [f"Add up to {MAX_MEDIA} photos or videos."]
        else:
            found = {str(m.id): m for m in BuzzMedia.objects.filter(partner=partner, pk__in=media_ids)
                     .filter(Q(post__isnull=True) | Q(post=post) if post else Q(post__isnull=True))}
            if len(found) != len(set(map(str, media_ids))):
                errors["media_ids"] = ["Some media couldn’t be found. Upload it again."]
            else:
                media = [found[str(i)] for i in media_ids]
                if sum(m.kind == BuzzMedia.Kind.VIDEO for m in media) > 1:
                    errors["media_ids"] = ["Add at most one video per post."]
    if errors:
        raise DomainError("Please check the highlighted fields.", code="validation_error", details=errors)
    return {"headline": headline, "caption": caption, "kind": kind, "audience": audience, "target_type": target_type,
            "target_id": target_id, "cta": cta, "product": product, "store_offer": offer, "publish_at": publish_at,
            "expires_at": expires_at, "_media": media}


@transaction.atomic
def save_post(partner: Partner, data: dict, post: BuzzPost | None = None, submit: bool = False) -> BuzzPost:
    if post is not None:
        post = BuzzPost.objects.select_for_update().get(pk=post.pk, partner=partner)
        if display_status(post) in ("removed", "archived"):
            raise ConflictError("This post can’t be edited.", code="not_editable")
    fields = _clean(partner, data, post)
    media = fields.pop("_media")
    reviewed = post is not None and post.status not in (BuzzPost.Status.DRAFT, BuzzPost.Status.REJECTED)
    post = post or BuzzPost(partner=partner)
    for k, v in fields.items():
        setattr(post, k, v)
    if submit or reviewed:
        _require_publishable(partner)
        # Anything customers might see is checked again by Click.
        post.status, post.submitted_at, post.review_note = BuzzPost.Status.IN_REVIEW, timezone.now(), ""
    post.save()
    if media is not None:
        keep = {m.id for m in media}
        for old in post.media.exclude(pk__in=keep):
            delete_media_files(old)
            old.delete()
        for i, m in enumerate(media):
            m.post, m.position = post, i
            m.save(update_fields=["post", "position", "updated_at"])
    return post


def _require_publishable(partner: Partner) -> None:
    if not can_publish(partner):
        raise ConflictError("Click needs to verify your account before your posts can go live.", code="partner_not_verified")
    if not listings(partner):
        raise ConflictError("You need a live Click listing before you can post to Buzz.", code="no_listing")


@transaction.atomic
def act(partner: Partner, post_id, action: str) -> BuzzPost | None:
    post = BuzzPost.objects.select_for_update().filter(partner=partner, pk=post_id).first()
    if post is None:
        raise DomainError("That post wasn't found.", code="not_found", status_code=404)
    state = display_status(post)
    if action not in ACTIONS.get(state, []) or action == "edit":
        raise ConflictError(f"You can’t {action} a post that is {STATUS_LABEL[state].lower()}.", code="invalid_transition")
    S = BuzzPost.Status
    if action == "delete":
        for m in post.media.all():
            delete_media_files(m)
        post.delete()
        return None
    if action == "submit":
        _clean(partner, {}, post)  # dates may have passed since the draft was saved
        _require_publishable(partner)
        post.status, post.submitted_at, post.review_note = S.IN_REVIEW, timezone.now(), ""
    elif action == "withdraw":
        post.status = S.DRAFT
    elif action == "pause":
        post.status = S.PAUSED
    elif action == "resume":
        post.status = S.APPROVED
    elif action == "archive":
        post.status = S.ARCHIVED
    elif action == "restore":
        post.status = S.DRAFT
    post.save(update_fields=["status", "submitted_at", "review_note", "updated_at"])
    return post


# --- moderation (Click staff) ------------------------------------------------------------------------------------

def review(post: BuzzPost, approve: bool, reviewer=None, note: str = "") -> BuzzPost:
    from apps.partners.notifications import notify_partner

    if post.status != BuzzPost.Status.IN_REVIEW:
        return post
    post.status = BuzzPost.Status.APPROVED if approve else BuzzPost.Status.REJECTED
    post.review_note, post.reviewed_at, post.reviewed_by = note[:300], timezone.now(), reviewer
    post.save(update_fields=["status", "review_note", "reviewed_at", "reviewed_by", "updated_at"])
    if approve:
        when = "is live on Click. Buzz" if display_status(post) == "live" else "is approved and will go live as scheduled"
        notify_partner(post.partner, "account", "Buzz post approved", f"“{post.headline}” {when}.", "/buzz")
    else:
        notify_partner(post.partner, "account", "Buzz post not approved", note or f"“{post.headline}” needs changes.", "/buzz")
    return post


def remove(post: BuzzPost, note: str) -> None:
    from apps.partners.notifications import notify_partner

    post.status, post.review_note = BuzzPost.Status.REMOVED, note[:300]
    post.save(update_fields=["status", "review_note", "updated_at"])
    notify_partner(post.partner, "account", "Buzz post removed", note or f"“{post.headline}” broke the Buzz guidelines.", "/buzz")


# --- reading -----------------------------------------------------------------------------------------------------

def post_dict(p: BuzzPost, now=None) -> dict:
    state = display_status(p, now)
    listing = _find_listing(p.partner, p.target_type, p.target_id) if p.target_type else None
    open_reports = getattr(p, "open_reports", None)
    return {
        "id": str(p.id), "kind": p.kind, "kind_label": p.get_kind_display(), "headline": p.headline, "caption": p.caption,
        "audience": p.audience, "target_type": p.target_type, "target_id": p.target_id,
        "target_title": listing["title"] if listing else ("Listing no longer live" if p.target_type else ""),
        "cta": p.cta, "cta_label": CTA_LABEL.get(p.cta, ""), "link": listing["link"] if listing else "",
        "product": {"id": str(p.product.id), "name": p.product.name, "price": f"{p.product.price:.2f}", "available": p.product.is_available}
        if p.product else None,
        "offer": {"id": str(p.store_offer.id), "title": p.store_offer.title} if p.store_offer else None,
        "media": [media_dict(m) for m in p.media.all()],
        "status": state, "status_label": STATUS_LABEL[state], "review_note": p.review_note,
        "publish_at": p.publish_at.isoformat() if p.publish_at else None, "expires_at": p.expires_at.isoformat() if p.expires_at else None,
        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None, "created_at": p.created_at.isoformat(),
        "stats": {"views": p.views, "cta_clicks": p.cta_clicks, "likes": p.likes, "saves": p.saves,
                  "ctr": round(p.cta_clicks * 100 / p.views, 1) if p.views else None, "open_reports": open_reports or 0},
        "actions": ACTIONS[state],
    }


def overview(partner: Partner, status: str = "") -> dict:
    now = timezone.now()
    posts = list(BuzzPost.objects.filter(partner=partner).select_related("partner", "product", "store_offer").prefetch_related("media")
                 .annotate(open_reports=Count("reports", filter=Q(reports__status="open"))))
    rows = [post_dict(p, now) for p in posts]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    week = now.date() - timedelta(days=6)
    ev = BuzzEvent.objects.filter(post__partner=partner, day__gte=week).values("kind").annotate(n=Count("id"))
    last7 = {e["kind"]: e["n"] for e in ev}
    return {
        "posts": [r for r in rows if not status or r["status"] == status],
        "counts": [{"status": k, "count": v} for k, v in counts.items()],  # a list: status values aren't renamed to camelCase
        "totals": {"views7d": last7.get("view", 0), "clicks7d": last7.get("click", 0),
                   "likes": sum(p.likes for p in posts), "saves": sum(p.saves for p in posts)},
        "can_publish": can_publish(partner), "listings": [{k: v for k, v in x.items() if k != "store_type"} for x in listings(partner)],
        "cta_labels": [{"value": k, "label": v} for k, v in CTA_LABEL.items()], "kinds": [{"value": v, "label": label} for v, label in BuzzPost.Kind.choices],
        **attachables(partner),
        "limits": {"media": MAX_MEDIA, "video_mb": MAX_VIDEO_BYTES // (1024 * 1024), "image_mb": 8, "max_days": MAX_RUN.days},
    }
