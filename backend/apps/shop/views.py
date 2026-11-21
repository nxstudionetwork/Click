from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer

from . import reviews, services, vision
from . import serializers as S
from .listings import listings
from .models import ProductReview


class Public(APIView):
    permission_classes = [permissions.AllowAny]


class ShopHomeView(Public):
    """GET /shop/home -> campaigns, categories and the sections that have real content (personal when signed in)."""

    def get(self, request):
        return Response(services.home(request))


class ShopFeedView(Public):
    """GET /shop/feed?cursor= -> endless discovery feed (cursor pagination)."""

    def get(self, request):
        return Response(services.feed(request, request.query_params.get("cursor")))


class ShopSearchView(Public):
    """GET /shop/search?q=&category=&brand=&min_price=&max_price=&rating=&discount=&deals=&in_stock=&seller=
    &attr_<code>=a,b&opt_<axis>=a,b&sort=&page="""

    throttle_scope = "search"

    def get(self, request):
        params = {k: v for k, v in request.query_params.items()}
        data = services.search(params, request)
        if data["page"] == 1:
            services.record_search(services.customer_of(request), data["query"])
        return Response(data)


class ShopSuggestView(Public):
    def get(self, request):
        return Response(services.suggest(request.query_params.get("q", "")))


class ShopCategoriesView(Public):
    def get(self, request):
        return Response({"results": services.top_categories()})


class ShopCategoryView(Public):
    def get(self, request, slug):
        return Response(services.category_page(slug, request))


class ShopBrandsView(Public):
    def get(self, request):
        return Response({"results": services.brand_list()})


class ShopProductView(Public):
    """GET /shop/products/<id>?lat=&lng=&city= -> full product page (delivery estimate when a location is given)."""

    def get(self, request, pk):
        qp = request.query_params
        try:
            lat = float(qp["lat"]) if qp.get("lat") else None
            lng = float(qp["lng"]) if qp.get("lng") else None
        except ValueError:
            raise DomainError("Location must be numbers.", code="invalid_location")
        return Response(services.product_detail(pk, request, lat=lat, lng=lng, city=qp.get("city", "")[:100]))


class ShopProductReviewsView(Public):
    """GET /shop/products/<id>/reviews?page=&rating= -> published reviews, newest first."""

    PAGE = 10

    def get(self, request, pk):
        product = get_object_or_404(listings(), pk=pk)
        qs = ProductReview.objects.filter(product=product, status=ProductReview.Status.PUBLISHED).select_related("customer__user")
        if (r := request.query_params.get("rating")) and r.isdigit():
            qs = qs.filter(rating=int(r))
        page = max(int(request.query_params.get("page", "1") or 1), 1) if str(request.query_params.get("page", "1")).isdigit() else 1
        total = qs.count()
        items = qs[(page - 1) * self.PAGE: page * self.PAGE]
        return Response({"results": [S.review(x) for x in items], "count": total, "page": page, "has_more": page * self.PAGE < total})


class ShopCompareView(Public):
    def get(self, request):
        ids = [i for i in request.query_params.get("ids", "").split(",") if i][:4]
        try:
            import uuid

            ids = [str(uuid.UUID(i)) for i in ids]
        except ValueError:
            raise DomainError("Unknown product.", code="compare_unavailable", status_code=404)
        return Response(services.compare(ids, request))


class VisualSearchView(Public):
    """POST /shop/visual-search (multipart `image`) -> search words from the configured vision provider (503 when none)."""

    parser_classes = [MultiPartParser]

    def post(self, request):
        image = request.FILES.get("image")
        if image is None:
            raise DomainError("Choose a photo to search with.", code="image_required")
        if image.size > 8 * 1024 * 1024:
            raise DomainError("Images must be 8 MB or smaller.", code="image_too_large")
        return Response({"query": " ".join(vision.keywords_for(image))})


class ReviewInputSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class MyProductReviewView(APIView):
    """POST (create) / PATCH (edit) / DELETE the signed-in customer's review of a product they received."""

    permission_classes = [IsCustomer]

    def _save(self, request, pk, create):
        product = get_object_or_404(listings(), pk=pk)
        s = ReviewInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        r = reviews.save_review(request.user.customer_profile, product, create=create, **s.validated_data)
        return Response(S.review(ProductReview.objects.select_related("customer__user").get(pk=r.pk)),
                        status=status.HTTP_201_CREATED if create else status.HTTP_200_OK)

    def post(self, request, pk):
        return self._save(request, pk, True)

    def patch(self, request, pk):
        return self._save(request, pk, False)

    def delete(self, request, pk):
        reviews.delete_review(request.user.customer_profile, get_object_or_404(listings(), pk=pk))
        return Response(status=status.HTTP_204_NO_CONTENT)
