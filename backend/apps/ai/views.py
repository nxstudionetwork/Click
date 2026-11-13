import logging

from django.conf import settings

from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from .providers import AIContext, AIMessage, AIUnavailable, BuddyReply, get_provider
from .speech import AUDIO_TYPES, MAX_AUDIO_BYTES, SpeechUnavailable, get_speech_provider, speech_enabled

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


class AssistantCapabilitiesView(APIView):
    """GET /customer/assistant/capabilities — what Buddy can do on this deployment (the app adapts its UI)."""

    permission_classes = [IsCustomer]

    def get(self, request):
        try:
            mode = getattr(get_provider(), "mode", "provider")
        except AIUnavailable:
            mode = "unavailable"
        return Response({"mode": mode, "voice": speech_enabled(), "visualSearch": bool(settings.CLICK_VISION_PROVIDER)})


class TranscriptionSerializer(serializers.Serializer):
    audio = serializers.FileField()
    language = serializers.RegexField(r"^[a-z]{2}(-[A-Z]{2})?$", required=False, default="en-IN")

    def validate_audio(self, f):
        if f.size > MAX_AUDIO_BYTES:
            raise serializers.ValidationError("Recording is too long.")
        if (f.content_type or "").split(";")[0] not in AUDIO_TYPES:
            raise serializers.ValidationError("Unsupported audio format.")
        return f


class AssistantTranscribeView(APIView):
    """POST /customer/assistant/transcribe (multipart `audio`) — speech to text for Buddy GO and voice search."""

    permission_classes = [IsCustomer]
    parser_classes = [MultiPartParser]
    throttle_scope = "ai"

    def post(self, request):
        if not speech_enabled():
            raise DomainError("Voice isn't available yet. Type your request instead.", code="speech_unavailable", status_code=503)
        s = TranscriptionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        audio = s.validated_data["audio"]
        try:
            text = get_speech_provider().transcribe(audio.read(), audio.content_type.split(";")[0], s.validated_data["language"])
        except SpeechUnavailable:
            raise DomainError("Voice isn't available yet. Type your request instead.", code="speech_unavailable", status_code=503)
        except Exception:
            logger.exception("Speech provider failed")
            raise DomainError("Couldn't hear that clearly. Please try again.", code="speech_error", status_code=502)
        return Response({"text": text.strip()[:500]})
