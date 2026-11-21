"""Notifications API — what Click. needs to tell the signed-in customer. Every query is scoped to them; notifications are
created only by backend events (apps.notifications.services.notify), never by a client."""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsCustomer

from .models import MUTABLE, Notification, NotificationCategory, NotificationPreference

# The inbox tabs → stored categories.
GROUPS = {"orders": ["orders", "deliveries"], "rides": ["rides"], "bookings": ["bookings"], "payments": ["payments"], "wallet": ["wallet"],
          "offers": ["offers"], "rewards": ["rewards"], "account": ["support", "system"]}


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "link_path", "priority", "is_read", "created_at"]

    def get_is_read(self, n) -> bool:
        return n.read_at is not None


def _mine(request):
    return Notification.objects.filter(customer=request.user.customer_profile)


class NotificationListView(generics.ListAPIView):
    """GET /customer/notifications?group=orders|rides|bookings|payments|wallet|offers|rewards|account&category=&unread=true&q=&page="""

    permission_classes = [IsCustomer]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = _mine(self.request)
        qp = self.request.query_params
        if qp.get("group") in GROUPS:
            qs = qs.filter(category__in=GROUPS[qp["group"]])
        elif (cat := qp.get("category")) in NotificationCategory.values:
            qs = qs.filter(category=cat)
        if qp.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        if q := (qp.get("q") or "").strip()[:60]:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
        return qs.order_by("-created_at", "-id")  # stable order: read state never reorders


class NotificationSummaryView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        unread = _mine(request).filter(read_at__isnull=True)
        return Response({"unread": unread.count(),
                         "by_group": {g: unread.filter(category__in=cats).count() for g, cats in GROUPS.items()}})


class NotificationReadView(APIView):
    """POST /customer/notifications/<id>/read ; DELETE dismisses it (the order / payment it was about is untouched)."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        n = get_object_or_404(_mine(request), pk=pk)
        if n.read_at is None:
            n.read_at = timezone.now()
            n.save(update_fields=["read_at", "updated_at"])
        return Response(NotificationSerializer(n).data)

    def delete(self, request, pk):
        get_object_or_404(_mine(request), pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationUnreadView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        n = get_object_or_404(_mine(request), pk=pk)
        n.read_at = None
        n.save(update_fields=["read_at", "updated_at"])
        return Response(NotificationSerializer(n).data)


class NotificationReadAllView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        qs = _mine(request).filter(read_at__isnull=True)
        if request.data.get("group") in GROUPS:
            qs = qs.filter(category__in=GROUPS[request.data["group"]])
        return Response({"updated": qs.update(read_at=timezone.now())})


class PreferencesView(APIView):
    """GET / PATCH /customer/notifications/preferences {muted: [...]} — only non-essential categories can be muted."""

    permission_classes = [IsCustomer]

    def _out(self, p):
        labels = dict(NotificationCategory.choices)
        return {"muted": p.muted, "categories": [{"code": c, "label": labels[c], "mutable": c in MUTABLE} for c in NotificationCategory.values],
                "note": "Payments, Wallet, Support and account / security notices always reach you."}

    def get(self, request):
        p, _ = NotificationPreference.objects.get_or_create(customer=request.user.customer_profile)
        return Response(self._out(p))

    def patch(self, request):
        p, _ = NotificationPreference.objects.get_or_create(customer=request.user.customer_profile)
        muted = request.data.get("muted")
        if not isinstance(muted, list):
            return Response({"error": {"code": "validation_error", "message": "Send a list of categories.", "details": {}}}, status=400)
        p.muted = sorted({m for m in muted if m in MUTABLE})
        p.save(update_fields=["muted", "updated_at"])
        return Response(self._out(p))
