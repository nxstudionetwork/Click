from rest_framework import generics, serializers

from apps.core.api.permissions import IsCustomer
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.orders.models import Order
from apps.parcels.models import ParcelOrder
from apps.professionals.models import ServiceBooking

from .models import SupportTicket


class SupportTicketSerializer(serializers.ModelSerializer):
    order_id = serializers.PrimaryKeyRelatedField(source="order", queryset=Order.objects.none(), required=False, allow_null=True)
    order_number = serializers.CharField(source="order.number", read_only=True, default=None)
    parcel_id = serializers.PrimaryKeyRelatedField(source="parcel", queryset=ParcelOrder.objects.none(), required=False, allow_null=True)
    parcel_number = serializers.CharField(source="parcel.number", read_only=True, default=None)
    service_booking_id = serializers.PrimaryKeyRelatedField(source="service_booking", queryset=ServiceBooking.objects.none(),
                                                            required=False, allow_null=True)
    service_booking_number = serializers.CharField(source="service_booking.number", read_only=True, default=None)

    class Meta:
        model = SupportTicket
        fields = ["id", "reference", "category", "subject", "message", "status", "order_id", "order_number", "parcel_id", "parcel_number", "service_booking_id", "service_booking_number", "created_at", "resolved_at"]
        read_only_fields = ["id", "reference", "status", "created_at", "resolved_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and hasattr(request.user, "customer_profile"):
            # A ticket may only reference the requester's own orders.
            self.fields["order_id"].queryset = Order.objects.filter(customer=request.user.customer_profile)
            self.fields["parcel_id"].queryset = ParcelOrder.objects.filter(customer=request.user.customer_profile)
            self.fields["service_booking_id"].queryset = ServiceBooking.objects.filter(customer=request.user.customer_profile)


class SupportTicketListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCustomer]
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        return SupportTicket.objects.filter(customer=self.request.user.customer_profile).select_related("order", "parcel", "service_booking")

    def perform_create(self, serializer):
        ticket = serializer.save(customer=self.request.user.customer_profile)
        notify(ticket.customer, NotificationCategory.SUPPORT, f"We received your request {ticket.reference}",
               "Our support team will get back to you.", f"/help/tickets/{ticket.id}")


class SupportTicketDetailView(generics.RetrieveAPIView):
    permission_classes = [IsCustomer]
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        return SupportTicket.objects.filter(customer=self.request.user.customer_profile).select_related("order", "parcel", "service_booking")
