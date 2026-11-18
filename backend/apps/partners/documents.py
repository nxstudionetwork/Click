"""
Partner verification documents: what the partner's category requires (catalog.py `documents`), what they submitted,
and what Click verified. A required document that is verified but past its expiry date blocks operating.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import DomainError

from .models import Partner, PartnerDocument

EXPIRING_SOON_DAYS = 30


def requirements(partner: Partner) -> list[dict]:
    from .services import configuration_for

    return configuration_for(partner.category).get("documents", [])


def _state(req: dict, doc: PartnerDocument | None, today: date) -> tuple[str, str]:
    if doc is None:
        return "missing", "Not submitted"
    if doc.status == PartnerDocument.Status.REJECTED:
        return "rejected", "Rejected"
    if req.get("expires") and doc.expires_on and doc.expires_on < today:
        return "expired", f"Expired on {doc.expires_on:%d %b %Y}"
    if doc.status == PartnerDocument.Status.PENDING:
        return "pending", "Waiting for Click review"
    if req.get("expires") and doc.expires_on and doc.expires_on <= today + timedelta(days=EXPIRING_SOON_DAYS):
        return "expiring", f"Expires on {doc.expires_on:%d %b %Y}"
    return "verified", "Verified"


def documents_state(partner: Partner) -> list[dict]:
    today = timezone.localdate()
    docs = {d.key: d for d in partner.documents.all()}
    out = []
    for req in requirements(partner):
        doc = docs.get(req["key"])
        state, label = _state(req, doc, today)
        out.append({
            "key": req["key"], "label": req["label"], "required": req.get("required", True), "expires": req.get("expires", False),
            "help": req.get("help", ""), "state": state, "state_label": label,
            "number": _masked(doc.number) if doc else "", "expires_on": doc.expires_on.isoformat() if doc and doc.expires_on else None,
            "review_note": doc.review_note if doc else "", "can_submit": state in ("missing", "rejected", "expired", "expiring"),
        })
    return out


def _masked(number: str) -> str:
    """Documents are shown back masked (last 4 characters) so a shared screen never exposes the full number."""
    n = number.replace(" ", "")
    return f"•••• {n[-4:]}" if len(n) > 4 else n


def blocking_reason(partner: Partner) -> str:
    """Why this partner can't operate because of documents ('' when nothing blocks). Only expired required documents
    block: partners verified before documents were collected in the app aren't blocked for missing records."""
    expired = [d for d in documents_state(partner) if d["required"] and d["state"] == "expired"]
    if not expired:
        return ""
    names = ", ".join(d["label"].lower() for d in expired)
    return f"Your {names} {'has' if len(expired) == 1 else 'have'} expired. Submit the renewed document to start working again."


@transaction.atomic
def submit(partner: Partner, data: dict) -> PartnerDocument:
    req = next((r for r in requirements(partner) if r["key"] == data.get("key")), None)
    if req is None:
        raise DomainError("This document isn’t needed for your partner type.", code="validation_error",
                          details={"key": ["Choose a listed document."]})
    number = " ".join(str(data.get("number") or "").split()).upper()
    if not 4 <= len(number) <= 40:
        raise DomainError("Enter the document number as printed.", code="validation_error", details={"number": ["Enter the document number."]})
    expires_on = None
    if req.get("expires"):
        try:
            expires_on = date.fromisoformat(str(data.get("expires_on") or ""))
        except ValueError:
            raise DomainError("Enter the expiry date.", code="validation_error", details={"expires_on": ["Enter the expiry date."]})
        if expires_on <= timezone.localdate():
            raise DomainError("This document has already expired.", code="validation_error",
                              details={"expires_on": ["Submit a document that is still valid."]})
    doc, _ = PartnerDocument.objects.select_for_update().get_or_create(
        partner=partner, key=req["key"], defaults={"submitted_at": timezone.now()})
    if doc.status == PartnerDocument.Status.PENDING and doc.number == number and doc.expires_on == expires_on and doc.pk:
        return doc  # same submission again (double tap / retry): nothing changes
    doc.number, doc.expires_on, doc.status, doc.review_note = number, expires_on, PartnerDocument.Status.PENDING, ""
    doc.submitted_at, doc.reviewed_at = timezone.now(), None
    doc.save()
    return doc


def review(doc: PartnerDocument, approve: bool, note: str = "") -> None:
    """Click staff decision (Business OS / admin)."""
    from .notifications import notify_partner

    doc.status = PartnerDocument.Status.VERIFIED if approve else PartnerDocument.Status.REJECTED
    doc.review_note, doc.reviewed_at = note[:200], timezone.now()
    doc.save(update_fields=["status", "review_note", "reviewed_at", "updated_at"])
    label = next((r["label"] for r in requirements(doc.partner) if r["key"] == doc.key), doc.key)
    notify_partner(doc.partner, "account", f"{label} {'verified' if approve else 'not accepted'}",
                   "" if approve else (note or "Submit a clearer or valid copy."), "/documents")
