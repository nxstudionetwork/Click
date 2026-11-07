from django.conf import settings
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import RewardTransaction
from .services import balance


class RewardTransactionSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = RewardTransaction
        fields = ["id", "kind", "points", "description", "order_id", "expires_at", "created_at"]


class RewardsView(APIView):
    """GET /customer/rewards — balance derived from the ledger, plus recent history and earning rules."""

    permission_classes = [IsCustomer]

    def get(self, request):
        customer = request.user.customer_profile
        history = RewardTransaction.objects.filter(customer=customer)[:50]
        return Response({
            **balance(customer),
            "history": RewardTransactionSerializer(history, many=True).data,
            "rules": {
                "points_per_100": settings.CLICK_REWARD_POINTS_PER_100,
                "expiry_days": settings.CLICK_REWARD_EXPIRY_DAYS,
                "redemption_available": False,
            },
        })
