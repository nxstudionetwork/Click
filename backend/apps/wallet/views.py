from django.conf import settings
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import WalletTransaction
from .services import balance


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ["id", "kind", "amount", "currency", "description", "created_at"]


class WalletView(APIView):
    """GET /customer/wallet — balance derived from the ledger, plus recent transactions."""

    permission_classes = [IsCustomer]

    def get(self, request):
        customer = request.user.customer_profile
        txns = WalletTransaction.objects.filter(customer=customer)[:50]
        return Response({
            "balance": f"{balance(customer):.2f}",
            "currency": settings.CLICK_DEFAULT_CURRENCY,
            "transactions": WalletTransactionSerializer(txns, many=True).data,
            "top_up_available": False,
        })
