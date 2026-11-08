from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .serializers import AddressSerializer
from .summary import profile_summary


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsCustomer]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        # Ownership isolation: a customer can only ever see their own addresses.
        return self.request.user.customer_profile.addresses.all()

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user.customer_profile)


class ProfileSummaryView(APIView):
    """GET /customer/profile/summary — counts for the Profile page; scoped to the signed-in customer."""

    permission_classes = [IsCustomer]

    def get(self, request):
        return Response(profile_summary(request.user.customer_profile))
