from rest_framework import viewsets

from apps.core.api.permissions import IsCustomer

from .serializers import AddressSerializer


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
