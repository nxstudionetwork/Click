"""Click. Wallet API — everything is scoped to the signed-in customer; no endpoint lets a client set a balance. Balance
changes happen only in apps.wallet.services (payments, refunds, verified top-ups, cashback, rewards conversions)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import providers, services
from .models import WalletTopUp, WalletTransaction as T

FILTERS = {"added": Q(kind="topup"), "spent": Q(kind="payment"), "refunds": Q(kind="refund"), "cashback": Q(kind="cashback"),
           "rewards": Q(kind="reward"), "promo": Q(kind="promo"), "expired": Q(kind="expiry"), "adjustments": Q(kind="adjustment")}

# Services where checkout accepts Click. Wallet today (each service's payment code takes PaymentMethod.WALLET).
ELIGIBLE = [("food", "Food", "/food"), ("groceries", "Groceries", "/groceries"), ("shop", "Shop", "/shopping"), ("ride", "Ride", "/rides"),
            ("parcel", "Parcel", "/parcels"), ("services", "Services", "/services"), ("shows", "Shows", "/showtime"), ("events", "Events", "/events"),
            ("hotels", "Hotels", "/hotels"), ("travel", "Travel", "/travel"), ("bookings", "Bookings", "/bookings")]


def _service_of(t: T) -> dict | None:
    if t.payment_id:
        from apps.payments.records import describe

        d = describe(t.payment)
        return {**d, "payment_id": str(t.payment_id)}
    return None


def txn_out(t: T, full: bool = False) -> dict:
    out = {"id": str(t.id), "kind": t.kind, "kind_label": t.get_kind_display(), "bucket": t.bucket, "bucket_label": t.get_bucket_display(),
           "amount": f"{t.amount:.2f}", "direction": "credit" if t.amount > 0 else "debit", "currency": t.currency, "description": t.description,
           "created_at": t.created_at.isoformat(), "expires_at": t.expires_at.isoformat() if t.expires_at else None,
           "status": "completed", "status_label": "Expired" if t.kind == "expiry" else "Completed", "reference": str(t.id)[:8].upper()}
    if t.payment_id:
        out["service"] = _service_of(t)
    if not full:
        return out
    before = T.objects.filter(customer=t.customer, created_at__lt=t.created_at).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    same = T.objects.filter(customer=t.customer, created_at=t.created_at, id__lt=t.id).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    before += same
    out.update({"balance_before": f"{before:.2f}", "balance_after": f"{before + t.amount:.2f}"})
    if t.bucket == "promo" and t.amount > 0:
        used = t.consumptions.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        remaining = t.amount + used
        expired = bool(t.expires_at and t.expires_at <= timezone.now())
        out["credit"] = {"remaining": f"{max(Decimal('0'), remaining):.2f}", "used": f"{-used:.2f}", "expired": expired,
                         "state": "expired" if expired and remaining > 0 else "used" if remaining <= 0 else "available"}
    if t.lot_id:
        out["from_credit"] = {"id": str(t.lot_id), "description": t.lot.description}
    if t.kind == "topup" and hasattr(t, "topup"):
        tu = t.topup
        out["topup"] = {"method": tu.method, "provider_reference": tu.provider_reference, "status": tu.status}
    if t.kind == "refund" and t.payment_id:
        p = t.payment
        out["refund"] = {"original_amount": f"{p.amount:.2f}", "original_method": p.get_method_display(), "status": "credited",
                         "status_label": "Refund credited", "credited_at": t.created_at.isoformat()}
    if t.kind == "reward" and hasattr(t, "reward_redemption"):
        r = t.reward_redemption
        out["reward"] = {"item": r.item.title, "points": r.points}
    out["tickets"] = [{"id": str(x.id), "reference": x.reference, "status": x.status} for x in t.support_tickets.all()]
    return out


def _summary(customer) -> dict:
    month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = T.objects.filter(customer=customer, created_at__gte=month)

    def s(**f):
        return f"{abs(qs.filter(**f).aggregate(s=Sum('amount'))['s'] or 0):.2f}"

    return {"spent": s(kind="payment"), "added": s(kind="topup"), "refunds": s(kind="refund"), "cashback": s(kind="cashback"),
            "rewards": s(kind="reward"), "since": month.isoformat()}


class WalletView(APIView):
    """GET /customer/wallet — balance (from the ledger), breakdown, credits expiring, limits, where it's accepted, recent activity."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        services.sweep_expired(c)
        acc = services.account(c)
        b = services.breakdown(c)
        prov = providers.current()
        from apps.rewards.services import balance as reward_balance

        recent = T.objects.filter(customer=c).select_related("payment__order__store")[:6]
        last = T.objects.filter(customer=c).first()
        return Response({
            "balance": f"{services.balance(c):.2f}", "currency": settings.CLICK_DEFAULT_CURRENCY,
            "status": acc.status, "status_label": acc.get_status_display(), "status_reason": acc.status_reason,
            "breakdown": {"cash": f"{b['cash']:.2f}", "promo": f"{b['promo']:.2f}", **{k: f"{v:.2f}" for k, v in b["by_kind"].items()}},
            "expiring": [{"id": str(lot.id), "kind": lot.kind, "kind_label": lot.get_kind_display(), "description": lot.description,
                          "remaining": f"{r:.2f}", "expires_at": lot.expires_at.isoformat()} for lot, r in b["expiring"]],
            "credits": [{"id": str(lot.id), "kind": lot.kind, "kind_label": lot.get_kind_display(), "description": lot.description,
                         "remaining": f"{r:.2f}", "expires_at": lot.expires_at.isoformat() if lot.expires_at else None} for lot, r in services.lots(c)],
            "limits": {k: f"{v:.2f}" for k, v in services.limits().items()},
            "top_up_available": prov is not None and acc.status == "active",
            "top_up": {"provider": prov.name, "test_mode": getattr(prov, "test_mode", False), "methods": list(prov.methods),
                       "presets": ["100", "500", "1000", "2000"]} if prov else None,
            "eligible_services": [{"code": c_, "label": l, "path": p, "wallet": True} for c_, l, p in ELIGIBLE],
            "partial_payment": False,
            "rewards_points": reward_balance(c)["balance"],
            "summary": _summary(c), "last_updated": last.created_at.isoformat() if last else None,
            "transactions": [txn_out(t) for t in recent],
        })


class TransactionsView(APIView):
    """GET /customer/wallet/transactions?filter=&q=&page= — the wallet ledger, newest first, 20 per page."""

    permission_classes = [IsCustomer]

    def get(self, request):
        qs = T.objects.filter(customer=request.user.customer_profile).select_related("payment__order__store", "payment__wallet_topup")
        f = request.query_params.get("filter")
        if f in FILTERS:
            qs = qs.filter(FILTERS[f])
        q = (request.query_params.get("q") or "").strip()[:60]
        if q:
            num = q.replace("₹", "").replace(",", "").strip()
            cond = Q(description__icontains=q)
            for kind, label in T.Kind.choices:
                if q.lower() in label.lower():
                    cond |= Q(kind=kind)
            if num.replace(".", "", 1).isdigit():
                cond |= Q(amount=Decimal(num)) | Q(amount=-Decimal(num))
            qs = qs.filter(cond)
        page = max(1, int(request.query_params.get("page") or 1)) if str(request.query_params.get("page") or "1").isdigit() else 1
        rows = list(qs[(page - 1) * 20: page * 20 + 1])
        return Response({"results": [txn_out(t) for t in rows[:20]], "has_next": len(rows) > 20, "page": page})


class TransactionDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        t = get_object_or_404(T.objects.filter(customer=request.user.customer_profile).select_related("payment", "lot"), pk=pk)
        return Response(txn_out(t, full=True))


class TopUpInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    method = serializers.ChoiceField(choices=["upi", "card", "netbanking"])
    idempotency_key = serializers.CharField(max_length=64)


def topup_out(t: WalletTopUp) -> dict:
    return {"id": str(t.id), "amount": f"{t.amount:.2f}", "method": t.method, "status": t.status, "status_label": t.get_status_display(),
            "provider": t.provider, "provider_reference": t.provider_reference, "failure_reason": t.failure_reason,
            "transaction_id": str(t.wallet_transaction_id) if t.wallet_transaction_id else None, "payment_id": str(t.payment_id) if t.payment_id else None,
            "created_at": t.created_at.isoformat()}


class TopUpsView(APIView):
    """POST /customer/wallet/top-ups — creates an intent with the payment provider. The wallet is NOT credited here."""

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def post(self, request):
        s = TopUpInput(data=request.data)
        s.is_valid(raise_exception=True)
        t, client = services.start_topup(request.user.customer_profile, s.validated_data["amount"], s.validated_data["method"], s.validated_data["idempotency_key"])
        return Response({**topup_out(t), "client": client}, status=status.HTTP_201_CREATED)


class TopUpDetailView(APIView):
    """GET /customer/wallet/top-ups/<id> — the real status (check it after a network interruption before retrying)."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        services.expire_topups()
        return Response(topup_out(get_object_or_404(WalletTopUp, pk=pk, customer=request.user.customer_profile)))


class SandboxPayView(APIView):
    """POST /customer/wallet/top-ups/<id>/sandbox {outcome} — test mode only: Click. plays the provider and sends the
    signed event through the same verified path as a real provider. Unavailable when the sandbox is off."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        prov = providers.current()
        if not isinstance(prov, providers.SandboxProvider):
            raise DomainError("Not available.", code="not_found", status_code=404)
        t = get_object_or_404(WalletTopUp, pk=pk, customer=request.user.customer_profile)
        outcome = request.data.get("outcome")
        if outcome not in ("succeeded", "failed", "pending"):
            raise DomainError("Choose an outcome.", code="validation_error")
        body, sig = prov.event(t, outcome, "Declined by the test bank" if outcome == "failed" else "")
        return Response(topup_out(providers.handle_event(body, sig)))


class ProviderWebhookView(APIView):
    """POST /payments/webhooks/<provider> — provider → Click. confirmations, verified by HMAC signature; idempotent."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    def post(self, request, provider):
        prov = providers.current()
        if prov is None or prov.name != provider:
            raise DomainError("Unknown provider.", code="not_found", status_code=404)
        t = providers.handle_event(request.body, request.headers.get("X-Click-Signature", ""))
        return Response({"received": True, "status": t.status})


class SecurityView(APIView):
    """GET /customer/wallet/security — status, recent money-in / money-out events and how to report a problem."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        acc = services.account(c)
        recent = T.objects.filter(customer=c, kind__in=["topup", "payment", "adjustment"], created_at__gte=timezone.now() - timedelta(days=30))
        return Response({"status": acc.status, "status_label": acc.get_status_display(), "status_reason": acc.status_reason,
                         "events": [txn_out(t) for t in recent[:8]],
                         "failed_topups": WalletTopUp.objects.filter(customer=c, status="failed", created_at__gte=timezone.now() - timedelta(days=30)).count(),
                         "protections": ["Every balance change is a server-side ledger entry you can open and trace.",
                                         "Money is added only after the payment provider’s signed confirmation is verified.",
                                         "Two payments can’t spend the same balance: the wallet is locked while a payment runs.",
                                         "Click. never stores card numbers, CVVs or UPI PINs."]})
