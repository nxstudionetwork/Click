"""Customer Reviews & Ratings API (shared layer over each service's reviews)."""

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.core.api.permissions import IsCustomer

from . import hub
from .models import ReviewReport


class ReviewsView(APIView):
    """GET /customer/reviews → {pending, mine}; POST {kind, targetId, rating, liked, better, aspects} writes one review."""

    permission_classes = [IsCustomer]
    throttle_scope = "reviews"

    class Input(serializers.Serializer):
        kind = serializers.ChoiceField(choices=list(hub.KINDS))
        target_id = serializers.UUIDField()
        rating = serializers.IntegerField(min_value=1, max_value=5)
        liked = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
        better = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
        aspects = serializers.DictField(child=serializers.IntegerField(min_value=1, max_value=5), required=False, default=dict)

    def get(self, request):
        c = request.user.customer_profile
        return Response({"pending": hub.pending(c), "mine": hub.history(c)})

    def post(self, request):
        s = self.Input(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        d = s.validated_data
        hub.submit(c, d["kind"], str(d["target_id"]), d["rating"], d["liked"], d["better"], d["aspects"])
        record(c, "review.submitted", {"kind": d["kind"], "rating": d["rating"]})
        return Response({"pending": hub.pending(c), "mine": hub.history(c)}, status=status.HTTP_201_CREATED)


class ReportView(APIView):
    """POST /customer/reviews/report {kind, reviewId, reason, note} — flag someone else's review for moderation."""

    permission_classes = [IsCustomer]
    throttle_scope = "reviews"

    class Input(serializers.Serializer):
        kind = serializers.CharField(max_length=20)
        review_id = serializers.UUIDField()
        reason = serializers.ChoiceField(choices=ReviewReport.Reason.choices)
        note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")

    def post(self, request):
        s = self.Input(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        created = hub.report(request.user.customer_profile, d["kind"], str(d["review_id"]), d["reason"], d["note"])
        return Response({"reported": True, "already": not created})
