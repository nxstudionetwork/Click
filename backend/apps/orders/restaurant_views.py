"""
/api/v1/partner/restaurant/* — Restaurant mode of Click Partner.

Every view resolves the restaurant from request.user (restaurant.require_restaurant): the partner must be a
restaurant partner and the store must be one they operate. `?store=` only chooses among the partner's own stores.
"""

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.core.api.exceptions import DomainError

from . import restaurant as r


class RestaurantView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "partner_onboarding"

    def ctx(self, request):
        return r.require_restaurant(request.user, request.query_params.get("store") or None)

    @staticmethod
    def body(request) -> dict:
        return request.data if isinstance(request.data, dict) else {}


class MenuView(RestaurantView):
    def get(self, request):
        partner, store = self.ctx(request)
        return Response({"store": r.store_summary(store, partner), **r.menu(store)})


def _category(c) -> dict:
    return {"id": str(c.id), "name": c.name, "position": c.position, "is_active": c.is_active}


class MenuCategoriesView(RestaurantView):
    def post(self, request):
        _, store = self.ctx(request)
        return Response(_category(r.create_category(store, self.body(request))), status=201)


class MenuCategoryView(RestaurantView):
    def patch(self, request, pk):
        _, store = self.ctx(request)
        return Response(_category(r.update_category(store, pk, self.body(request))))

    def delete(self, request, pk):
        _, store = self.ctx(request)
        r.delete_category(store, pk)
        return Response(status=204)


class MenuCategoryOrderView(RestaurantView):
    def post(self, request):
        _, store = self.ctx(request)
        r.reorder_categories(store, self.body(request).get("ids"))
        return Response({"ok": True})


class MenuItemsView(RestaurantView):
    def post(self, request):
        _, store = self.ctx(request)
        p = r.create_item(store, self.body(request))
        return Response(r.item_dict(Product.objects.prefetch_related("option_groups__options").get(pk=p.pk)), status=201)


class MenuItemView(RestaurantView):
    def patch(self, request, pk):
        _, store = self.ctx(request)
        return Response(r.item_dict(r.update_item(store, pk, self.body(request))))


class MenuItemOrderView(RestaurantView):
    def post(self, request):
        _, store = self.ctx(request)
        body = self.body(request)
        r.reorder_items(store, body.get("category_id"), body.get("ids"))
        return Response({"ok": True})


class OperationsView(RestaurantView):
    def get(self, request):
        _, store = self.ctx(request)
        return Response(r.operations_state(store))

    def post(self, request):
        _, store = self.ctx(request)
        return Response(r.operations_state(r.update_operations(store, self.body(request), request.user)))


class OrdersView(RestaurantView):
    def get(self, request):
        partner, store = self.ctx(request)
        return Response(r.search_orders(partner, store, request.query_params))


class KitchenView(RestaurantView):
    def get(self, request):
        partner, store = self.ctx(request)
        return Response(r.kitchen(partner, store))


class OffersView(RestaurantView):
    def get(self, request):
        _, store = self.ctx(request)
        return Response({"offers": r.offers(store)})

    def post(self, request):
        _, store = self.ctx(request)
        return Response(r.offer_dict(r.create_offer(store, self.body(request))), status=201)


class OfferActionView(RestaurantView):
    def post(self, request, pk, action):
        _, store = self.ctx(request)
        if action not in ("pause", "resume"):
            raise DomainError("Unknown action.", code="not_found", status_code=404)
        return Response(r.offer_dict(r.set_offer_paused(store, pk, action == "pause")))


class InsightsView(RestaurantView):
    def get(self, request):
        _, store = self.ctx(request)
        days = {"1": 1, "7": 7, "30": 30}.get(request.query_params.get("days", "7"), 7)
        return Response(r.insights(store, days))
