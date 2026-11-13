"""
Click. Pharma API.

Public:   GET /pharma/home · GET /pharma/products?category=&q=&pharmacy= · GET /pharma/products/<id>
Customer: prescriptions (upload / list / detail / file / cancel), attach a verified prescription to the cart,
          refill reminders.
Partner:  POST /partner/pharma/prescriptions/<id>/review — the pharmacy's own pharmacist decides; nothing is automatic.

Click. gives no medical advice: no diagnosis, no symptom-to-medicine suggestions, no substitutions without the
customer's and the pharmacist's say.
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.core.api.permissions import IsCustomer
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify

from .models import Prescription, RefillReminder

CATEGORIES = [  # code, label, icon — the global Pharma aisles (each product carries one)
    ("medicines", "Medicines", "receipt"), ("otc", "OTC / Non-prescription", "receipt"), ("first_aid", "First aid", "plus"),
    ("vitamins", "Vitamins & supplements", "leaf"), ("personal_care", "Personal care", "spray"), ("baby_care", "Baby care", "baby"),
    ("womens_care", "Women’s care", "user"), ("mens_care", "Men’s care", "user"), ("dental", "Dental care", "sparkle"),
    ("skin", "Skin care", "drop"), ("hair", "Hair care", "spray"), ("devices", "Medical devices", "device"), ("diabetes", "Diabetes care", "drop"),
    ("ortho", "Orthopaedic support", "dumbbell"), ("elder", "Elder care", "heart"), ("wellness", "Wellness", "leaf"), ("hygiene", "Hygiene", "spray"),
    ("monitoring", "Health monitoring", "chart"),
]
LABEL = {c: l for c, l, _ in CATEGORIES}
ALLOWED = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_BYTES = 10 * 1024 * 1024
DISCLAIMER = ("Click. doesn’t give medical advice. Follow your doctor’s prescription and ask the pharmacist about dosage, interactions "
              "and side effects.")


def _pharmacies():
    from apps.stores.views import public_stores

    return public_stores().filter(store_type="pharmacy")


def _products():
    from apps.catalog.views import public_products

    return public_products().filter(store__store_type="pharmacy")


def product_out(p) -> dict:
    return {"id": str(p.id), "name": p.name, "brand": p.brand, "composition": p.composition, "pack_size": p.pack_size, "manufacturer": p.manufacturer,
            "price": f"{p.price:.2f}", "mrp": f"{p.mrp:.2f}" if getattr(p, "mrp", None) else None, "image": p.image_url,
            "requires_prescription": p.requires_prescription, "category": p.health_category, "category_label": LABEL.get(p.health_category, ""),
            "available": bool(p.is_available and p.in_stock), "max_per_order": p.max_per_order, "description": p.description,
            "pharmacy": {"id": str(p.store_id), "name": p.store.name, "slug": p.store.slug, "open": p.store.is_open}}


def pharmacy_out(s) -> dict:
    return {"id": str(s.id), "name": s.name, "slug": s.slug, "image": s.image_url, "locality": s.locality, "city": s.city, "open": s.is_open,
            "rating": f"{s.rating_average}" if s.rating_count else None, "rating_count": s.rating_count,
            "eta": f"{s.delivery_time_min}–{s.delivery_time_max} min", "verified": bool(getattr(getattr(s, "partner_link", None), "partner", None)
                                                                                      and s.partner_link.partner.partner_code)}


class HomeView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ps = list(_pharmacies().select_related("partner_link__partner").order_by("-is_accepting_orders", "-rating_average")[:12])
        counts = dict(_products().values_list("health_category").annotate(n=Count("id")))
        trending = _products().filter(is_available=True, requires_prescription=False).order_by("-units_sold")[:10]
        again = []
        u = request.user
        if u and u.is_authenticated and hasattr(u, "customer_profile"):
            from apps.orders.models import OrderItem

            ids = list(OrderItem.objects.filter(order__customer=u.customer_profile, order__store__store_type="pharmacy", order__status="delivered")
                       .values_list("product_id", flat=True).distinct()[:10])
            again = [product_out(p) for p in _products().filter(pk__in=ids)]
        return Response({"categories": [{"code": c, "label": l, "icon": i, "count": counts.get(c, 0)} for c, l, i in CATEGORIES if counts.get(c)],
                         "pharmacies": [pharmacy_out(s) for s in ps], "trending": [product_out(p) for p in trending], "order_again": again,
                         "disclaimer": DISCLAIMER})


class ProductsView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "search"

    def get(self, request):
        qp = request.query_params
        qs = _products()
        if qp.get("category") in LABEL:
            qs = qs.filter(health_category=qp["category"])
        if qp.get("pharmacy"):
            qs = qs.filter(store_id=qp["pharmacy"])
        if qp.get("rx") in ("0", "1"):
            qs = qs.filter(requires_prescription=qp["rx"] == "1")
        if q := (qp.get("q") or "").strip()[:60]:
            for w in q.split()[:4]:
                qs = qs.filter(Q(name__icontains=w) | Q(brand__icontains=w) | Q(composition__icontains=w) | Q(manufacturer__icontains=w))
        qs = qs.order_by("-is_available", "name")
        return Response({"results": [product_out(p) for p in qs[:60]], "count": qs.count(), "disclaimer": DISCLAIMER})


class ProductView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        p = _products().filter(pk=pk).first()
        if p is None:
            raise DomainError("This product isn’t available.", code="not_found", status_code=404)
        others = _products().filter(composition__iexact=p.composition).exclude(pk=p.pk)[:6] if p.composition else []
        return Response({**product_out(p), "same_composition": [product_out(o) for o in others], "disclaimer": DISCLAIMER})


def rx_out(r: Prescription) -> dict:
    return {"id": str(r.id), "reference": r.reference, "status": r.status, "status_label": r.get_status_display(), "note": r.note,
            "pharmacist_note": r.pharmacist_note, "alternative_note": r.alternative_note, "file_name": r.file_name, "file_type": r.file_type,
            "pharmacy": {"id": str(r.pharmacy_id), "name": r.pharmacy.name}, "uploaded_at": r.created_at.isoformat(),
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None, "valid_until": r.valid_until.isoformat() if r.valid_until else None,
            "approved_items": [{"id": str(p.id), "name": p.name} for p in r.approved_items.all()],
            "order": {"id": str(r.order_id), "number": r.order.number} if r.order_id else None}


def usable(customer, pharmacy_id) -> Prescription | None:
    today = timezone.localdate()
    return (Prescription.objects.filter(customer=customer, pharmacy_id=pharmacy_id, status__in=[Prescription.Status.VERIFIED, Prescription.Status.PARTIAL])
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today)).order_by("-reviewed_at").first())


class PrescriptionsView(APIView):
    permission_classes = [IsCustomer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "uploads"

    def get(self, request):
        rows = Prescription.objects.filter(customer=request.user.customer_profile).select_related("pharmacy", "order").prefetch_related("approved_items")
        return Response({"results": [rx_out(r) for r in rows]})

    def post(self, request):
        c = request.user.customer_profile
        f = request.FILES.get("file")
        pharmacy = _pharmacies().filter(pk=request.data.get("pharmacy_id") or request.data.get("pharmacyId")).first()
        if pharmacy is None:
            raise DomainError("Choose a pharmacy to review it.", code="validation_error")
        if not f:
            raise DomainError("Attach a photo or PDF of the prescription.", code="validation_error")
        if f.size > MAX_BYTES:
            raise DomainError("The file can be up to 10 MB.", code="file_too_large")
        head = f.read(16)
        f.seek(0)
        kind = ("image/jpeg" if head[:3] == b"\xff\xd8\xff" else "image/png" if head[:8] == b"\x89PNG\r\n\x1a\n" else
                "image/webp" if head[:4] == b"RIFF" and head[8:12] == b"WEBP" else "application/pdf" if head[:5] == b"%PDF-" else "")
        if kind not in ALLOWED:
            raise DomainError("Upload a JPEG, PNG, WebP photo or a PDF.", code="file_type")
        name = os.path.basename(f.name)[:120]
        f.name = f"{uuid.uuid4().hex}{os.path.splitext(name)[1][:6].lower()}"  # unguessable storage name
        r = Prescription.objects.create(customer=c, pharmacy=pharmacy, file=f, file_name=name, file_type=kind, note=str(request.data.get("note") or "")[:500])
        record(c, "prescription.uploaded", {"pharmacy": pharmacy.slug})
        notify(c, NotificationCategory.ORDERS, f"Prescription {r.reference} sent to {pharmacy.name}",
               "Their pharmacist will review it. You’ll be notified of the outcome.", "/pharma/prescriptions")
        return Response(rx_out(r), status=status.HTTP_201_CREATED)


class PrescriptionView(APIView):
    permission_classes = [IsCustomer]

    def _own(self, request, pk):
        return get_object_or_404(Prescription.objects.select_related("pharmacy", "order"), pk=pk, customer=request.user.customer_profile)

    def get(self, request, pk):
        return Response(rx_out(self._own(request, pk)))

    def delete(self, request, pk):
        r = self._own(request, pk)
        if r.status in (Prescription.Status.USED,):
            raise ConflictError("This prescription was used for an order.", code="rx_used")
        r.status = Prescription.Status.CANCELLED
        r.save(update_fields=["status", "updated_at"])
        return Response(rx_out(r))


class PrescriptionFileView(APIView):
    """The document itself: only its owner (or the pharmacy's partner members) can open it."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        r = get_object_or_404(Prescription, pk=pk)
        own = hasattr(request.user, "customer_profile") and r.customer_id == request.user.customer_profile.id
        if not own and not _is_pharmacy_member(request.user, r.pharmacy_id):
            raise DomainError("Not found.", code="not_found", status_code=404)
        return FileResponse(r.file.open("rb"), content_type=r.file_type, as_attachment=True, filename=r.file_name)


def _is_pharmacy_member(user, store_id) -> bool:
    from apps.partners.models import PartnerMembership, PartnerStore

    link = PartnerStore.objects.filter(store_id=store_id).first()
    return bool(link and PartnerMembership.objects.filter(partner_id=link.partner_id, user=user).exists())


class CartPrescriptionView(APIView):
    """POST /customer/cart/prescription {prescriptionId} — attach a verified prescription for the cart's pharmacy."""

    permission_classes = [IsCustomer]

    def post(self, request):
        from apps.carts.models import Cart

        c = request.user.customer_profile
        cart = Cart.objects.filter(customer=c).select_related("store").first()
        if not cart or not cart.store_id or cart.store.store_type != "pharmacy":
            raise DomainError("Add items from a pharmacy first.", code="validation_error")
        r = Prescription.objects.filter(pk=request.data.get("prescriptionId") or request.data.get("prescription_id"), customer=c).first()
        if r is None or r.pharmacy_id != cart.store_id or usable(c, cart.store_id) is None or r.status not in (Prescription.Status.VERIFIED, Prescription.Status.PARTIAL):
            raise DomainError("Choose a prescription this pharmacy has verified.", code="rx_not_verified")
        cart.prescription = r
        cart.save(update_fields=["prescription", "updated_at"])
        return Response({"attached": rx_out(r)})


class ReviewInput(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["verified", "partial", "clarification", "rejected"])
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    approved_product_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    alternative_note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    valid_days = serializers.IntegerField(min_value=1, max_value=365, required=False, default=30)


class PartnerReviewView(APIView):
    """POST /partner/pharma/prescriptions/<id>/review — the pharmacy's pharmacist records the outcome."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        r = get_object_or_404(Prescription.objects.select_for_update(), pk=pk)
        if not _is_pharmacy_member(request.user, r.pharmacy_id):
            raise DomainError("Not found.", code="not_found", status_code=404)
        if r.status not in (Prescription.Status.UNDER_REVIEW, Prescription.Status.CLARIFICATION):
            raise ConflictError("This prescription has already been reviewed.", code="rx_reviewed")
        s = ReviewInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        r.status, r.pharmacist_note, r.alternative_note = d["outcome"], d["note"], d["alternative_note"]
        r.reviewed_at, r.reviewed_by = timezone.now(), request.user
        if d["outcome"] in ("verified", "partial"):
            r.valid_until = timezone.localdate() + timedelta(days=d["valid_days"])
        r.save()
        if d["approved_product_ids"]:
            r.approved_items.set(_products().filter(store_id=r.pharmacy_id, pk__in=d["approved_product_ids"]))
        msg = {"verified": "Verified — you can order the prescribed items now.", "partial": "Partly accepted — see which items you can order.",
               "clarification": "The pharmacist needs more information.", "rejected": "The pharmacist couldn’t accept it."}[d["outcome"]]
        notify(r.customer, NotificationCategory.ORDERS, f"Prescription {r.reference}: {r.get_status_display()}",
               f"{msg}{' ' + d['note'] if d['note'] else ''}", "/pharma/prescriptions")
        return Response(rx_out(r))


class RefillsView(APIView):
    """GET / POST /customer/pharma/refills {productId, everyDays} · DELETE /customer/pharma/refills/<id>"""

    permission_classes = [IsCustomer]

    def get(self, request):
        rows = RefillReminder.objects.filter(customer=request.user.customer_profile, is_active=True).select_related("product__store")
        return Response({"results": [{"id": str(x.id), "every_days": x.every_days, "next_on": x.next_on.isoformat(), "product": product_out(x.product)} for x in rows]})

    def post(self, request):
        c = request.user.customer_profile
        p = _products().filter(pk=request.data.get("productId") or request.data.get("product_id")).first()
        days = int(request.data.get("everyDays") or request.data.get("every_days") or 0)
        if p is None or not 7 <= days <= 180:
            raise DomainError("Choose a product and a reminder every 7 to 180 days.", code="validation_error")
        x, _ = RefillReminder.objects.update_or_create(customer=c, product=p, defaults={"every_days": days, "next_on": timezone.localdate() + timedelta(days=days), "is_active": True})
        return Response({"id": str(x.id), "next_on": x.next_on.isoformat()}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk=None):
        RefillReminder.objects.filter(customer=request.user.customer_profile, pk=pk).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


def run_due() -> int:
    """Scheduled daily: send due refill reminders and expire old verified prescriptions."""
    today = timezone.localdate()
    n = 0
    for x in RefillReminder.objects.filter(is_active=True, next_on__lte=today).select_related("product"):
        notify(x.customer, NotificationCategory.ORDERS, f"Time to reorder {x.product.name}?", "Your refill reminder. Reorder from the pharmacy in Click. Pharma.",
               f"/pharma/p/{x.product_id}")
        x.next_on = today + timedelta(days=x.every_days)
        x.save(update_fields=["next_on", "updated_at"])
        n += 1
    Prescription.objects.filter(status__in=["verified", "partial"], valid_until__lt=today).update(status=Prescription.Status.EXPIRED)
    return n
