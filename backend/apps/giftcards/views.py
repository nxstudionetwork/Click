"""Gift Cards API."""

from __future__ import annotations

import re

from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import services
from .models import GiftCard, GiftCardDesign

SERVICE_LABEL = {"food": "Food", "groceries": "Groceries", "shop": "Shop"}


def design_out(d: GiftCardDesign) -> dict:
    return {"id": str(d.id), "title": d.title, "category": d.category, "category_label": d.get_category_display(), "occasion": d.occasion,
            "tagline": d.tagline, "colors": d.colors, "min_amount": f"{d.min_amount:.2f}", "max_amount": f"{d.max_amount:.2f}",
            "presets": [str(p) for p in d.presets], "validity_days": d.validity_days,
            "services": [{"code": s, "label": SERVICE_LABEL.get(s, s)} for s in d.services], "terms": d.terms}


def card_out(c: GiftCard, viewer) -> dict:
    holder = c.holder_id == viewer.id
    bought = c.buyer_id == viewer.id
    show_code = holder or (bought and c.status in (GiftCard.Status.ACTIVE, GiftCard.Status.USED) and not c.holder_id)
    out = {"id": str(c.id), "design": design_out(c.design), "amount": f"{c.amount:.2f}", "balance": f"{services.balance(c):.2f}",
           "status": c.status, "status_label": c.get_status_display(), "recipient_name": c.recipient_name, "message": c.message,
           "delivery": c.delivery, "delivery_label": c.get_delivery_display(), "deliver_on": c.deliver_on.isoformat() if c.deliver_on else None,
           "delivered_at": c.delivered_at.isoformat() if c.delivered_at else None, "expires_at": c.expires_at.isoformat() if c.expires_at else None,
           "from_name": (c.buyer.user.full_name or "").split(" ")[0], "role": "holder" if holder else "buyer",
           "redeemed": bool(c.holder_id), "code": c.code if show_code else f"••••-••••-••••-{c.code[-4:]}", "created_at": c.created_at.isoformat()}
    if holder or bought:
        out["entries"] = [{"id": str(e.id), "kind": e.kind, "kind_label": e.get_kind_display(), "amount": f"{e.amount:.2f}", "description": e.description,
                           "at": e.created_at.isoformat(), "payment_id": str(e.payment_id) if e.payment_id else None}
                          for e in c.entries.all()] if holder else []
    return out


class DesignsView(APIView):
    """GET /gift-cards — designs by category (public)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ds = list(GiftCardDesign.objects.filter(is_active=True))
        cats = []
        for code, label in GiftCardDesign.Category.choices:
            rows = [design_out(d) for d in ds if d.category == code]
            if rows:
                cats.append({"code": code, "label": label, "designs": rows})
        return Response({"categories": cats})


class PurchaseInput(serializers.Serializer):
    design_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=8, decimal_places=2)
    recipient_name = serializers.CharField(min_length=1, max_length=80)
    recipient_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    message = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    delivery = serializers.ChoiceField(choices=GiftCard.Delivery.choices)
    deliver_on = serializers.DateField(required=False, allow_null=True, default=None)
    payment_method = serializers.ChoiceField(choices=["wallet", "upi", "card", "netbanking"])
    idempotency_key = serializers.CharField(max_length=64)

    def validate_recipient_phone(self, v):
        v = v.replace(" ", "")
        if v and not re.fullmatch(r"\+[1-9]\d{7,14}", v):
            raise serializers.ValidationError("Enter the number with its country code, e.g. +91 98765 43210.")
        return v


class MyCardsView(APIView):
    """GET /customer/gift-cards → {held, sent}; POST buys one."""

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def get(self, request):
        c = request.user.customer_profile
        held = GiftCard.objects.filter(holder=c).select_related("design", "buyer__user")
        sent = GiftCard.objects.filter(buyer=c).exclude(holder=c).select_related("design", "buyer__user")
        return Response({"held": [card_out(x, c) for x in held], "sent": [card_out(x, c) for x in sent]})

    def post(self, request):
        s = PurchaseInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        card, intent = services.purchase(request.user.customer_profile, design_id=d["design_id"], amount=d["amount"], recipient_name=d["recipient_name"],
                                         recipient_phone=d["recipient_phone"], message=d["message"], delivery=d["delivery"], deliver_on=d["deliver_on"],
                                         method=d["payment_method"], idempotency_key=d["idempotency_key"])
        card.refresh_from_db()
        return Response({**card_out(card, request.user.customer_profile), "payment_intent": intent}, status=status.HTTP_201_CREATED)


class CardView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        c = request.user.customer_profile
        card = GiftCard.objects.filter(pk=pk).select_related("design", "buyer__user").first()
        if card is None or c.id not in (card.buyer_id, card.holder_id):
            raise DomainError("Not found.", code="not_found", status_code=404)
        out = card_out(card, c)
        if card.buyer_id == c.id:
            p = card.payments.order_by("-created_at").first()
            if p and p.method in ("upi", "card", "netbanking") and p.provider_reference:
                from apps.payments.gateway import intent

                out["payment_intent"] = intent(p.provider_reference)
        return Response(out)


class RedeemView(APIView):
    """POST /customer/gift-cards/redeem {code}"""

    permission_classes = [IsCustomer]
    throttle_scope = "auth"  # code guessing is limited like sign-in

    def post(self, request):
        code = str(request.data.get("code") or "")
        card = services.redeem(request.user.customer_profile, code)
        return Response(card_out(card, request.user.customer_profile))


class UsableView(APIView):
    """GET /customer/gift-cards/usable?service= — your cards that can pay at this checkout."""

    permission_classes = [IsCustomer]

    def get(self, request):
        service = request.query_params.get("service", "")
        rows = services.usable(request.user.customer_profile, service)
        return Response({"results": [{"id": str(c.id), "title": c.design.title, "balance": f"{b:.2f}", "code_end": c.code[-4:],
                                      "expires_at": c.expires_at.isoformat() if c.expires_at else None} for c, b in rows]})
