"""Click. Payments API: how the customer pays and every payment they made — owned through the paid record, never by a
client-supplied id. Statuses come from the payment records and the wallet ledger (refunds), never from the client."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from .models import Payment, PaymentPreference
from .records import METHODS, TARGETS, describe, owned, status_of, with_relations

SERVICE_FILTER = {"food": Q(order__store__store_type="restaurant"), "groceries": Q(order__store__store_type="grocery"),
                  "shop": Q(order__store__store_type="retail"), "ride": Q(ride__isnull=False), "parcel": Q(parcel__isnull=False),
                  "services": Q(service_booking__isnull=False), "shows": Q(booking__isnull=False), "events": Q(event_booking__isnull=False),
                  "hotels": Q(hotel_booking__isnull=False), "travel": Q(travel_booking__isnull=False), "bookings": Q(experience_booking__isnull=False),
                  "wallet": Q(wallet_topup__isnull=False)}
OFFLINE_METHODS = ["cash_on_delivery", "cash", "pay_at_venue"]
STATUS_FILTER = {"successful": Q(status="captured"), "pending": Q(status__in=["pending", "authorized"]) & ~Q(method__in=OFFLINE_METHODS),
                 "pay_later": Q(status="pending", method__in=OFFLINE_METHODS), "failed": Q(status="failed"),
                 "refunded": Q(status="refunded") | Q(wallet_transactions__kind="refund"), "cancelled": Q(status="cancelled")}


def payment_out(p: Payment, full: bool = False) -> dict:
    d = describe(p)
    st, label = status_of(p)
    out = {"id": str(p.id), "reference": f"PAY-{str(p.id)[:8].upper()}", "service": d["service"], "label": d["label"], "order_reference": d["reference"],
           "link": d["link"], "method": p.method, "method_label": p.get_method_display(), "amount": f"{p.amount:.2f}", "currency": p.currency,
           "status": st, "status_label": label, "created_at": p.created_at.isoformat()}
    if not full:
        return out
    wallet = [t for t in p.wallet_transactions.all()]
    refunds = [t for t in wallet if t.kind == "refund"]
    out.update({
        "provider": "Click. Wallet" if p.method == "wallet" else ("Payment provider" if p.method in ("upi", "card", "netbanking") else "Collected in person"),
        "provider_reference": p.provider_reference or None,
        "wallet_entries": [{"id": str(t.id), "kind": t.kind, "kind_label": t.get_kind_display(), "amount": f"{t.amount:.2f}", "bucket": t.bucket} for t in wallet],
        "refunds": [{"id": str(t.id), "amount": f"{t.amount:.2f}", "status": "completed", "status_label": "Refund completed",
                     "to": "Click. Wallet", "credited_at": t.created_at.isoformat(), "description": t.description} for t in refunds],
        "breakdown": _breakdown(p, d["target"]),
        "receipt": st in ("successful", "partly_refunded", "refunded"),
        "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in p.support_tickets.all()],
        "retry": _retry(p, d),
    })
    return out


def _breakdown(p: Payment, target: str) -> dict | None:
    obj = getattr(p, target)
    fields = {}
    for name, label in (("subtotal", "Subtotal"), ("base_fare", "Fare"), ("room_total", "Room"), ("delivery_fee", "Delivery fee"),
                        ("convenience_fee", "Convenience fee"), ("fees", "Charges"), ("discount", "Discount"), ("tax", "Taxes"), ("total", "Total")):
        v = getattr(obj, name, None)
        if v is not None and (name in ("total",) or v):
            fields[name] = {"label": label, "amount": f"{v:.2f}"}
    offer = getattr(obj, "offer_title", "") or ""
    return {"lines": list(fields.values()), "offer": offer or None} if fields else None


def _retry(p: Payment, d: dict) -> dict | None:
    """Where a failed / pending payment can be retried: on the record that owns it (so a retry never creates a second order)."""
    if p.status in ("failed", "pending") and d["target"] in ("hotel_booking", "travel_booking", "experience_booking", "event_booking"):
        return {"label": "Retry on the booking", "path": d["link"]}
    return None


class PaymentsView(APIView):
    """GET /customer/payments?service=&status=&q=&period=today|7d|30d&from=&to=&page="""

    permission_classes = [IsCustomer]

    def get(self, request):
        qs = with_relations(owned(request.user.customer_profile))
        qp = request.query_params
        if qp.get("service") in SERVICE_FILTER:
            qs = qs.filter(SERVICE_FILTER[qp["service"]])
        if qp.get("status") in STATUS_FILTER:
            qs = qs.filter(STATUS_FILTER[qp["status"]])
        period = qp.get("period")
        now = timezone.now()
        if period in ("today", "7d", "30d"):
            qs = qs.filter(created_at__gte=now - {"today": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}[period])
        try:
            if qp.get("from"):
                qs = qs.filter(created_at__date__gte=date.fromisoformat(qp["from"]))
            if qp.get("to"):
                qs = qs.filter(created_at__date__lte=date.fromisoformat(qp["to"]))
        except ValueError:
            raise DomainError("Choose valid dates.", code="validation_error")
        q = (qp.get("q") or "").strip().upper()[:40]
        if q:
            cond = Q()
            for f, (_, _, _, _, _) in TARGETS.items():
                ref = {"order": "order__number", "booking": "booking__reference", "ride": "ride__number", "parcel": "parcel__number",
                       "service_booking": "service_booking__number", "event_booking": "event_booking__number", "hotel_booking": "hotel_booking__number",
                       "travel_booking": "travel_booking__number", "experience_booking": "experience_booking__number",
                       "wallet_topup": "wallet_topup__provider_reference"}[f]
                cond |= Q(**{f"{ref}__icontains": q})
            cond |= Q(order__store__name__icontains=q)
            if q.startswith("PAY-"):
                cond |= Q(id__startswith=q[4:].lower())
            qs = qs.filter(cond)
        qs = qs.distinct().order_by("-created_at")
        page = max(1, int(qp.get("page") or 1)) if str(qp.get("page") or "1").isdigit() else 1
        rows = list(qs[(page - 1) * 20: page * 20 + 1])
        return Response({"results": [payment_out(p) for p in rows[:20]], "has_next": len(rows) > 20, "page": page})


class PaymentDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        p = get_object_or_404(with_relations(owned(request.user.customer_profile)).prefetch_related("support_tickets"), pk=pk)
        return Response(payment_out(p, full=True))


class OverviewView(APIView):
    """GET /customer/payments/overview — methods Click. can take, the default, counts that need attention, recent payments."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        pref = PaymentPreference.objects.filter(customer=c).first()
        qs = owned(c)
        from apps.wallet.services import balance

        refunds = c.wallet_transactions.filter(kind="refund", payment__isnull=False)
        return Response({
            "methods": [{**m, "default": (pref.default_method if pref else "wallet") == m["code"],
                         "detail": f"Balance ₹{balance(c):,.2f}" if m["code"] == "wallet" else ""} for m in METHODS],
            "default_method": pref.default_method if pref else "wallet",
            "online_methods": {"available": False,
                               "note": "Card and UPI checkout need a connected payment provider. Click. never stores card numbers, CVVs or UPI PINs."},
            "counts": {"pending": qs.filter(STATUS_FILTER["pending"]).count(), "pay_later": qs.filter(STATUS_FILTER["pay_later"]).count(), "failed": qs.filter(status="failed").count(),
                       "refunds": refunds.count()},
            "recent": [payment_out(p) for p in with_relations(qs).order_by("-created_at")[:5]],
        })


class PreferenceInput(serializers.Serializer):
    default_method = serializers.ChoiceField(choices=[m["code"] for m in METHODS if m["can_default"]])


class PreferencesView(APIView):
    """PATCH /customer/payments/preferences {defaultMethod} — stored on the server; checkout preselects it."""

    permission_classes = [IsCustomer]

    def patch(self, request):
        s = PreferenceInput(data=request.data)
        s.is_valid(raise_exception=True)
        pref, _ = PaymentPreference.objects.update_or_create(customer=request.user.customer_profile, defaults=s.validated_data)
        return Response({"default_method": pref.default_method})


class RefundsView(APIView):
    """GET /customer/payments/refunds — refunds credited from payments (read from the wallet ledger)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = (request.user.customer_profile.wallet_transactions.filter(kind="refund", payment__isnull=False)
                .select_related("payment__order__store", "payment__hotel_booking", "payment__travel_booking", "payment__experience_booking",
                                "payment__booking", "payment__event_booking", "payment__service_booking", "payment__ride", "payment__parcel")[:100])
        out = []
        for t in rows:
            d = describe(t.payment)
            out.append({"id": str(t.id), "refund_reference": f"RFD-{str(t.id)[:8].upper()}", "amount": f"{t.amount:.2f}", "status": "completed",
                        "status_label": "Refund completed", "to": "Click. Wallet", "credited_at": t.created_at.isoformat(), "reason": t.description,
                        "payment": {"id": str(t.payment_id), "reference": f"PAY-{str(t.payment_id)[:8].upper()}", "amount": f"{t.payment.amount:.2f}",
                                    "method_label": t.payment.get_method_display(), "label": d["label"], "order_reference": d["reference"], "link": d["link"]}})
        return Response({"results": out})


