from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import Notification, NotificationCategory


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "link_path", "is_read", "created_at"]

    def get_is_read(self, n) -> bool:
        return n.read_at is not None


def _mine(request):
    return Notification.objects.filter(customer=request.user.customer_profile)


class NotificationListView(generics.ListAPIView):
    """GET /customer/notifications?category=orders&unread=true"""

    permission_classes = [IsCustomer]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = _mine(self.request)
        if (cat := self.request.query_params.get("category")) in NotificationCategory.values:
            qs = qs.filter(category=cat)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        return qs


class NotificationSummaryView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return Response({"unread": _mine(request).filter(read_at__isnull=True).count()})


class NotificationReadView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        n = get_object_or_404(_mine(request), pk=pk)
        if n.read_at is None:
            n.read_at = timezone.now()
            n.save(update_fields=["read_at", "updated_at"])
        return Response(NotificationSerializer(n).data)


class NotificationReadAllView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        updated = _mine(request).filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": updated})
