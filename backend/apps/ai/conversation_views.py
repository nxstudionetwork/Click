"""Buddy conversations, actions and analytics API (customer surface). Every query is scoped to the authenticated
customer; actions are validated and permission-checked in apps.ai.actions, never trusted from the client or the AI."""

from __future__ import annotations

import logging
import time

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import actions as action_layer, conversation as conv_service
from .models import BuddyEvent, Conversation
from .providers import AIUnavailable, get_provider

logger = logging.getLogger(__name__)


def _provider():
    try:
        return get_provider()
    except AIUnavailable:
        raise DomainError("Buddy isn't available right now.", code="ai_unavailable", status_code=503)


def _own(request):
    return Conversation.objects.filter(customer=request.user.customer_profile)


class ConversationsView(APIView):
    """GET /customer/assistant/conversations?archived&page — the customer's chats; POST starts a new one."""

    permission_classes = [IsCustomer]

    def get(self, request):
        qs = _own(request).filter(archived=request.query_params.get("archived") == "true", last_message_at__isnull=False)
        raw = str(request.query_params.get("page") or "1")
        page = int(raw) if raw.isdigit() and int(raw) > 0 else 1
        rows = list(qs[(page - 1) * 20: page * 20 + 1])
        return Response({"results": [conv_service.conversation_out(c, preview=True) for c in rows[:20]], "has_more": len(rows) > 20})

    def post(self, request):
        mode = request.data.get("mode") if request.data.get("mode") in ("man", "go") else "man"
        c = Conversation.objects.create(customer=request.user.customer_profile, mode=mode)
        return Response(conv_service.conversation_out(c), status=201)


class ConversationEdit(serializers.Serializer):
    title = serializers.CharField(max_length=80, required=False)
    archived = serializers.BooleanField(required=False)


class ConversationDetailView(APIView):
    """GET a chat with its messages (nothing is re-run); PATCH rename / archive; DELETE removes it."""

    permission_classes = [IsCustomer]

    def get(self, request, pk):
        c = get_object_or_404(_own(request), pk=pk)
        return Response({**conv_service.conversation_out(c), "messages": [conv_service.message_out(m) for m in c.messages.all()[:200]]})

    def patch(self, request, pk):
        c = get_object_or_404(_own(request), pk=pk)
        s = ConversationEdit(data=request.data)
        s.is_valid(raise_exception=True)
        if "title" in s.validated_data and s.validated_data["title"].strip():
            c.title, c.title_custom = s.validated_data["title"].strip()[:80], True
        if "archived" in s.validated_data:
            c.archived = s.validated_data["archived"]
        c.save(update_fields=["title", "title_custom", "archived", "updated_at"])
        return Response(conv_service.conversation_out(c, preview=True))

    def delete(self, request, pk):
        get_object_or_404(_own(request), pk=pk).delete()
        return Response(status=204)


class MessageInput(serializers.Serializer):
    content = serializers.CharField(max_length=2000)
    via_voice = serializers.BooleanField(required=False, default=False)
    language = serializers.ChoiceField(choices=["en", "hi", "te", "kn", "ta"], required=False, default="en")
    attachment = serializers.DictField(child=serializers.CharField(max_length=120), required=False)


ATTACHABLE = {"order": "orders", "service_booking": "service_bookings", "event_booking": "event_bookings", "hotel_booking": "hotel_bookings",
              "parcel": "parcels", "address": "addresses"}


def _attachment(customer, a: dict | None) -> dict | None:
    """A Click item the customer pinned — verified to be theirs, reduced to kind / id / label."""
    if not a:
        return None
    kind, pk = a.get("kind"), a.get("id")
    rel = ATTACHABLE.get(kind or "")
    if rel is None or not hasattr(customer, rel):
        raise DomainError("That can't be attached.", code="invalid_attachment")
    try:
        obj = getattr(customer, rel).filter(pk=pk).first()
    except Exception:  # malformed id
        obj = None
    if obj is None:
        raise DomainError("That item isn't yours or doesn't exist.", code="invalid_attachment", status_code=404)
    label = getattr(obj, "number", None) or getattr(obj, "label", None) or kind
    return {"kind": kind, "id": str(obj.pk), "label": f"{kind.replace('_', ' ')} {label}"}


class ConversationMessagesView(APIView):
    """POST /customer/assistant/conversations/<id>/messages — Buddy answers from Click data (and runs safe actions)."""

    permission_classes = [IsCustomer]
    throttle_scope = "ai"

    def post(self, request, pk):
        c = get_object_or_404(_own(request), pk=pk)
        s = MessageInput(data=request.data)
        s.is_valid(raise_exception=True)
        provider = _provider()
        att = _attachment(request.user.customer_profile, s.validated_data.get("attachment"))
        t0 = time.monotonic()
        try:
            out = conv_service.run(c, s.validated_data["content"], provider, via_voice=s.validated_data["via_voice"], attachment=att,
                                   language=s.validated_data["language"])
        except DomainError:
            raise
        except Exception:
            logger.exception("AI provider failed")
            raise DomainError("Buddy couldn't answer right now. Your message is kept — try again.", code="ai_error", status_code=502)
        BuddyEvent.objects.create(customer=request.user.customer_profile, kind="message", detail=out["conversation"]["topic"][:60],
                                  latency_ms=int((time.monotonic() - t0) * 1000))
        return Response(out)


class ActionInput(serializers.Serializer):
    action = serializers.CharField(max_length=40)
    args = serializers.DictField(required=False, default=dict)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class ActionsView(APIView):
    """POST /customer/assistant/actions — run a safe action, or get the server's confirmation summary for one that needs it."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = ActionInput(data=request.data)
        s.is_valid(raise_exception=True)
        customer = request.user.customer_profile
        cid = s.validated_data.get("conversation_id")
        conv = _own(request).filter(pk=cid).first() if cid else None
        BuddyEvent.objects.create(customer=customer, kind="action_requested", detail=s.validated_data["action"][:60])
        run = action_layer.request(customer, s.validated_data["action"], s.validated_data["args"], conv)
        if run.status != "awaiting_confirmation":
            BuddyEvent.objects.create(customer=customer, kind="action_failed" if run.status == "failed" else "action_completed", detail=run.action)
        return Response(action_layer.out(run), status=409 if run.status == "failed" else 200)


class ActionDecisionView(APIView):
    """POST /customer/assistant/actions/<id>/confirm | cancel"""

    permission_classes = [IsCustomer]

    def post(self, request, pk, decision):
        customer = request.user.customer_profile
        if decision == "confirm":
            run = action_layer.confirm(customer, pk)
            BuddyEvent.objects.create(customer=customer, kind="action_failed" if run.status == "failed" else "action_completed", detail=run.action)
        elif decision == "cancel":
            run = action_layer.cancel(customer, pk)
        else:
            raise DomainError("Unknown decision.", code="validation_error")
        return Response(action_layer.out(run), status=409 if run.status == "failed" else 200)


class EventInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=BuddyEvent.KINDS)
    detail = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    latency_ms = serializers.IntegerField(min_value=0, max_value=600000, required=False, allow_null=True)


class EventsView(APIView):
    """POST /customer/assistant/events — content-free analytics (opened, mode chosen, voice outcome, navigation)."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = EventInput(data=request.data)
        s.is_valid(raise_exception=True)
        BuddyEvent.objects.create(customer=request.user.customer_profile, **s.validated_data)
        return Response(status=204)
