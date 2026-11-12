"""Help & Support API. Articles are public; support requests, their conversation and attachments belong to the signed-in
customer (every query is scoped to them, and a request can only reference the customer's own records). Status changes
other than closing / reopening are made by Click. Support (admin / Business OS), never by the customer."""

from __future__ import annotations

import os
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import ConflictError, DomainError
from apps.core.api.permissions import IsCustomer
from apps.eventhub.models import EventBooking
from apps.experiences.models import ExperienceBooking
from apps.hotels.models import HotelBooking
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.orders.models import Order
from apps.parcels.models import ParcelOrder
from apps.professionals.models import ServiceBooking
from apps.bookings.models import Booking
from apps.payments.models import Payment
from apps.rides.models import Ride
from apps.travel.models import TravelBooking
from apps.wallet.models import WalletTransaction

from .models import ArticleFeedback, HelpArticle, SupportMessage, SupportTicket

# Issue types per category (what the form offers). Security, unauthorised payments, unrecognised wallet activity and ride
# safety are marked urgent automatically; money problems important.
ISSUES = {
    "food": ["Missing item", "Wrong item", "Damaged item", "Late delivery", "Cancellation", "Refund", "Other"],
    "groceries": ["Missing item", "Damaged item", "Late delivery", "Wrong slot", "Refund", "Other"],
    "shop": ["Return or replacement", "Damaged item", "Wrong item", "Late delivery", "Refund", "Other"],
    "order": ["Missing item", "Wrong item", "Late delivery", "Cancellation", "Refund", "Other"],
    "ride": ["Driver issue", "Pickup issue", "Fare issue", "Cancellation", "Lost item", "Safety concern", "Other"],
    "parcel": ["Pickup issue", "Delivery failed", "Damaged parcel", "Tracking issue", "Other"],
    "delivery": ["Late delivery", "Delivery partner issue", "Other"],
    "travel": ["Ticket issue", "Cancellation", "Refund", "Schedule change", "Boarding issue", "Other"],
    "hotels": ["Booking issue", "Check-in problem", "Room issue", "Cancellation", "Refund", "Other"],
    "shows": ["Ticket issue", "Seat issue", "Show changed or cancelled", "Refund", "Other"],
    "events": ["Booking issue", "Quote issue", "Team / provider issue", "Cancellation", "Refund", "Other"],
    "bookings": ["Entry issue", "Slot issue", "Cancellation", "Refund", "Other"],
    "service": ["Professional didn’t arrive", "Quote issue", "Work quality", "Payment issue", "Cancellation", "Other"],
    "payment": ["Payment failed", "Payment pending", "Charged but order failed", "Charged twice", "Refund missing", "Wrong amount",
                "Unauthorised payment", "Receipt issue", "Other"],
    "wallet": ["Top-up issue", "Wrong balance", "Cashback missing", "Refund missing", "Wallet debit issue", "Transaction I don’t recognise",
               "Wallet restricted", "Other"],
    "rewards": ["Points missing", "Redemption issue", "Points expired", "Other"],
    "account": ["Login or OTP", "Profile or phone number", "Security concern", "Other"],
    "other": ["Other"],
}
URGENT = {"Security concern", "Unauthorised payment", "Transaction I don’t recognise", "Safety concern"}
IMPORTANT_CATS = {"payment", "wallet"}
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_BYTES = 5 * 1024 * 1024
LINKS = ("order", "parcel", "service_booking", "event_booking", "hotel_booking", "travel_booking", "experience_booking", "ride", "show_booking",
         "payment", "wallet_transaction")


def _owned_querysets(c) -> dict:
    from apps.payments.records import owned

    return {"order": Order.objects.filter(customer=c), "parcel": ParcelOrder.objects.filter(customer=c), "service_booking": ServiceBooking.objects.filter(customer=c),
            "event_booking": EventBooking.objects.filter(customer=c), "hotel_booking": HotelBooking.objects.filter(customer=c),
            "travel_booking": TravelBooking.objects.filter(customer=c), "experience_booking": ExperienceBooking.objects.filter(customer=c),
            "ride": Ride.objects.filter(customer=c), "show_booking": Booking.objects.filter(customer=c), "payment": owned(c),
            "wallet_transaction": WalletTransaction.objects.filter(customer=c)}


def _related(t: SupportTicket) -> dict | None:
    for f in LINKS:
        obj = getattr(t, f)
        if obj is None:
            continue
        label = {"order": lambda o: f"Order {o.number}", "parcel": lambda o: f"Parcel {o.number}", "service_booking": lambda o: f"Service booking {o.number}",
                 "event_booking": lambda o: f"Event booking {o.number}", "hotel_booking": lambda o: f"Hotel booking {o.number}",
                 "travel_booking": lambda o: f"Travel booking {o.pnr or o.number}", "experience_booking": lambda o: f"Booking {o.number}",
                 "ride": lambda o: f"Ride {o.number}", "show_booking": lambda o: f"Show tickets {o.reference}",
                 "payment": lambda o: f"Payment PAY-{str(o.id)[:8].upper()}", "wallet_transaction": lambda o: f"Wallet entry {str(o.id)[:8].upper()} · {'+' if o.amount > 0 else '−'}₹{abs(o.amount):,.2f}"}[f](obj)
        link = {"order": f"/orders/{obj.pk}", "parcel": f"/parcels/{obj.pk}", "service_booking": f"/services/bookings/{obj.pk}",
                "event_booking": f"/events/bookings/{obj.pk}", "hotel_booking": f"/hotels/bookings/{obj.pk}", "travel_booking": f"/travel/bookings/{obj.pk}",
                "experience_booking": f"/bookings/r/{obj.pk}", "ride": f"/rides/{obj.pk}", "show_booking": f"/tickets/{obj.pk}",
                "payment": f"/account/payments/{obj.pk}", "wallet_transaction": f"/wallet/activity/{obj.pk}"}[f]
        return {"type": f, "id": str(obj.pk), "label": label, "link": link}
    return None


class SupportTicketSerializer(serializers.ModelSerializer):
    # Writable links (validated against the customer's own records in __init__), plus read-only numbers kept for older clients.
    order_id = serializers.PrimaryKeyRelatedField(source="order", queryset=Order.objects.none(), required=False, allow_null=True)
    parcel_id = serializers.PrimaryKeyRelatedField(source="parcel", queryset=ParcelOrder.objects.none(), required=False, allow_null=True)
    service_booking_id = serializers.PrimaryKeyRelatedField(source="service_booking", queryset=ServiceBooking.objects.none(), required=False, allow_null=True)
    event_booking_id = serializers.PrimaryKeyRelatedField(source="event_booking", queryset=EventBooking.objects.none(), required=False, allow_null=True)
    hotel_booking_id = serializers.PrimaryKeyRelatedField(source="hotel_booking", queryset=HotelBooking.objects.none(), required=False, allow_null=True)
    travel_booking_id = serializers.PrimaryKeyRelatedField(source="travel_booking", queryset=TravelBooking.objects.none(), required=False, allow_null=True)
    experience_booking_id = serializers.PrimaryKeyRelatedField(source="experience_booking", queryset=ExperienceBooking.objects.none(), required=False, allow_null=True)
    ride_id = serializers.PrimaryKeyRelatedField(source="ride", queryset=Ride.objects.none(), required=False, allow_null=True)
    show_booking_id = serializers.PrimaryKeyRelatedField(source="show_booking", queryset=Booking.objects.none(), required=False, allow_null=True)
    payment_id = serializers.PrimaryKeyRelatedField(source="payment", queryset=Payment.objects.none(), required=False, allow_null=True)
    wallet_transaction_id = serializers.PrimaryKeyRelatedField(source="wallet_transaction", queryset=WalletTransaction.objects.none(), required=False, allow_null=True)
    order_number = serializers.CharField(source="order.number", read_only=True, default=None)
    parcel_number = serializers.CharField(source="parcel.number", read_only=True, default=None)
    service_booking_number = serializers.CharField(source="service_booking.number", read_only=True, default=None)
    event_booking_number = serializers.CharField(source="event_booking.number", read_only=True, default=None)
    hotel_booking_number = serializers.CharField(source="hotel_booking.number", read_only=True, default=None)
    travel_booking_number = serializers.CharField(source="travel_booking.number", read_only=True, default=None)
    experience_booking_number = serializers.CharField(source="experience_booking.number", read_only=True, default=None)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    related = serializers.SerializerMethodField()
    last_update = serializers.SerializerMethodField()
    idempotency_key = serializers.CharField(write_only=True, required=False, max_length=64)

    class Meta:
        model = SupportTicket
        fields = ["id", "reference", "category", "category_label", "issue_type", "subject", "message", "status", "status_label", "priority", "priority_label",
                  *[f"{f}_id" for f in LINKS], "order_number", "parcel_number", "service_booking_number", "event_booking_number", "hotel_booking_number",
                  "travel_booking_number", "experience_booking_number", "related", "last_update", "created_at", "updated_at", "resolved_at", "idempotency_key"]
        read_only_fields = ["id", "reference", "status", "priority", "created_at", "updated_at", "resolved_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and hasattr(request.user, "customer_profile"):
            for f, qs in _owned_querysets(request.user.customer_profile).items():  # only the customer's own records
                self.fields[f"{f}_id"].queryset = qs

    def validate(self, attrs):
        cat = attrs.get("category")
        issue = attrs.get("issue_type") or ""
        if issue and cat in ISSUES and issue not in ISSUES[cat]:
            raise serializers.ValidationError({"issue_type": "Choose an issue from the list."})
        if sum(1 for f in LINKS if attrs.get(f)) > 1:
            raise serializers.ValidationError("Attach one related item.")
        return attrs

    def get_related(self, t) -> dict | None:
        return _related(t)

    def get_last_update(self, t) -> str:
        m = t.messages.order_by("-created_at").first()
        return (m.created_at if m else t.updated_at).isoformat()


def _priority(c, category: str, issue: str) -> str:
    if issue in URGENT:
        return SupportTicket.Priority.URGENT
    from apps.rewards.services import tier_of

    if category in IMPORTANT_CATS or tier_of(c)["code"] in ("gold", "platinum"):
        return SupportTicket.Priority.IMPORTANT
    return SupportTicket.Priority.NORMAL


class SupportTicketListCreateView(generics.ListCreateAPIView):
    """GET /customer/support/tickets?status=open ; POST creates a request (rate limited, duplicate-safe)."""

    permission_classes = [IsCustomer]
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        qs = SupportTicket.objects.filter(customer=self.request.user.customer_profile).select_related(*LINKS).prefetch_related("messages")
        if self.request.query_params.get("status") == "open":
            qs = qs.exclude(status__in=["resolved", "closed"])
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        c = self.request.user.customer_profile
        v = serializer.validated_data
        recent = SupportTicket.objects.filter(customer=c, created_at__gte=timezone.now() - timedelta(hours=1))
        same = recent.filter(subject__iexact=v["subject"].strip(), category=v["category"]).first()
        if same:  # double submit / repeat of the same request
            raise ConflictError(f"You already raised this request ({same.reference}). We’ll reply there.", code="duplicate_ticket",
                                details={"id": str(same.id), "reference": same.reference})
        if recent.count() >= settings.CLICK_SUPPORT_TICKETS_PER_HOUR:
            raise DomainError("You’ve raised several requests in the last hour. Add details to an existing request, or email Click. Support.",
                              code="rate_limited", status_code=429)
        v.pop("idempotency_key", None)
        ticket = serializer.save(customer=c, priority=_priority(c, v["category"], v.get("issue_type") or ""))
        SupportMessage.objects.create(ticket=ticket, sender=SupportMessage.Sender.CUSTOMER, body=ticket.message)
        notify(c, NotificationCategory.SUPPORT, f"We received your request {ticket.reference}",
               "Click. Support will reply here.", f"/help/tickets/{ticket.id}")
        from apps.activity.services import record

        record(c, "support.created", {"reference": ticket.reference, "category": ticket.category}, obj=ticket)


class SupportTicketDetailView(generics.RetrieveAPIView):
    permission_classes = [IsCustomer]
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        return SupportTicket.objects.filter(customer=self.request.user.customer_profile).select_related(*LINKS)


def message_out(m: SupportMessage, request) -> dict:
    return {"id": str(m.id), "sender": m.sender, "sender_label": m.get_sender_display(), "body": m.body, "created_at": m.created_at.isoformat(),
            "attachment": {"name": m.attachment_name, "type": m.attachment_type, "size": m.attachment_size,
                           "url": request.build_absolute_uri(f"/api/v1/customer/support/attachments/{m.id}")} if m.attachment else None}


class MessagesView(APIView):
    """GET / POST /customer/support/tickets/<id>/messages — the conversation; POST takes text and / or one attachment
    (JPEG, PNG, WebP or PDF, up to 5 MB; checked by content, not just the name)."""

    permission_classes = [IsCustomer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "uploads"

    def _ticket(self, request, pk):
        return get_object_or_404(SupportTicket, pk=pk, customer=request.user.customer_profile)

    def get(self, request, pk):
        t = self._ticket(request, pk)
        return Response({"results": [message_out(m, request) for m in t.messages.all()]})

    def post(self, request, pk):
        t = self._ticket(request, pk)
        if t.status == SupportTicket.Status.CLOSED:
            raise ConflictError("This request is closed. Reopen it or create a new one.", code="ticket_closed")
        body = str(request.data.get("body") or "").strip()[:4000]
        f = request.FILES.get("attachment")
        if not body and not f:
            raise DomainError("Write a message or attach a file.", code="validation_error")
        m = SupportMessage(ticket=t, sender=SupportMessage.Sender.CUSTOMER, body=body)
        if f:
            if f.size > MAX_BYTES:
                raise DomainError("Attachments can be up to 5 MB.", code="attachment_too_large")
            head = f.read(16)
            f.seek(0)
            kind = ("image/jpeg" if head[:3] == b"\xff\xd8\xff" else "image/png" if head[:8] == b"\x89PNG\r\n\x1a\n" else
                    "image/webp" if head[:4] == b"RIFF" and head[8:12] == b"WEBP" else "application/pdf" if head[:5] == b"%PDF-" else "")
            if kind not in ALLOWED_TYPES:
                raise DomainError("Attach a JPEG, PNG, WebP image or a PDF.", code="attachment_type")
            m.attachment, m.attachment_name, m.attachment_type, m.attachment_size = f, os.path.basename(f.name)[:120], kind, f.size
        m.save()
        if t.status == SupportTicket.Status.AWAITING_CUSTOMER:
            t.status = SupportTicket.Status.IN_PROGRESS
        t.save(update_fields=["status", "updated_at"])
        return Response(message_out(m, request), status=status.HTTP_201_CREATED)


class AttachmentView(APIView):
    """GET /customer/support/attachments/<message id> — only the ticket owner can download it."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        from django.http import FileResponse

        m = get_object_or_404(SupportMessage, pk=pk, ticket__customer=request.user.customer_profile)
        if not m.attachment:
            raise DomainError("Not found.", code="not_found", status_code=404)
        return FileResponse(m.attachment.open("rb"), content_type=m.attachment_type, as_attachment=m.attachment_type == "application/pdf",
                            filename=m.attachment_name)


class TicketActionView(APIView):
    """POST /customer/support/tickets/<id>/<close|reopen> — the only status changes a customer can make."""

    permission_classes = [IsCustomer]

    def post(self, request, pk, action):
        t = get_object_or_404(SupportTicket, pk=pk, customer=request.user.customer_profile)
        if action == "close" and t.status != SupportTicket.Status.CLOSED:
            t.status = SupportTicket.Status.CLOSED
        elif action == "reopen" and t.status in (SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED):
            t.status, t.resolved_at = SupportTicket.Status.REOPENED, None
        else:
            raise ConflictError("That isn’t possible for this request now.", code="invalid_transition")
        t.save(update_fields=["status", "resolved_at", "updated_at"])
        return Response(SupportTicketSerializer(t, context={"request": request}).data)


class RelatedItemsView(APIView):
    """GET /customer/support/related?category= — the customer's recent records to attach (their own only)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        cat = request.query_params.get("category") or ""
        q = _owned_querysets(c)
        pick = {"food": [("order", q["order"].filter(store__store_type="restaurant"))], "groceries": [("order", q["order"].filter(store__store_type="grocery"))],
                "shop": [("order", q["order"].filter(store__store_type="retail"))], "order": [("order", q["order"])], "ride": [("ride", q["ride"])],
                "parcel": [("parcel", q["parcel"])], "travel": [("travel_booking", q["travel_booking"])], "hotels": [("hotel_booking", q["hotel_booking"])],
                "shows": [("show_booking", q["show_booking"])], "events": [("event_booking", q["event_booking"])],
                "bookings": [("experience_booking", q["experience_booking"])], "service": [("service_booking", q["service_booking"])],
                "payment": [("payment", q["payment"])], "wallet": [("wallet_transaction", q["wallet_transaction"])]}.get(cat, [])
        out = []
        for field, qs in pick:
            for obj in qs.order_by("-created_at")[:10]:
                fake = SupportTicket(**{field: obj})
                r = _related(fake)
                out.append({**r, "at": obj.created_at.isoformat()})
        return Response({"results": out, "issues": ISSUES.get(cat, ISSUES["other"])})


def article_out(a: HelpArticle, full: bool = False) -> dict:
    out = {"slug": a.slug, "category": a.category, "category_label": a.get_category_display(), "title": a.title, "summary": a.summary,
           "popular": a.is_popular}
    if full:
        out.update({"body": a.body, "steps": a.steps, "action": {"label": a.action_label, "path": a.action_path} if a.action_path else None,
                    "related": [article_out(x) for x in HelpArticle.objects.filter(category=a.category, is_published=True).exclude(pk=a.pk)[:4]]})
    return out


class HelpHomeView(APIView):
    """GET /support/help — categories with articles, popular articles, contacts and issue types (public)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        arts = list(HelpArticle.objects.filter(is_published=True))
        cats = []
        for code, label in SupportTicket.Category.choices:
            n = sum(1 for a in arts if a.category == code)
            if n or code in ISSUES:
                cats.append({"code": code, "label": label, "articles": n, "issues": ISSUES.get(code, ISSUES["other"])})
        phone = settings.CLICK_SUPPORT_PHONE
        return Response({"categories": cats, "popular": [article_out(a) for a in arts if a.is_popular][:8],
                         "contact": {"email": settings.CLICK_SUPPORT_EMAIL, "phone": phone, "phone_callable": phone.replace("+", "").isdigit(),
                                     "hours": settings.CLICK_SUPPORT_HOURS or None},
                         "articles": [article_out(a) for a in arts]})


class ArticleSearchView(APIView):
    """GET /support/articles?q=&category= — searches title, summary, body and keywords; ranked by title / keyword match."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()[:60]
        qs = HelpArticle.objects.filter(is_published=True)
        if request.query_params.get("category"):
            qs = qs.filter(category=request.query_params["category"])
        if q:
            words = [w for w in q.lower().split() if len(w) > 1][:6]
            cond = Q()
            for w in words:
                cond |= Q(title__icontains=w) | Q(summary__icontains=w) | Q(keywords__icontains=w) | Q(body__icontains=w)
            qs = qs.filter(cond)
            rows = sorted(qs, key=lambda a: -sum((3 if w in a.title.lower() else 0) + (2 if w in a.keywords else 0) + (1 if w in a.summary.lower() else 0) for w in words))
        else:
            rows = list(qs)
        return Response({"results": [article_out(a) for a in rows[:20]]})


class ArticleView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        return Response(article_out(get_object_or_404(HelpArticle, slug=slug, is_published=True), full=True))


class ArticleFeedbackView(APIView):
    """POST /customer/support/articles/<slug>/feedback {helpful} — once per customer (changing the answer updates it)."""

    permission_classes = [IsCustomer]

    @transaction.atomic
    def post(self, request, slug):
        a = get_object_or_404(HelpArticle.objects.select_for_update(), slug=slug, is_published=True)
        helpful = bool(request.data.get("helpful"))
        fb = ArticleFeedback.objects.filter(article=a, customer=request.user.customer_profile).first()
        if fb and fb.helpful != helpful:
            HelpArticle.objects.filter(pk=a.pk).update(**({"helpful_yes": F("helpful_yes") + 1, "helpful_no": F("helpful_no") - 1} if helpful else
                                                         {"helpful_no": F("helpful_no") + 1, "helpful_yes": F("helpful_yes") - 1}))
            fb.helpful = helpful
            fb.save(update_fields=["helpful", "updated_at"])
        elif not fb:
            ArticleFeedback.objects.create(article=a, customer=request.user.customer_profile, helpful=helpful)
            HelpArticle.objects.filter(pk=a.pk).update(**({"helpful_yes": F("helpful_yes") + 1} if helpful else {"helpful_no": F("helpful_no") + 1}))
        return Response({"helpful": helpful})
