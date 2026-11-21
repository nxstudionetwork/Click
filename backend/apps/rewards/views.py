"""Click. Rewards API — balance, tiers, missions, achievements, catalog and history from the ledger; redemption is the
only write, and the server decides everything about it."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from . import services
from .models import RewardCampaign, RewardCatalogItem, RewardTransaction as R

MISSION_LINK = {"food": "/food", "groceries": "/groceries", "shop": "/shopping", "ride": "/rides", "travel": "/travel", "hotels": "/hotels",
                "bookings": "/bookings", "profile": "/account", "explore": "/explore"}


def txn_out(t: R) -> dict:
    source = None
    if t.order_id:
        source = {"label": f"Order {t.order.number}", "link": f"/orders/{t.order_id}"}
    elif t.reference.startswith("travel:"):
        source = {"label": "Travel booking", "link": f"/travel/bookings/{t.reference[7:]}"}
    elif t.reference.startswith("experience:"):
        source = {"label": "Booking", "link": f"/bookings/r/{t.reference[11:]}"}
    elif t.kind == "redeem" and hasattr(t, "redemption") and t.redemption.wallet_transaction_id:
        source = {"label": "Click. Wallet credit", "link": f"/wallet/activity/{t.redemption.wallet_transaction_id}"}
    return {"id": str(t.id), "reference": str(t.id)[:8].upper(), "kind": t.kind, "kind_label": t.get_kind_display(), "points": t.points,
            "description": t.description, "order_id": str(t.order_id) if t.order_id else None, "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "created_at": t.created_at.isoformat(), "source": source, "reverses": str(t.reverses_id) if t.reverses_id else None,
            "reversed": t.reversals.exists() if t.kind == "earn" else False}


def item_out(i: RewardCatalogItem, customer, points: int, tier_code: str) -> dict:
    ok, why = services.item_state(i, customer, points, tier_code)
    return {"id": str(i.id), "title": i.title, "kind": i.kind, "kind_label": i.get_kind_display(), "description": i.description,
            "points_cost": i.points_cost, "value": f"{i.value:.2f}", "credit_valid_days": i.credit_valid_days, "min_tier": i.min_tier or None,
            "terms": i.terms, "ends_at": i.ends_at.isoformat() if i.ends_at else None, "available": ok, "reason": why,
            "affordable": points >= i.points_cost}


class RewardsView(APIView):
    """GET /customer/rewards — the whole Rewards picture for the signed-in customer."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        services.check_missions(c)
        b = services.balance(c)
        tier = services.tier_of(c)
        now = timezone.now()
        items = RewardCatalogItem.objects.filter(is_active=True).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        history = R.objects.filter(customer=c).select_related("order")[:8]
        return Response({
            "balance": b["balance"], "earned": b["earned"], "used": b["used"], "redeemed": b["redeemed"], "expired": b["expired"],
            "earned_this_month": b["earned_this_month"],
            "expiring": [{"id": str(e.id), "points": r, "description": e.description, "expires_at": e.expires_at.isoformat()} for e, r in b["expiring"]],
            "tier": {"code": tier["code"], "name": tier["name"], "multiplier": f"{tier['multiplier']}", "qualifying_points": tier["qualifying_points"],
                     "next": {"code": tier["next"]["code"], "name": tier["next"]["name"], "min_points": tier["next"]["min_points"]} if tier["next"] else None,
                     "to_next": tier["to_next"]},
            "tiers": [{"code": t["code"], "name": t["name"], "min_points": t["min_points"], "multiplier": f"{t['multiplier']}",
                       "benefits": [f"{t['multiplier']}× points on eligible purchases" if t["multiplier"] > 1 else "Earn points on eligible purchases",
                                    *(["Support requests marked important"] if t["code"] in ("gold", "platinum") else [])]} for t in services.tiers()],
            "missions": [{"code": m["mission"].code, "title": m["mission"].title, "description": m["mission"].description, "target": m["mission"].target,
                          "progress": m["progress"], "points": m["mission"].points, "completed": m["completed"], "expired": m["expired"],
                          "ends_at": m["mission"].ends_at.isoformat() if m["mission"].ends_at else None,
                          "link": MISSION_LINK.get(m["mission"].service, "/explore")} for m in services.missions(c)],
            "achievements": services.achievements(c),
            "catalog": [item_out(i, c, b["balance"], tier["code"]) for i in items],
            "campaigns": [{"id": str(x.id), "title": x.title, "description": x.description, "service": x.service, "multiplier": f"{x.multiplier}",
                           "starts_at": x.starts_at.isoformat(), "ends_at": x.ends_at.isoformat()}
                          for x in RewardCampaign.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)],
            "history": [txn_out(t) for t in history],
            "rules": {"points_per_100": settings.CLICK_REWARD_POINTS_PER_100, "expiry_days": settings.CLICK_REWARD_EXPIRY_DAYS,
                      "redemption_available": items.exists(),
                      "earn_on": ["Delivered Food, Groceries and Shop orders (on the item subtotal)", "Completed Travel journeys (on the fare)",
                                  "Completed Bookings visits (on the ticket price)", "Missions"],
                      "conversion_note": "Points have no fixed cash value; each reward shows exactly what you get for its points."},
        })


class HistoryView(APIView):
    """GET /customer/rewards/history?kind=&page= — the points ledger."""

    permission_classes = [IsCustomer]

    def get(self, request):
        qs = R.objects.filter(customer=request.user.customer_profile).select_related("order")
        if request.query_params.get("kind") in R.Kind.values:
            qs = qs.filter(kind=request.query_params["kind"])
        page = max(1, int(request.query_params.get("page") or 1)) if str(request.query_params.get("page") or "1").isdigit() else 1
        rows = list(qs[(page - 1) * 20: page * 20 + 1])
        return Response({"results": [txn_out(t) for t in rows[:20]], "has_next": len(rows) > 20, "page": page})


class HistoryDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        t = get_object_or_404(R.objects.filter(customer=request.user.customer_profile).select_related("order"), pk=pk)
        return Response(txn_out(t))


class RedeemInput(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=64)


class RedeemView(APIView):
    """POST /customer/rewards/catalog/<id>/redeem {idempotencyKey} — points deducted and the reward issued atomically."""

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def post(self, request, pk):
        s = RedeemInput(data=request.data)
        s.is_valid(raise_exception=True)
        r = services.redeem(request.user.customer_profile, pk, s.validated_data["idempotency_key"])
        return Response({"id": str(r.id), "title": r.item.title, "points": r.points, "value": f"{r.value:.2f}", "status": r.status,
                         "wallet_transaction_id": str(r.wallet_transaction_id) if r.wallet_transaction_id else None,
                         "balance": services.balance(request.user.customer_profile)["balance"]}, status=status.HTTP_201_CREATED)
