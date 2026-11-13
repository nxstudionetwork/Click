import secrets

from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import CustomerProfile


def _reference() -> str:
    return "SUP-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(7))


class SupportTicket(BaseModel):
    """Customer-raised ticket. Agents work these from Business OS (Phase 6)."""

    class Category(models.TextChoices):
        ORDER = "order", "Orders"
        FOOD = "food", "Food"
        GROCERIES = "groceries", "Groceries"
        SHOP = "shop", "Shop"
        RIDE = "ride", "Ride"
        PARCEL = "parcel", "Parcel"
        DELIVERY = "delivery", "Delivery"
        TRAVEL = "travel", "Travel"
        HOTELS = "hotels", "Hotels"
        SHOWS = "shows", "Shows"
        EVENTS = "events", "Events"
        BOOKINGS = "bookings", "Bookings (places & experiences)"
        SERVICE = "service", "Services"
        PAYMENT = "payment", "Payments"
        WALLET = "wallet", "Wallet"
        REWARDS = "rewards", "Rewards"
        ACCOUNT = "account", "Account & security"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        AWAITING_CUSTOMER = "awaiting_customer", "Waiting for your reply"
        REOPENED = "reopened", "Reopened"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    reference = models.CharField(max_length=12, unique=True, default=_reference, editable=False)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name="support_tickets")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    parcel = models.ForeignKey("parcels.ParcelOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    service_booking = models.ForeignKey("professionals.ServiceBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="support_tickets")
    event_booking = models.ForeignKey("eventhub.EventBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="support_tickets")
    hotel_booking = models.ForeignKey("hotels.HotelBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="support_tickets")
    travel_booking = models.ForeignKey("travel.TravelBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="support_tickets")
    experience_booking = models.ForeignKey("experiences.ExperienceBooking", on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="support_tickets")
    ride = models.ForeignKey("rides.Ride", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    show_booking = models.ForeignKey("bookings.Booking", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    payment = models.ForeignKey("payments.Payment", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    wallet_transaction = models.ForeignKey("wallet.WalletTransaction", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    # Safety Center reports are ordinary support requests, flagged so they're triaged first and listed in Safety Center.
    is_safety = models.BooleanField(default=False)
    contact_preference = models.CharField(max_length=8, blank=True, choices=[("call", "Call me"), ("message", "Message in the app"), ("email", "Email")])
    category = models.CharField(max_length=20, choices=Category.choices)
    issue_type = models.CharField(max_length=40, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL,
                                help_text="Set by Click. rules (security, payments, safety), never by the customer.")
    subject = models.CharField(max_length=150)
    message = models.TextField(max_length=4000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"], name="support_customer_recent_idx"),
                   models.Index(fields=["status"], name="support_status_idx")]


def _attachment_path(instance, filename):
    import os
    import uuid

    return f"support/{instance.ticket_id}/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class SupportMessage(BaseModel):
    """One message in a support request conversation (the customer's or Click. Support's)."""

    class Sender(models.TextChoices):
        CUSTOMER = "customer", "You"
        SUPPORT = "support", "Click. Support"

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=10, choices=Sender.choices)
    agent = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    body = models.TextField(max_length=4000, blank=True)
    attachment = models.FileField(upload_to=_attachment_path, blank=True)
    attachment_name = models.CharField(max_length=120, blank=True)
    attachment_type = models.CharField(max_length=60, blank=True)
    attachment_size = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        new = self._state.adding
        super().save(*args, **kwargs)
        if new and self.sender == self.Sender.SUPPORT:  # replies reach the customer through Notifications
            from apps.notifications.models import NotificationCategory
            from apps.notifications.services import notify

            notify(self.ticket.customer, NotificationCategory.SUPPORT, "Click. Support replied to your request",
                   f"{self.ticket.reference}: {self.body[:120]}", f"/help/tickets/{self.ticket_id}")
            if self.ticket.status in (SupportTicket.Status.OPEN, SupportTicket.Status.REOPENED):
                SupportTicket.objects.filter(pk=self.ticket_id).update(status=SupportTicket.Status.IN_PROGRESS)


class HelpArticle(BaseModel):
    slug = models.SlugField(max_length=80, unique=True)
    category = models.CharField(max_length=20, choices=SupportTicket.Category.choices)
    title = models.CharField(max_length=140)
    summary = models.CharField(max_length=240)
    body = models.JSONField(help_text='Paragraphs: ["...", "..."]')
    steps = models.JSONField(default=list, blank=True, help_text="Optional step-by-step list.")
    keywords = models.CharField(max_length=240, blank=True)
    action_label = models.CharField(max_length=60, blank=True)
    action_path = models.CharField(max_length=120, blank=True, help_text="In-app route the article points to.")
    is_popular = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)
    helpful_yes = models.PositiveIntegerField(default=0)
    helpful_no = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category", "position"]

    def __str__(self) -> str:
        return self.title


class ArticleFeedback(BaseModel):
    article = models.ForeignKey(HelpArticle, on_delete=models.CASCADE, related_name="feedback")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="article_feedback")
    helpful = models.BooleanField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["article", "customer"], name="support_one_feedback_per_article")]
