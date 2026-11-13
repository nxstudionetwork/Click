"""Click. Offers API. Discovery is public (personalised when signed in); saving, claiming and savings belong to the
signed-in customer. Eligibility and discounts are always decided by each service at its own checkout."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import ConflictError, DomainError
from apps.core.api.permissions import IsCustomer

from . import catalog
from .models import OfferClaim, OfferSave

SORTS = {"recommended", "ending_soon", "biggest", "newest", "best_value"}


def _customer(request):
    u = request.user
    return u.customer_profile if u and u.is_authenticated and hasattr(u, "customer_profile") else None


def _decorate(rows, customer):
    saved = set(OfferSave.objects.filter(customer=customer).values_list("offer_ref", flat=True)) if customer else set()
    claimed = set(OfferClaim.objects.filter(customer=customer).values_list("offer_ref", flat=True)) if customer else set()
    for o in rows:
        o["saved"] = o["id"] in saved
        o["claimed"] = o["id"] in claimed
    return rows


def _used_services(customer) -> list[str]:
    """Services the customer has actually used (for “Picked for you”), most used first."""
    if customer is None:
        return []
    counts = {}
    for t, s in (("restaurant", "food"), ("grocery", "groceries"), ("retail", "shop")):
        counts[s] = customer.orders.filter(store__store_type=t).count()
    counts.update({"ride": customer.rides.count(), "hotels": customer.hotel_bookings.count(), "travel": customer.travel_bookings.count(),
                   "bookings": customer.experience_bookings.count(), "services": customer.service_bookings.count(), "shows": customer.bookings.count(),
                   "events": customer.event_bookings.count(), "parcel": customer.parcels.count()})
    return [s for s, n in sorted(counts.items(), key=lambda x: -x[1]) if n > 0]


def _sort(rows, how):
    far = "9999"
    if how == "ending_soon":
        return sorted(rows, key=lambda o: o["ends_at"] or far)
    if how == "biggest":
        return sorted(rows, key=lambda o: -(o["percent"] or 0) - (float(o["flat"] or 0) / 10))
    if how == "newest":
        return sorted(rows, key=lambda o: o["starts_at"] or "", reverse=True)
    if how == "best_value":
        return sorted(rows, key=lambda o: -o["value_score"])
    return sorted(rows, key=lambda o: (-o["value_score"], o["ends_at"] or far))


class HubView(APIView):
    """GET /offers/hub?service=&kind=&q=&sort= — every live offer across Click., sections built by stated rules."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        c = _customer(request)
        rows = _decorate(catalog.all_offers(c), c)
        qp = request.query_params
        feed = rows
        if qp.get("service"):
            feed = [o for o in feed if o["service"] == qp["service"]]
        if qp.get("kind"):
            feed = [o for o in feed if o["kind"] == qp["kind"] or qp["kind"] in o["badges"]]
        if q := (qp.get("q") or "").strip().lower()[:60]:
            words = [w for w in q.replace("₹", "").split() if w not in ("offers", "offer", "deals", "deal", "for", "on")]
            feed = [o for o in feed if all(w in f"{o['title']} {o['description']} {o['service_label']} {o['benefit']} {o['kind']} {(o['partner'] or {}).get('name', '')} {' '.join(o['badges'])}".lower()
                                           for w in words)]
        feed = _sort(feed, qp.get("sort") if qp.get("sort") in SORTS else "recommended")
        used = _used_services(c)
        now = timezone.now()
        soon = [o for o in rows if o["ends_at"] and timezone.datetime.fromisoformat(o["ends_at"]) - now <= timedelta(hours=72)]
        services = sorted({o["service"] for o in rows}, key=lambda s: list(catalog.SERVICE_LABEL).index(s))
        hero = sorted([o for o in rows if o["kind"] in ("discount", "coupon", "cashback")], key=lambda o: (-o["value_score"], o["ends_at"] or "9999"))[:3]
        return Response({
            "count": len(feed), "results": feed[:60],
            "services": [{"code": s, "label": catalog.SERVICE_LABEL[s], "theme": catalog.SERVICE_THEME[s], "count": sum(1 for o in rows if o["service"] == s)}
                         for s in services],
            "sections": {
                "hero": hero,
                "picked": [o for s in used for o in rows if o["service"] == s][:8],
                "ending_soon": sorted(soon, key=lambda o: o["ends_at"])[:8],
                "coupons": [o for o in rows if o["code"]][:10],
                "cashback": [o for o in rows if o["kind"] == "cashback"][:6],
                "partners": [o for o in rows if o["partner"]][:10],
                "click_offers": [o for o in rows if "click_offer" in o["badges"] and o["kind"] != "info"][:8],
                "new_user": [o for o in rows if o["new_user"]][:6],
                "best_value": sorted([o for o in rows if o["value_score"] > 0], key=lambda o: -o["value_score"])[:6],
                "boosts": [o for o in rows if o["kind"] == "reward_boost"][:4],
            },
            "picked_reason": ("Because you use " + " and ".join(catalog.SERVICE_LABEL[s] for s in used[:2])) if used else "",
            "best_value_rule": "Estimated saving at the offer’s minimum spend (or ₹500 when it has none), as a share of that spend.",
        })


class OfferView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, ref):
        c = _customer(request)
        o = catalog.get(ref, c)
        if o is None:
            raise DomainError("This offer has ended or isn’t available.", code="offer_unavailable", status_code=404)
        return Response(_decorate([o], c)[0])


class SaveView(APIView):
    """POST / DELETE /customer/offers/<ref>/save"""

    permission_classes = [IsCustomer]

    def post(self, request, ref):
        if catalog.get(ref, request.user.customer_profile) is None:
            raise DomainError("This offer has ended.", code="offer_unavailable", status_code=404)
        OfferSave.objects.get_or_create(customer=request.user.customer_profile, offer_ref=ref)
        from apps.activity.services import record

        record(request.user.customer_profile, "offer.saved", {"offer": ref})
        return Response({"saved": True}, status=status.HTTP_201_CREATED)

    def delete(self, request, ref):
        OfferSave.objects.filter(customer=request.user.customer_profile, offer_ref=ref).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClaimView(APIView):
    """POST /customer/offers/<ref>/claim — keeps a coupon on the account so the matching checkout offers it. The
    service still validates the code there (dates, minimum, usage)."""

    permission_classes = [IsCustomer]

    def post(self, request, ref):
        c = request.user.customer_profile
        o = catalog.get(ref, c)
        if o is None:
            raise DomainError("This offer has ended.", code="offer_unavailable", status_code=404)
        if not o["code"]:
            raise ConflictError("This offer doesn’t need claiming: it’s applied automatically when you qualify.", code="not_claimable")
        claim, created = OfferClaim.objects.get_or_create(customer=c, offer_ref=ref, defaults={"service": o["service"], "code": o["code"]})
        if created:
            from apps.activity.services import record

            record(c, "offer.claimed", {"offer": ref, "code": o["code"]})
        return Response({"claimed": True, "code": claim.code}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ClaimedView(APIView):
    """GET /customer/offers/claimed?service= — claimed codes still live, for the checkout to suggest."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        live = {o["id"]: o for o in catalog.all_offers(c) if o["code"]}
        rows = OfferClaim.objects.filter(customer=c)
        if request.query_params.get("service"):
            rows = rows.filter(service=request.query_params["service"])
        return Response({"results": [{"offer": r.offer_ref, "code": r.code, "title": live[r.offer_ref]["title"], "benefit": live[r.offer_ref]["benefit"]}
                                     for r in rows if r.offer_ref in live]})


def savings(customer) -> dict:
    """Discounts the customer actually got (from each service's own records) and cashback credited."""
    now = timezone.now()
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year = month.replace(month=1)
    sources = [("Food, Groceries & Shop", customer.orders.exclude(status="cancelled"), "orders"),
               ("Rides", customer.rides.exclude(status="cancelled"), "rides"),
               ("Parcel", customer.parcels.all(), "parcels"), ("Shows", customer.bookings.filter(status="confirmed"), "shows"),
               ("Services", customer.service_bookings.exclude(status__in=["cancelled", "unassigned"]), "services"),
               ("Hotels", customer.hotel_bookings.filter(status__in=["confirmed", "completed"]), "hotels"),
               ("Travel", customer.travel_bookings.filter(status__in=["confirmed", "completed"]), "travel"),
               ("Bookings", customer.experience_bookings.filter(status__in=["confirmed", "completed"]), "bookings"),
               ("Events", customer.event_bookings.exclude(status="cancelled"), "events")]
    total_m = total_y = Decimal("0")
    used = 0
    history = []
    for label, qs, _ in sources:
        with_disc = qs.filter(discount__gt=0)
        total_m += with_disc.filter(created_at__gte=month).aggregate(s=Sum("discount"))["s"] or 0
        total_y += with_disc.filter(created_at__gte=year).aggregate(s=Sum("discount"))["s"] or 0
        used += with_disc.count()
        for x in with_disc.order_by("-created_at")[:5]:
            history.append({"service": label, "title": getattr(x, "offer_title", "") or "Offer", "saved": f"{x.discount:.2f}", "at": x.created_at.isoformat(),
                            "reference": getattr(x, "number", "") or getattr(x, "reference", "")})
    cash = customer.wallet_transactions.filter(kind="cashback")
    history.sort(key=lambda h: h["at"], reverse=True)
    return {"saved_this_month": f"{total_m:.2f}", "saved_this_year": f"{total_y:.2f}", "offers_used": used,
            "cashback_earned": f"{cash.aggregate(s=Sum('amount'))['s'] or 0:.2f}", "history": history[:20]}


class MineView(APIView):
    """GET /customer/offers/mine — saved offers (with their live state), claimed codes, used offers and savings."""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = request.user.customer_profile
        live = {o["id"]: o for o in _decorate(catalog.all_offers(c), c)}
        saved = []
        for s in OfferSave.objects.filter(customer=c):
            o = live.get(s.offer_ref)
            saved.append(o if o else {"id": s.offer_ref, "expired": True, "title": "This offer has ended", "saved": True})
        return Response({"saved": saved, "claimed": [{"offer": x.offer_ref, "code": x.code, "service": x.service, "live": x.offer_ref in live,
                                                      "title": live[x.offer_ref]["title"] if x.offer_ref in live else "Ended"} for x in OfferClaim.objects.filter(customer=c)],
                         "savings": savings(c)})
