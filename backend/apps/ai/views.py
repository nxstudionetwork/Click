import logging

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from .providers import AIContext, AIMessage, AIUnavailable, BuddyReply, get_provider

logger = logging.getLogger(__name__)


class MessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=2000)


class AssistantRequestSerializer(serializers.Serializer):
    messages = MessageSerializer(many=True, min_length=1, max_length=20)


def customer_context(customer) -> AIContext:
    recent = list(customer.orders.select_related("store").order_by("-created_at")[:5])
    return AIContext(
        surface="customer",
        actor_id=str(customer.id),
        facts={"recent_orders": [{"number": o.number, "store": o.store.name, "status": o.status} for o in recent]},
        customer=customer,
    )


class CustomerAssistantView(APIView):
    """POST /customer/assistant/messages — Buddy, Click's AI, for customers (role-scoped context and tools)."""

    permission_classes = [IsCustomer]
    throttle_scope = "ai"

    def post(self, request):
        s = AssistantRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            provider = get_provider()
        except AIUnavailable:
            raise DomainError("Buddy isn't available right now.", code="ai_unavailable", status_code=503)
        messages = [AIMessage(**m) for m in s.validated_data["messages"]]
        try:
            reply = provider.reply(messages, customer_context(request.user.customer_profile))
        except Exception:
            logger.exception("AI provider failed")
            raise DomainError("Buddy couldn't answer right now. Please try again.", code="ai_error", status_code=502)
        if isinstance(reply, str):
            reply = BuddyReply(reply)
        return Response({
            "message": {"role": "assistant", "content": reply.content},
            "cards": reply.cards,
            "actions": reply.actions,
            "mode": getattr(provider, "mode", "provider"),
        })
