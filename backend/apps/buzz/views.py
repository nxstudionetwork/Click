from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import MAX_ITEMS, build_feed


class FeedQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=MAX_ITEMS, default=12)


class BuzzFeedView(APIView):
    """GET /api/v1/buzz?limit=12 — public, actionable Click. Buzz feed (real offers, shows and stores)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = FeedQuerySerializer(data=request.query_params)
        q.is_valid(raise_exception=True)
        return Response({"results": build_feed(q.validated_data["limit"])})
