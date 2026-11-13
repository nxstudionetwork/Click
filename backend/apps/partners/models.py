"""
Click Partner identity.

  PartnerType          top-level group (transport, food, logistics, ...)
  PartnerCategory      what the partner provides (driver, restaurant, ...);
                       its `configuration` drives onboarding fields and Home
  Partner              the business / service-provider entity
  PartnerMembership    which users act for a partner (owner today; staff later)
  PartnerProfile       contact + category-specific business details
  PartnerAddress       operating location and service area
  PartnerVerification  verification submissions and reviews (staff decide)
  PartnerStatusEvent   append-only audit trail of status changes

Partners never use the phone number or the database UUID as a public ID: the
customer/business-facing ID is `partner_code` (CLK-PT-000001), drawn from a
dedicated PostgreSQL sequence once the profile is completed and never changed.
Future Business OS concepts (branches, staff, catalogue, orders) hang off
Partner through their own tables.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

PARTNER_CODE_SEQUENCE = "partners_partner_code_seq"
PARTNER_CODE_PREFIX = "CLK-PT-"


class CatalogEntry(BaseModel):
    slug = models.SlugField(max_length=60)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=240, blank=True)
    icon = models.CharField(max_length=40, blank=True, help_text="Icon key understood by Click apps.")
    image_url = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class PartnerType(CatalogEntry):
    """Configuration holds the shared onboarding fields and Home modules for the group."""

    class Meta(CatalogEntry.Meta):
        constraints = [models.UniqueConstraint(fields=["slug"], name="partners_type_slug_unique")]


class PartnerCategory(CatalogEntry):
    """Configuration may override/extend the type's fields (defaults, extra fields, labels)."""

    partner_type = models.ForeignKey(PartnerType, on_delete=models.PROTECT, related_name="categories")

    class Meta(CatalogEntry.Meta):
        verbose_name_plural = "partner categories"
        constraints = [
            models.UniqueConstraint(fields=["partner_type", "slug"], name="partners_category_type_slug_unique"),
        ]


class Partner(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROFILE_COMPLETED = "profile_completed", "Profile completed"
        VERIFICATION_PENDING = "verification_pending", "Verification pending"
        VERIFIED = "verified", "Verified"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"
        INACTIVE = "inactive", "Inactive"

    partner_code = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    partner_type = models.ForeignKey(PartnerType, on_delete=models.PROTECT, related_name="partners")
    category = models.ForeignKey(PartnerCategory, on_delete=models.PROTECT, related_name="partners")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    business_name = models.CharField(max_length=150, blank=True)
    is_available = models.BooleanField(default=False, help_text="Partner-controlled online/open toggle (later phases).")
    profile_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["partner_type", "category", "status"], name="partners_category_status_idx"),
        ]

    def __str__(self) -> str:
        return self.partner_code or f"Draft partner {self.business_name or self.pk}"

    @property
    def is_onboarded(self) -> bool:
        return bool(self.partner_code)


class PartnerMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partner_memberships")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.OWNER)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["partner", "user"], name="partners_membership_unique"),
            # One owned partner per user for now; prevents duplicate partners on retries/races.
            models.UniqueConstraint(fields=["user"], condition=Q(role="owner"), name="partners_one_owned_partner_per_user"),
        ]


class PartnerProfile(BaseModel):
    partner = models.OneToOneField(Partner, on_delete=models.CASCADE, related_name="profile")
    contact_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    description = models.CharField(max_length=500, blank=True)
    details = models.JSONField(default=dict, blank=True, help_text="Category-specific fields, validated against the category schema.")
    logo_url = models.URLField(blank=True)


class PartnerAddress(BaseModel):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="addresses")
    is_primary = models.BooleanField(default=True)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=12)
    country = models.CharField(max_length=2, default="IN", help_text="ISO 3166-1 alpha-2")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    service_area = models.CharField(max_length=255, blank=True, help_text="Localities or area served.")
    service_radius_km = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(500)])

    class Meta:
        ordering = ["-is_primary", "-created_at"]
        verbose_name_plural = "partner addresses"
        constraints = [
            models.UniqueConstraint(fields=["partner"], condition=Q(is_primary=True), name="partners_one_primary_address"),
        ]


class PartnerVerification(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="verifications")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField()
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewer_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["partner"], condition=Q(status="pending"), name="partners_one_pending_verification"),
        ]


class PartnerStatusEvent(BaseModel):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="status_events")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]


# --- Operations (Partner Home) -----------------------------------------------------------------
# Links from a partner to the customer-facing records it operates. Customers keep ordering from a Store and booking
# a Venue's shows exactly as before; these tables only say which partner runs them, so Partner Home, the Business OS
# and the Customer App all read one shared model. Staff create the link (Django admin today, Business OS later).

class PartnerStore(BaseModel):
    """A storefront (restaurant, grocery, retail) operated by this partner. One store has exactly one operator."""

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="store_links")
    store = models.OneToOneField("stores.Store", on_delete=models.CASCADE, related_name="partner_link")

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.partner} → {self.store}"


class PartnerVenue(BaseModel):
    """A venue (cinema, theatre, arena) operated by this partner; its shows and bookings appear on Partner Home."""

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="venue_links")
    venue = models.OneToOneField("bookings.Venue", on_delete=models.CASCADE, related_name="partner_link")

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.partner} → {self.venue}"


class PartnerAvailabilityEvent(BaseModel):
    """Append-only log of every online/open toggle. Online time and Business OS availability reports derive from it."""

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="availability_events")
    is_available = models.BooleanField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["partner", "created_at"], name="partners_avail_recent_idx")]


class PartnerNotification(BaseModel):
    """In-app notification for a partner (new work, cancellations, verification). Push channels fan out later."""

    class Category(models.TextChoices):
        WORK = "work", "New work"
        UPDATE = "update", "Work update"
        ACCOUNT = "account", "Account"
        PAYMENT = "payment", "Payment"
        SYSTEM = "system", "System"

    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=12, choices=Category.choices)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300, blank=True)
    link_path = models.CharField(max_length=200, blank=True, help_text="Partner App route, e.g. /work?view=new.")
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["partner", "-created_at"], name="partners_notif_recent_idx"),
            models.Index(fields=["partner"], condition=Q(read_at__isnull=True), name="partners_notif_unread_idx"),
        ]
