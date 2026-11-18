from rest_framework import permissions, serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError

from . import partner as pb
from .models import BuzzPost
from .services import MAX_ITEMS, build_feed, record_event, report, toggle_reaction


class FeedQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=MAX_ITEMS, default=12)


class BuzzFeedView(APIView):
    """GET /api/v1/buzz?limit=12 — public, actionable Click. Buzz feed (partner posts, offers, shows and stores)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = FeedQuerySerializer(data=request.query_params)
        q.is_valid(raise_exception=True)
        return Response({"results": build_feed(q.validated_data["limit"], request.user)})


# --- engagement (Customer App and Partner App) ---------------------------------------------------------------------

class ReactionView(APIView):
    """POST /api/v1/buzz/posts/<id>/like|save — toggles; returns {on, count}."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "buzz"

    def post(self, request, pk, kind):
        return Response(toggle_reaction(request.user, pk, kind))


class EventView(APIView):
    """POST /api/v1/buzz/posts/<id>/event {kind: view|click} — counted once per viewer per day."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "buzz"

    def post(self, request, pk):
        from apps.discover.engine import viewer_key

        kind = (request.data or {}).get("kind")
        if kind not in ("view", "click"):
            raise DomainError("Unknown event.", code="validation_error")
        return Response({"counted": record_event(pk, kind, viewer_key(request))})


class ReportView(APIView):
    """POST /api/v1/buzz/posts/<id>/report {reason, note} — goes to Click moderation."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "buzz"

    def post(self, request, pk):
        d = request.data if isinstance(request.data, dict) else {}
        report(request.user, pk, d.get("reason", ""), d.get("note", ""))
        return Response({"ok": True}, status=201)


# --- Partner App -----------------------------------------------------------------------------------------------------

def _partner(request):
    from apps.partners.services import require_owned_partner

    partner = require_owned_partner(request.user)
    if not partner.is_onboarded:
        raise DomainError("Finish setting up your Partner profile first.", code="onboarding_incomplete", status_code=409)
    return partner


def _body(request) -> dict:
    return request.data if isinstance(request.data, dict) else {}


class PartnerBuzzView(APIView):
    """GET /partner/buzz?status= — own posts, performance and what posts can link to. POST — create (submit: bool)."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "partner_onboarding"

    def get(self, request):
        return Response(pb.overview(_partner(request), request.query_params.get("status", "")))

    def post(self, request):
        partner = _partner(request)
        body = _body(request)
        post = pb.save_post(partner, body, submit=bool(body.get("submit")))
        return Response(pb.post_dict(post), status=201)


class PartnerBuzzPostView(APIView):
    """PATCH /partner/buzz/<id> (edit; a reviewed post goes back to review) · DELETE."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "partner_onboarding"

    def _post(self, request, pk):
        partner = _partner(request)
        post = BuzzPost.objects.filter(partner=partner, pk=pk).first()
        if post is None:
            raise DomainError("That post wasn't found.", code="not_found", status_code=404)
        return partner, post

    def patch(self, request, pk):
        partner, post = self._post(request, pk)
        body = _body(request)
        return Response(pb.post_dict(pb.save_post(partner, body, post, submit=bool(body.get("submit")))))

    def delete(self, request, pk):
        partner, post = self._post(request, pk)
        pb.act(partner, post.pk, "delete")
        return Response(status=204)


class PartnerBuzzActionView(APIView):
    """POST /partner/buzz/<id>/<submit|withdraw|pause|resume|archive|restore>."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "partner_onboarding"

    def post(self, request, pk, action):
        post = pb.act(_partner(request), pk, action)
        return Response(pb.post_dict(post) if post else None)


class PartnerBuzzMediaView(APIView):
    """POST /partner/buzz/media (multipart `file`) → {id, kind, url, ...}. DELETE /partner/buzz/media/<id>."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "uploads"

    def post(self, request):
        return Response(pb.media_dict(pb.upload_media(_partner(request), request.FILES.get("file"))), status=201)

    def delete(self, request, pk):
        pb.discard_media(_partner(request), pk)
        return Response(status=204)


class PartnerBuzzCommunityView(APIView):
    """GET /partner/buzz/community — live posts from fellow Click partners (both audiences)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .models import BuzzReaction

        partner = _partner(request)
        posts = list(pb.live_posts(audience=None).exclude(partner=partner).order_by("-publish_at", "-reviewed_at")[:40])
        mine = set(BuzzReaction.objects.filter(user=request.user, post__in=posts).values_list("post_id", "kind"))
        rows = []
        for p in posts:
            d = pb.post_dict(p)
            rows.append({k: d[k] for k in ("id", "kind_label", "headline", "caption", "media", "cta_label", "link", "audience",
                                           "product", "offer", "publish_at")}
                        | {"partner": p.partner.business_name, "category": p.partner.category.name, "likes": p.likes,
                           "liked": (p.id, "like") in mine, "saved": (p.id, "save") in mine})
        return Response({"results": rows})
