from rest_framework import serializers

from . import services
from .models import ParcelOrder, ParcelStatus, SavedRecipient


class PlaceInput(serializers.Serializer):
    label = serializers.CharField(max_length=120)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    alt_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    instructions = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class PackageInput(serializers.Serializer):
    category = serializers.SlugField(max_length=30, required=False, allow_blank=True, default="")
    size = serializers.ChoiceField(choices=ParcelOrder.Size.choices, required=False, allow_blank=True, default="")
    weight_kg = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0, max_value=5000, required=False, allow_null=True)
    length_cm = serializers.IntegerField(min_value=1, max_value=600, required=False, allow_null=True)
    width_cm = serializers.IntegerField(min_value=1, max_value=600, required=False, allow_null=True)
    height_cm = serializers.IntegerField(min_value=1, max_value=600, required=False, allow_null=True)
    declared_value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True)
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class QuoteInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=ParcelOrder.Mode.choices, default="send")
    pickup = PlaceInput(required=False, allow_null=True)
    drop = PlaceInput(required=False, allow_null=True)
    stops = PlaceInput(many=True, required=False, default=list, max_length=3)
    package = PackageInput(required=False, default=dict)
    service = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    store_id = serializers.UUIDField(required=False, allow_null=True)


class BookInput(QuoteInput):
    pickup = PlaceInput()
    drop = PlaceInput()
    service = serializers.CharField(max_length=12)
    vehicle = serializers.SlugField(max_length=20)
    payment_method = serializers.ChoiceField(choices=["wallet", "cash"])
    expected_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    idempotency_key = serializers.UUIDField()
    contents_confirmed = serializers.BooleanField()
    save_recipient = serializers.BooleanField(required=False, default=False)
    store_reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    repeat_of = serializers.UUIDField(required=False, allow_null=True)


class RecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedRecipient
        fields = ["id", "name", "phone", "alt_phone", "label", "address", "lat", "lng", "instructions", "times_used", "last_used_at"]
        read_only_fields = ["id", "times_used", "last_used_at"]

    def validate_phone(self, v):
        if not services.PHONE.match(v.strip()):
            raise serializers.ValidationError("Enter a valid phone number.")
        return v.strip()


def _place(label, address, lat, lng) -> dict:
    return {"label": label, "address": address, "lat": float(lat), "lng": float(lng)}


def parcel_summary(p: ParcelOrder) -> dict:
    return {
        "id": str(p.id), "number": p.number, "mode": p.mode, "mode_label": p.get_mode_display(), "status": p.status,
        "status_label": p.get_status_display(), "service": {"code": p.service.code, "name": p.service.name},
        "vehicle": {"code": p.vehicle.code, "name": p.vehicle.name, "icon": p.vehicle.icon},
        "pickup": _place(p.pickup_label, p.pickup_address, p.pickup_lat, p.pickup_lng),
        "drop": _place(p.drop_label, p.drop_address, p.drop_lat, p.drop_lng),
        "total": f"{p.total:.2f}", "currency": p.currency, "created_at": p.created_at.isoformat(),
        "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
        "deliver_by": p.deliver_by.isoformat() if p.deliver_by else None,
        "delivered_at": p.delivered_at.isoformat() if p.delivered_at else None,
        "is_active": p.status not in (ParcelStatus.DELIVERED, ParcelStatus.CANCELLED, ParcelStatus.FAILED, ParcelStatus.NO_PARTNER),
    }


def parcel_detail(p: ParcelOrder) -> dict:
    """The owner's view: includes PINs (until used), recipient contact, payment, proof and cancellation terms."""
    payment = p.payments.order_by("created_at").first()
    partner = None
    if p.partner_id:
        details = getattr(getattr(p.partner, "profile", None), "details", {}) or {}
        name = (getattr(getattr(p.partner, "profile", None), "contact_name", "") or p.partner.business_name or "Delivery partner").split()[0]
        partner = {"name": name, "vehicle": p.vehicle.name, "vehicle_number": details.get("vehicle_number", ""),
                   "position": services.partner_position(p)}
    before_pickup = p.status in (ParcelStatus.SCHEDULED, ParcelStatus.SEARCHING, ParcelStatus.ASSIGNED, ParcelStatus.AT_PICKUP)
    done = p.status in (ParcelStatus.DELIVERED, ParcelStatus.CANCELLED, ParcelStatus.FAILED, ParcelStatus.NO_PARTNER)
    return {
        **parcel_summary(p),
        "pickup": {**_place(p.pickup_label, p.pickup_address, p.pickup_lat, p.pickup_lng), "name": p.pickup_name,
                   "phone_masked": services.mask_phone(p.pickup_phone), "instructions": p.pickup_instructions,
                   "store": {"id": str(p.store_id), "name": p.store.name} if p.store_id else None, "store_reference": p.store_reference},
        "drop": {**_place(p.drop_label, p.drop_address, p.drop_lat, p.drop_lng), "name": p.drop_name,
                 "phone_masked": services.mask_phone(p.drop_phone), "instructions": p.drop_instructions},
        "stops": [{"position": s.position, **_place(s.label, s.address, s.lat, s.lng), "name": s.contact_name,
                   "completed_at": s.completed_at.isoformat() if s.completed_at else None} for s in p.stops.all()],
        "package": {"category": p.category.label, "category_code": p.category.code, "size": p.size, "size_label": p.get_size_display(),
                    "weight_kg": f"{p.weight_kg:.1f}", "dims": [p.length_cm, p.width_cm, p.height_cm] if p.length_cm else None,
                    "declared_value": f"{p.declared_value:.2f}" if p.declared_value is not None else None, "notes": p.package_notes},
        "fare": {"base": f"{p.fare_base:.2f}", "distance": f"{p.fare_distance:.2f}", "service": f"{p.fare_service:.2f}",
                 "stops": f"{p.fare_stops:.2f}", "tax": f"{p.tax:.2f}", "discount": f"{p.discount:.2f}", "total": f"{p.total:.2f}",
                 "cancellation_fee": f"{p.cancellation_fee:.2f}"},
        "distance_km": f"{p.distance_km:.1f}", "duration_minutes": p.duration_minutes, "estimate_basis": p.estimate_basis,
        "payment": {"method": p.payment_method, "status": payment.status if payment else None,
                    "refunded": any(x.status == "refunded" for x in p.payments.all())},
        "pins": {"pickup": p.pickup_pin if before_pickup else None, "delivery": p.delivery_pin if not done else None},
        "partner": partner,
        "timeline": services.timeline(p),
        "events": [{"to": e.to_status, "note": e.note, "at": e.created_at.isoformat()} for e in p.events.all()],
        "proofs": [{"kind": x.kind, "kind_label": x.get_kind_display(), "method": x.method, "at": x.created_at.isoformat(),
                    "located": x.lat is not None} for x in p.proofs.all()],
        "cancellation": services.cancellation_terms(p),
        "failure_reason": p.failure_reason, "cancel_reason": p.cancel_reason,
        "support_required": p.status == ParcelStatus.FAILED,
        "tickets": [{"id": str(t.id), "reference": t.reference, "status": t.status} for t in p.support_tickets.all()],
    }


def shared_view(p: ParcelOrder) -> dict:
    """What anyone with a share link sees: no phone numbers, PINs, prices or exact addresses."""
    return {"number": p.number, "status": p.status, "status_label": p.get_status_display(), "service": p.service.name,
            "from": p.pickup_label, "to": p.drop_label, "deliver_by": p.deliver_by.isoformat() if p.deliver_by else None,
            "timeline": services.timeline(p), "delivered_at": p.delivered_at.isoformat() if p.delivered_at else None}
