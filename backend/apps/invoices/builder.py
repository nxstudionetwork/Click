"""Builds an invoice from a payment and the order / booking it paid for. Never from client input."""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.records import describe, owned, target_field, with_relations

from .models import Invoice

BILLABLE = (Payment.Status.CAPTURED, Payment.Status.REFUNDED)
METHOD = {"wallet": "Click. Wallet", "cash_on_delivery": "Cash on delivery", "cash": "Cash", "pay_at_venue": "Paid at venue",
          "upi": "UPI", "card": "Card", "netbanking": "Net banking"}


def _m(v) -> str:
    return f"{Decimal(v or 0):.2f}"


def _partner_seller(partner, name="", fallback_city=""):
    if partner is None:
        return {"name": name or "Click. partner", "address": fallback_city}
    a = partner.addresses.filter(is_primary=True).first()
    addr = ", ".join(x for x in [a.line1, a.line2, a.city, a.state, a.postal_code] if x) if a else fallback_city
    return {"name": name or partner.business_name or "Click. partner", "address": addr, "partner_id": partner.partner_code or ""}


def _seller(p: Payment, t: str) -> dict:
    if t == "order":
        s = p.order.store
        from apps.partners.models import PartnerStore

        link = PartnerStore.objects.select_related("partner").filter(store=s).first()
        return _partner_seller(link.partner if link else None, s.name, ", ".join(x for x in [s.locality, s.city] if x))
    if t == "ride":
        return _partner_seller(p.ride.driver, getattr(p.ride.driver, "business_name", "") if p.ride.driver_id else "Click. Ride")
    if t == "parcel":
        partner = getattr(p.parcel, "partner", None)
        return _partner_seller(partner, getattr(partner, "business_name", "") if partner else "Click. Parcel")
    if t == "service_booking":
        return _partner_seller(p.service_booking.provider.partner if p.service_booking.provider_id else None)
    if t == "event_booking":
        return _partner_seller(p.event_booking.provider.partner)
    if t == "hotel_booking":
        prop = p.hotel_booking.property
        seller = _partner_seller(prop.partner)
        seller["address"] = prop.address or seller["address"]
        return seller
    if t == "travel_booking":
        op = p.travel_booking.journey.service.operator
        return _partner_seller(op.partner, op.name) if op.partner_id else {"name": op.name, "address": ""}
    if t == "experience_booking":
        a = p.experience_booking.attraction
        return {"name": a.name, "address": ", ".join(x for x in [getattr(a, "area", ""), a.city] if x)}
    if t == "gift_card":
        return {"name": "Click.", "address": ""}
    if t == "booking":
        v = p.booking.show.venue
        return {"name": v.name, "address": ", ".join(x for x in [v.address, v.city] if x)}
    return {"name": "Click.", "address": ""}


def _buyer(p: Payment, t: str) -> dict:
    c = p_customer(p)
    u = c.user
    phone = u.phone or ""
    masked = f"{phone[:-6]}••••{phone[-2:]}" if len(phone) > 8 else ""
    out = {"name": u.full_name or "", "email": u.email or "", "phone": masked, "customer_id": c.customer_code}
    if t == "order":
        a = p.order.delivery_address or {}
        out["address"] = ", ".join(str(a.get(k)) for k in ("line1", "line2", "city", "postal_code") if a.get(k))
    return out


def p_customer(p: Payment):
    obj = getattr(p, target_field(p))
    return getattr(obj, "customer", None) or obj.buyer


def _lines(p: Payment, t: str) -> tuple[list[dict], dict]:
    obj = getattr(p, t)
    if t == "order":
        o = obj
        lines = [{"description": i.product_name + (f" ({i.options_summary})" if i.options_summary else ""), "quantity": i.quantity,
                  "unit_price": _m(i.unit_price), "discount": "0.00", "tax": None, "total": _m(i.line_total)} for i in o.items.all()]
        totals = {"subtotal": _m(o.subtotal), "discount": _m(o.discount), "delivery_fee": _m(o.delivery_fee), "fees": "0.00", "tax": _m(o.tax),
                  "total": _m(o.total), "offer": o.offer_title or ""}
        return lines, totals
    d = describe(p)
    if t == "gift_card":
        g = p.gift_card
        line = {"description": f"{g.design.title} for {g.recipient_name}", "quantity": 1, "unit_price": _m(g.amount), "discount": "0.00", "tax": None, "total": _m(g.amount)}
        return [line], {"subtotal": _m(g.amount), "discount": "0.00", "delivery_fee": "0.00", "fees": "0.00", "tax": "0.00", "total": _m(g.amount), "offer": ""}
    when = ""
    for f in ("check_in", "visit_date", "departs_at", "event_date", "scheduled_start", "scheduled_for"):
        v = getattr(obj, f, None)
        if v:
            when = v.strftime("%d %b %Y") if hasattr(v, "strftime") else str(v)
            break
    qty = getattr(obj, "nights", None) or getattr(obj, "tickets", None) or (getattr(obj, "adults", 0) + getattr(obj, "children", 0)) or 1
    if not isinstance(qty, int):
        qty = 1
    sub = next((getattr(obj, f) for f in ("subtotal", "base_fare", "room_total") if getattr(obj, f, None) is not None), p.amount)
    fees = sum((getattr(obj, f) or 0 for f in ("convenience_fee", "fees", "service_fee", "platform_fee") if hasattr(obj, f)), Decimal("0"))
    tax = next((getattr(obj, f) for f in ("tax", "taxes", "gst") if getattr(obj, f, None) is not None), Decimal("0"))
    disc = getattr(obj, "discount", None) or Decimal("0")
    lines = [{"description": f"{d['label']} {d['reference']}" + (f" · {when}" if when else ""), "quantity": qty, "unit_price": None,
              "discount": _m(disc), "tax": _m(tax), "total": _m(sub)}]
    totals = {"subtotal": _m(sub), "discount": _m(disc), "delivery_fee": _m(getattr(obj, "delivery_fee", 0) or 0), "fees": _m(fees), "tax": _m(tax),
              "total": _m(getattr(obj, "total", None) or p.amount), "offer": getattr(obj, "offer_title", "") or ""}
    return lines, totals


def _refunds(p: Payment, inv_number: str) -> list[dict]:
    rows = [{"number": f"CN-{inv_number[4:]}-{i + 1}", "amount": _m(t.amount), "at": t.created_at.isoformat(), "to": "Click. Wallet", "reason": t.description}
            for i, t in enumerate(p.wallet_transactions.filter(kind="refund").order_by("created_at"))]
    if not rows and p.status == Payment.Status.REFUNDED:
        rows = [{"number": f"CN-{inv_number[4:]}-1", "amount": _m(p.amount), "at": p.updated_at.isoformat(), "to": METHOD.get(p.method, p.method),
                 "reason": "Refund to the original payment method"}]
    return rows


def ensure(p: Payment) -> Invoice | None:
    """Create the invoice the first time it's needed; afterwards only refunds are added. Idempotent."""
    t = target_field(p)
    if t == "wallet_topup" or p.status not in BILLABLE:
        return getattr(p, "invoice", None) if hasattr(p, "invoice") else None
    inv = Invoice.objects.filter(payment=p).first()
    if inv is None:
        lines, totals = _lines(p, t)
        d = describe(p)
        seller = _seller(p, t)
        try:
            with transaction.atomic():
                inv = Invoice.objects.create(customer=p_customer(p), payment=p, service=d["service"], reference=d["reference"], seller=seller,
                                             buyer=_buyer(p, t), lines=lines, totals={**totals, "paid": _m(p.amount)},
                                             title="Tax invoice" if seller.get("gstin") else "Invoice", issued_at=p.updated_at or timezone.now())
        except IntegrityError:
            inv = Invoice.objects.get(payment=p)
    refunds = _refunds(p, inv.number)
    if refunds != inv.refunds:
        new = len(refunds) > len(inv.refunds)
        inv.refunds = refunds
        inv.status = Invoice.Status.REFUND
        inv.save(update_fields=["refunds", "status", "updated_at"])
        if new:
            from apps.notifications.models import NotificationCategory
            from apps.notifications.services import notify

            notify(inv.customer, NotificationCategory.PAYMENTS, f"Refund document for {inv.number}",
                   f"₹{float(refunds[-1]['amount']):,.2f} refunded to {refunds[-1]['to']}.", f"/account/invoices/{inv.id}")
    return inv


def cards(customer, *, service: str = "", status: str = "", q: str = "", date_from=None, date_to=None) -> list[dict]:
    """Every purchase / booking the customer paid or will pay for, with its invoice state."""
    qs = with_relations(owned(customer)).exclude(wallet_topup__isnull=False).select_related("invoice").order_by("-created_at")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    out = []
    for p in qs[:300]:
        inv = ensure(p) if p.status in BILLABLE else None
        d = describe(p)
        t = target_field(p)
        if inv:
            st, label = inv.status, inv.get_status_display()
        elif p.status == Payment.Status.CANCELLED or p.status == Payment.Status.FAILED:
            st, label = "cancelled", "No charge"
        else:
            st, label = "pending", "Pending — issued once paid"
        seller = inv.seller["name"] if inv else _seller(p, t)["name"]
        row = {"id": str(inv.id) if inv else None, "payment_id": str(p.id), "number": inv.number if inv else None, "service": d["service"],
               "label": d["label"].split(" · ")[0], "vendor": seller, "reference": d["reference"], "date": p.created_at.isoformat(),
               "amount": _m(p.amount), "payment_status": p.status, "invoice_status": st, "invoice_status_label": label, "link": d["link"],
               "refunded": sum(Decimal(r["amount"]) for r in inv.refunds) if inv and inv.refunds else None}
        out.append(row)
    if service:
        out = [r for r in out if r["service"] == service]
    if status:
        out = [r for r in out if r["invoice_status"] == status]
    if q:
        ql = q.lower().strip()
        out = [r for r in out if ql in f"{r['number'] or ''} {r['reference']} {r['vendor']} {r['label']} {r['service']}".lower()]
    return out


def detail(inv: Invoice) -> dict:
    p = inv.payment
    d = describe(p)
    return {"id": str(inv.id), "number": inv.number, "title": inv.title, "status": inv.status, "status_label": inv.get_status_display(),
            "issued_at": inv.issued_at.isoformat(), "service": inv.service, "label": d["label"], "reference": inv.reference, "link": d["link"],
            "seller": inv.seller, "buyer": inv.buyer, "lines": inv.lines, "totals": inv.totals, "refunds": inv.refunds,
            "payment": {"id": str(p.id), "reference": f"PAY-{str(p.id)[:8].upper()}", "method": METHOD.get(p.method, p.method), "status": p.get_status_display(),
                        "provider_reference": p.provider_reference or None},
            "gst_note": "" if inv.seller.get("gstin") else "The seller's GST registration isn’t on file with Click., so this is an invoice, not a GST tax invoice."}


def owned_invoice(customer, pk):
    return Invoice.objects.filter(customer=customer).filter(Q(pk=pk)).select_related("payment").first()
