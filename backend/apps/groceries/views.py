"""
Click. Groceries API. Public discovery endpoints work signed out (location from `lat`/`lng`); signed-in customers
can pass `address=<id>` (their own saved address only) and get personal sections. Customer endpoints are scoped to
the authenticated customer; ids from the client are never trusted as identity.
"""

from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.carts.models import Cart, CartItem
from apps.carts.serializers import CartSerializer
from apps.carts.services import add_item, cart_items, get_or_create_cart
from apps.catalog.models import Product
from apps.catalog.pricing import price_of
from apps.core.api.exceptions import DomainError
from apps.core.api.permissions import IsCustomer
from apps.orders.models import Order
from apps.orders.serializers import CheckoutSerializer, OrderSummarySerializer
from apps.orders.services import place_checkout
from apps.payments.models import PaymentMethod
from apps.stores.models import StoreType

from . import catalog as cat
from . import checkout as gco
from . import discovery, lists, search
from .models import GroceryOrderDetails, ShoppingList, ShoppingListItem, StockAlert


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


def _location(request):
    """(point, address) from `address` (the caller's own) or `lat`/`lng`. Invalid input means no location."""
    customer = _customer(request)
    addr_id = request.query_params.get("address") or (request.data.get("address_id") if isinstance(request.data, dict) else None)
    if addr_id and customer is not None:
        try:
            address = customer.addresses.filter(pk=uuid.UUID(str(addr_id))).first()
        except ValueError:
            address = None
        if address is not None:
            from .delivery import address_point

            return address_point(address), address
    try:
        lat, lng = float(request.query_params["lat"]), float(request.query_params["lng"])
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return (lat, lng), None
    except (KeyError, ValueError):
        pass
    return None, None


class HomeView(APIView):
    """GET /groceries/home?address|lat&lng"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        point, _ = _location(request)
        return Response(discovery.home(_customer(request), point))


class SearchView(APIView):
    """GET /groceries/search?q&category&brand&store&min_price&max_price&in_stock&offers&dietary&min_rating&max_eta&sort&page"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        point, _ = _location(request)
        data = search.search(request.query_params, point)
        if (c := _customer(request)) is not None and data["query"].strip() and request.query_params.get("page", "1") == "1":
            record(c, "grocery.searched", {"q": data["query"].strip()[:60], "results": data["count"]})
        return Response(data)


class SuggestView(APIView):
    """GET /groceries/suggest?q — typeahead; without q: recent searches (signed in) and popular near you."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        point, _ = _location(request)
        q = request.query_params.get("q", "")[:60]
        if q.strip():
            return Response(search.suggest(q, point))
        recent = []
        if (c := _customer(request)) is not None:
            from apps.activity.models import CustomerActivity

            for m in CustomerActivity.objects.filter(customer=c, verb="grocery.searched").values_list("metadata", flat=True)[:40]:
                term = (m or {}).get("q", "").strip()
                if term and term.lower() not in [r.lower() for r in recent]:
                    recent.append(term)
                if len(recent) == 6:
                    break
        return Response({"recent": recent, "popular": discovery.popular_terms(cat.deliverable_stores(point))})


class RecentSearchesView(APIView):
    """DELETE /customer/groceries/recent-searches — clear the caller's grocery search history."""

    permission_classes = [IsCustomer]

    def delete(self, request):
        from apps.activity.models import CustomerActivity

        CustomerActivity.objects.filter(customer=request.user.customer_profile, verb="grocery.searched").delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StoreView(APIView):
    """GET /groceries/stores/<slug>"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        store = get_object_or_404(cat.grocery_stores().select_related("grocery").prefetch_related("categories"), slug=slug)
        point, _ = _location(request)
        if (c := _customer(request)) is not None:
            record(c, "grocery.store_viewed", obj=store)
        return Response(discovery.store_page(store, point, _customer(request)))


class StoreProductsView(APIView):
    """GET /groceries/stores/<slug>/products?category&q&sort&page — this store's own listings only."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        store = get_object_or_404(cat.grocery_stores(), slug=slug)
        point, _ = _location(request)
        qs = cat.visible_listings().filter(store=store)
        if c := request.query_params.get("category"):
            qs = qs.filter(grocery_item__category__slug=c)
        if words := search.tokens(request.query_params.get("q", "")):
            qs = qs.filter(search.text_filter(words) | Q(grocery_item__category__in=search.matching_categories(words))).distinct()
        rows = list(qs[:400])
        from apps.catalog.pricing import attach_deals

        attach_deals(rows)
        sort = request.query_params.get("sort", "popular")
        keys = {"price_low": lambda p: price_of(p).price, "price_high": lambda p: -price_of(p).price,
                "new": lambda p: -p.created_at.timestamp(), "rating": lambda p: -float(p.rating_average)}
        rows.sort(key=lambda p: (not (p.is_orderable and store.is_accepting_orders), keys.get(sort, lambda p: -p.units_sold)(p),
                                 p.grocery_item.category.position, p.grocery_item.name))
        from .delivery import headline

        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except ValueError:
            page = 1
        size = 40
        chunk = rows[(page - 1) * size: page * size]
        ctx = {"stores": {store.id: headline(store, point)}}
        return Response({"count": len(rows), "page": page, "has_more": page * size < len(rows), "results": cat.cards(chunk, ctx)})


class ProductView(APIView):
    """GET /groceries/products/<id>"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        product = get_object_or_404(cat.visible_listings(), pk=pk)
        point, _ = _location(request)
        c = _customer(request)
        if c is not None:
            record(c, "grocery.product_viewed", obj=product)
        return Response(discovery.product_detail(product, point, c))


# --- customer: basket & checkout ---------------------------------------------------------------------------------

class DeliveryChoice(serializers.Serializer):
    mode = serializers.ChoiceField(choices=GroceryOrderDetails.Mode.choices)
    slot_start = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=40)


class QuoteSerializer(serializers.Serializer):
    address_id = serializers.UUIDField(required=False, allow_null=True)
    delivery = serializers.DictField(child=DeliveryChoice(), required=False, default=dict)


class CheckoutInput(QuoteSerializer):
    address_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=[PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.WALLET, "upi", "card", "netbanking"])
    idempotency_key = serializers.UUIDField()
    substitution = serializers.ChoiceField(choices=GroceryOrderDetails.Substitution.choices)
    substitution_note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    customer_note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


def _basket_response(customer, address, choices=None):
    cart = Cart.objects.select_related("store", "offer").get(pk=get_or_create_cart(customer).pk)
    data = CartSerializer(cart).data
    if cart.mode != Cart.Mode.BASKET:
        return {"cart": data, "grocery": None}
    info = gco.basket(cart, address, choices)
    alt_ids = {a for u in info["unavailable"] for a in u["alternatives"]}
    alts = {c["id"]: c for c in cat.cards(cat.visible_listings().filter(pk__in=alt_ids))} if alt_ids else {}
    for u in info["unavailable"]:
        u["alternatives"] = [alts[a] for a in u["alternatives"] if a in alts]
    grocery_cards = {c["id"]: c for c in cat.cards(Product.objects.filter(pk__in=[i["product"]["id"] for i in data["items"]])
                                                   .select_related("store", "grocery_item", "grocery_item__category")
                                                   .filter(grocery_item__isnull=False))}
    for i in data["items"]:
        i["listing"] = grocery_cards.get(i["product"]["id"])
    return {"cart": data, "grocery": info}


class BasketView(APIView):
    """GET /customer/groceries/basket?address=<id> — the basket priced for an address, per store."""

    permission_classes = [IsCustomer]

    def get(self, request):
        _, address = _location(request)
        return Response(_basket_response(request.user.customer_profile, address))


class QuoteView(APIView):
    """POST /customer/groceries/basket/quote {addressId, delivery: {storeId: {mode, slotStart}}}"""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = QuoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        address = c.addresses.filter(pk=s.validated_data.get("address_id")).first() if s.validated_data.get("address_id") else None
        return Response(_basket_response(c, address, s.validated_data["delivery"]))


class AcknowledgePricesView(APIView):
    """POST /customer/groceries/basket/acknowledge-prices — the customer has seen the new prices."""

    permission_classes = [IsCustomer]

    @transaction.atomic
    def post(self, request):
        c = request.user.customer_profile
        cart = get_or_create_cart(c)
        for i in cart_items(cart):
            now = price_of(i.product, i.variant).price
            if i.price_seen != now:
                CartItem.objects.filter(pk=i.pk).update(price_seen=now)
        _, address = _location(request)
        return Response(_basket_response(c, address))


class CheckoutView(APIView):
    """POST /customer/groceries/checkout — one order per store; nothing is created unless every store's part passes."""

    permission_classes = [IsCustomer]
    throttle_scope = "order_placement"

    def post(self, request):
        s = CheckoutInput(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        customer = request.user.customer_profile
        cart = get_or_create_cart(customer)
        if cart.mode != Cart.Mode.BASKET and not Order.objects.filter(customer=customer, idempotency_key=v["idempotency_key"]).exists():
            raise DomainError("Your basket has no grocery items.", code="cart_empty")
        record(customer, "grocery.checkout_started", {"stores": len(v["delivery"])})
        checkout, orders, created = place_checkout(
            customer=customer, address_id=v["address_id"], payment_method=v["payment_method"],
            idempotency_key=v["idempotency_key"], customer_note=v["customer_note"],
            grocery={"delivery": v["delivery"], "substitution": v["substitution"], "substitution_note": v["substitution_note"]},
        )
        rows = Order.objects.filter(customer=customer, pk__in=[o.pk for o in orders]).select_related("store").prefetch_related("items", "payments")
        return Response({"checkout": CheckoutSerializer(checkout).data if checkout else None,
                         "orders": OrderSummarySerializer(rows.order_by("created_at"), many=True).data},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BuyAgainView(APIView):
    """GET /customer/groceries/buy-again?address — items from delivered grocery orders, at today's prices and stock."""

    permission_classes = [IsCustomer]

    def get(self, request):
        point, _ = _location(request)
        c = request.user.customer_profile
        return Response({"results": discovery.buy_again(c, point), "running_low": discovery.running_low(c, point)})


class ReorderView(APIView):
    """POST /customer/groceries/orders/<id>/reorder — add a delivered order's items to the basket at today's prices.
    Nothing is cloned blindly: unavailable items are skipped and listed, and price changes are reported."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        c = request.user.customer_profile
        order = get_object_or_404(Order.objects.filter(customer=c, store__store_type=StoreType.GROCERY), pk=pk)
        added, skipped, changed = [], [], []
        for oi in order.items.select_related("product", "product__store"):
            p = oi.product
            if p is None or not (p.is_orderable and p.store.is_accepting_orders):
                skipped.append(oi.product_name)
                continue
            try:
                add_item(c, p.id, min(oi.quantity, p.stock_quantity) if p.stock_quantity is not None else oi.quantity)
            except DomainError:
                skipped.append(oi.product_name)
                continue
            now = price_of(p).price
            added.append(oi.product_name)
            if now != oi.unit_price:
                changed.append({"name": oi.product_name, "from": f"{oi.unit_price:.2f}", "to": f"{now:.2f}"})
        record(c, "grocery.reordered", {"added": len(added), "skipped": len(skipped)}, obj=order)
        return Response({"added": added, "skipped": skipped, "price_changes": changed})


class AlertSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=False)
    store_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if bool(data.get("product_id")) == bool(data.get("store_id")):
            raise serializers.ValidationError("Choose a product or a store.")
        return data


class AlertsView(APIView):
    """POST /customer/groceries/alerts {productId|storeId} — notify me once when it's available; DELETE cancels."""

    permission_classes = [IsCustomer]

    def post(self, request):
        s = AlertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        if pid := s.validated_data.get("product_id"):
            p = get_object_or_404(cat.visible_listings(), pk=pid)
            if p.is_orderable:
                raise DomainError("This item is in stock now.", code="already_available")
            StockAlert.objects.get_or_create(customer=c, product=p, notified_at=None)
        else:
            st = get_object_or_404(cat.grocery_stores(), pk=s.validated_data["store_id"])
            if st.is_open:
                raise DomainError("This store is taking orders now.", code="already_available")
            StockAlert.objects.get_or_create(customer=c, store=st, notified_at=None)
        record(c, "grocery.alert_set")
        return Response({"ok": True}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        s = AlertSerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        StockAlert.objects.filter(customer=request.user.customer_profile, notified_at__isnull=True,
                                  product_id=s.validated_data.get("product_id"), store_id=s.validated_data.get("store_id")).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- shopping lists ----------------------------------------------------------------------------------------------

def _list_out(sl: ShoppingList) -> dict:
    return {"id": str(sl.id), "name": sl.name, "updated_at": sl.updated_at.isoformat(),
            "items": [{"id": str(i.id), "text": i.text, "quantity": i.quantity, "is_done": i.is_done,
                       "item_id": str(i.item_id) if i.item_id else None} for i in sl.items.all()]}


class ListInput(serializers.Serializer):
    name = serializers.CharField(max_length=60, required=False, default="My list")
    items = serializers.ListField(child=serializers.CharField(max_length=80), required=False, default=list, max_length=60)


class ListItemInput(serializers.Serializer):
    text = serializers.CharField(max_length=80, required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=50, required=False)
    is_done = serializers.BooleanField(required=False)
    item_id = serializers.UUIDField(required=False, allow_null=True)


def _own_list(request, pk) -> ShoppingList:
    return get_object_or_404(ShoppingList.objects.prefetch_related("items"), pk=pk, customer=request.user.customer_profile)


class ListsView(APIView):
    """GET /customer/groceries/lists ; POST {name?, items?: ["milk", ...]}"""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = ShoppingList.objects.filter(customer=request.user.customer_profile).prefetch_related("items")[:20]
        return Response({"results": [_list_out(sl) for sl in rows]})

    @transaction.atomic
    def post(self, request):
        s = ListInput(data=request.data)
        s.is_valid(raise_exception=True)
        c = request.user.customer_profile
        if ShoppingList.objects.filter(customer=c).count() >= 20:
            raise DomainError("You can keep up to 20 lists.", code="limit_reached")
        sl = ShoppingList.objects.create(customer=c, name=s.validated_data["name"].strip() or "My list")
        texts = [t.strip() for t in s.validated_data["items"] if t.strip()]
        ShoppingListItem.objects.bulk_create([ShoppingListItem(shopping_list=sl, text=t, position=i) for i, t in enumerate(texts)])
        return Response(_list_out(_own_list(request, sl.pk)), status=status.HTTP_201_CREATED)


class ListDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        return Response(_list_out(_own_list(request, pk)))

    def patch(self, request, pk):
        sl = _own_list(request, pk)
        name = str(request.data.get("name", "")).strip()[:60]
        if name:
            sl.name = name
            sl.save(update_fields=["name", "updated_at"])
        return Response(_list_out(sl))

    def delete(self, request, pk):
        _own_list(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListItemsView(APIView):
    """POST /customer/groceries/lists/<id>/items {text, quantity?, itemId?}"""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        sl = _own_list(request, pk)
        s = ListItemInput(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if not (v.get("text") or "").strip():
            raise DomainError("Type what you need.", code="validation_error", details={"text": ["Enter an item."]})
        if sl.items.count() >= 60:
            raise DomainError("A list can hold up to 60 items.", code="limit_reached")
        ShoppingListItem.objects.create(shopping_list=sl, text=v["text"].strip(), quantity=v.get("quantity", 1),
                                        item_id=v.get("item_id"), position=sl.items.count())
        sl.save(update_fields=["updated_at"])
        return Response(_list_out(_own_list(request, pk)), status=status.HTTP_201_CREATED)


class ListItemDetailView(APIView):
    permission_classes = [IsCustomer]

    def patch(self, request, pk, item_pk):
        sl = _own_list(request, pk)
        li = get_object_or_404(sl.items, pk=item_pk)
        s = ListItemInput(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        for k, val in s.validated_data.items():
            setattr(li, k, val.strip() if isinstance(val, str) else val)
        li.save()
        sl.save(update_fields=["updated_at"])
        return Response(_list_out(_own_list(request, pk)))

    def delete(self, request, pk, item_pk):
        sl = _own_list(request, pk)
        get_object_or_404(sl.items, pk=item_pk).delete()
        return Response(_list_out(_own_list(request, pk)))


class FindEverythingView(APIView):
    """POST /customer/groceries/lists/<id>/find?address=<id> — which nearby stores have the list."""

    permission_classes = [IsCustomer]

    def post(self, request, pk):
        sl = _own_list(request, pk)
        point, _ = _location(request)
        record(request.user.customer_profile, "grocery.list_matched", obj=sl)
        return Response(lists.find_everything(sl, point))

