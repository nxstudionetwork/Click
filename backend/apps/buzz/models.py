"""
Partner Buzz posts: promotional media a partner publishes into Click. Buzz.

BuzzPost      what the partner says (caption, kind) and the one Click action it leads to: a listing the partner
              operates (their store, hotel, services profile, ride booking, ...), optionally one of their own items
              and one of their own live offers. Click reviews every post before customers see it.
BuzzMedia     uploaded photos (re-encoded WebP renditions) and short videos, kept in media storage; only paths
              are stored here.
BuzzReaction  a like or a save by a signed-in person (customer or partner).
BuzzEvent     a view or CTA click, once per viewer per post per day, so performance numbers aren't inflated.
BuzzReport    someone reported a post; Click moderators decide (Django admin today, Business OS later).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class BuzzPost(BaseModel):
    class Kind(models.TextChoices):
        UPDATE = "update", "Business update"
        NEW_ITEM = "new_item", "Something new"
        OFFER = "offer", "Offer"
        ANNOUNCEMENT = "announcement", "Announcement"
        EVENT = "event", "Event"
        SEASONAL = "seasonal", "Seasonal campaign"
        BEHIND_SCENES = "behind_scenes", "Behind the scenes"
        TIP = "tip", "Tip"
        ACHIEVEMENT = "achievement", "Achievement"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        APPROVED = "approved", "Approved"  # live, scheduled or expired depending on its dates
        PAUSED = "paused", "Paused"
        REJECTED = "rejected", "Not approved"
        REMOVED = "removed", "Removed by Click"
        ARCHIVED = "archived", "Archived"

    class Audience(models.TextChoices):
        PUBLIC = "public", "Customers and partners"
        PARTNERS = "partners", "Click partners only"

    partner = models.ForeignKey("partners.Partner", on_delete=models.CASCADE, related_name="buzz_posts")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.UPDATE)
    headline = models.CharField(max_length=80)
    caption = models.TextField(max_length=600, blank=True)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.PUBLIC)
    # The action: always one of the partner's own live listings, checked on every save and again when served.
    target_type = models.CharField(max_length=16, blank=True)
    target_id = models.CharField(max_length=64, blank=True, help_text="The listing's id (store/hotel/profile); empty for ride booking.")
    cta = models.CharField(max_length=16, blank=True, help_text="One of the listing's allowed actions, e.g. order, book.")
    product = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="buzz_posts")
    store_offer = models.ForeignKey("stores.StoreOffer", on_delete=models.SET_NULL, null=True, blank=True, related_name="buzz_posts")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    review_note = models.CharField(max_length=300, blank=True)
    publish_at = models.DateTimeField(null=True, blank=True, help_text="Empty = as soon as it is approved.")
    expires_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    views = models.PositiveIntegerField(default=0)
    cta_clicks = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "publish_at", "expires_at"], name="buzz_post_live_idx")]

    def __str__(self) -> str:
        return f"{self.headline} ({self.partner})"


class BuzzMedia(BaseModel):
    class Kind(models.TextChoices):
        IMAGE = "image", "Photo"
        VIDEO = "video", "Video"

    partner = models.ForeignKey("partners.Partner", on_delete=models.CASCADE, related_name="buzz_media")
    post = models.ForeignKey(BuzzPost, on_delete=models.CASCADE, null=True, blank=True, related_name="media")
    kind = models.CharField(max_length=5, choices=Kind.choices)
    renditions = models.JSONField(default=dict, blank=True, help_text="Photos: {width: storage path} of WebP renditions.")
    file = models.CharField(max_length=255, blank=True, help_text="Videos: storage path.")
    content_type = models.CharField(max_length=40, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    bytes = models.PositiveIntegerField(default=0)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]


class BuzzReaction(BaseModel):
    class Kind(models.TextChoices):
        LIKE = "like", "Like"
        SAVE = "save", "Save"

    post = models.ForeignKey(BuzzPost, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buzz_reactions")
    kind = models.CharField(max_length=4, choices=Kind.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "user", "kind"], name="buzz_reaction_once")]


class BuzzItemReaction(BaseModel):
    """Like / save on a Buzz item Click builds from live records (offer, show, store, product…), keyed by its feed id,
    e.g. "offer:<uuid>". Partner posts keep using BuzzReaction."""

    item_key = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buzz_item_reactions")
    kind = models.CharField(max_length=4, choices=BuzzReaction.Kind.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item_key", "user", "kind"], name="buzz_item_reaction_once")]


class BuzzEvent(BaseModel):
    class Kind(models.TextChoices):
        VIEW = "view", "View"
        CLICK = "click", "CTA click"

    post = models.ForeignKey(BuzzPost, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=5, choices=Kind.choices)
    viewer = models.CharField(max_length=64, help_text="User id, or a hashed anonymous key.")
    day = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "kind", "viewer", "day"], name="buzz_event_once_a_day")]
        indexes = [models.Index(fields=["post", "kind", "day"], name="buzz_event_post_day_idx")]


class BuzzReport(BaseModel):
    class Reason(models.TextChoices):
        MISLEADING = "misleading", "Misleading or false offer"
        SPAM = "spam", "Spam"
        OFFENSIVE = "offensive", "Offensive or harassing"
        ILLEGAL = "illegal", "Illegal or unsafe"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UPHELD = "upheld", "Upheld (post removed)"
        DISMISSED = "dismissed", "Dismissed"

    post = models.ForeignKey(BuzzPost, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buzz_reports")
    reason = models.CharField(max_length=12, choices=Reason.choices)
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "reporter"], condition=Q(status="open"), name="buzz_report_one_open")]
