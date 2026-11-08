"""
Partner onboarding and status rules. Views stay thin; every write goes through here.

Ownership: a partner is always resolved from the authenticated user's
membership. No endpoint accepts a partner ID from the client, so one partner
can never read or change another's records.
"""

from __future__ import annotations

import logging

from django.db import connection, transaction
from django.utils import timezone

from apps.core.api.exceptions import ConflictError, DomainError
from apps.users.models import User

from .catalog import resolve_configuration
from .models import (
    PARTNER_CODE_PREFIX, PARTNER_CODE_SEQUENCE, Partner, PartnerAddress, PartnerCategory, PartnerMembership,
    PartnerProfile, PartnerStatusEvent, PartnerVerification,
)
from .schema import validate_details

audit = logging.getLogger("click.audit")
S = Partner.Status

TRANSITIONS: dict[str, set[str]] = {
    S.DRAFT: {S.PROFILE_COMPLETED},
    S.PROFILE_COMPLETED: {S.VERIFICATION_PENDING},
    S.VERIFICATION_PENDING: {S.VERIFIED, S.REJECTED},
    S.REJECTED: {S.VERIFICATION_PENDING},
    S.VERIFIED: {S.ACTIVE, S.SUSPENDED},
    S.ACTIVE: {S.SUSPENDED, S.INACTIVE},
    S.SUSPENDED: {S.ACTIVE, S.INACTIVE},
    S.INACTIVE: {S.ACTIVE},
}


# --- lookup ---------------------------------------------------------------

def owned_partner(user, *, for_update: bool = False) -> Partner | None:
    qs = Partner.objects.select_related("partner_type", "category", "profile").filter(
        memberships__user=user, memberships__role=PartnerMembership.Role.OWNER, memberships__is_active=True,
    )
    if for_update:
        qs = qs.select_for_update(of=("self",))
    return qs.first()


def require_owned_partner(user, *, for_update: bool = False) -> Partner:
    partner = owned_partner(user, for_update=for_update)
    if partner is None:
        raise DomainError("Choose what you provide through Click first.", code="partner_not_found", status_code=404)
    return partner


def configuration_for(category: PartnerCategory) -> dict:
    return resolve_configuration(category.partner_type.configuration, category.configuration)


def primary_address(partner: Partner) -> PartnerAddress | None:
    return partner.addresses.filter(is_primary=True).first()


def onboarding_step(partner: Partner | None) -> str:
    if partner is None:
        return "category"
    if partner.is_onboarded:
        return "complete"
    if not partner.business_name:
        return "profile"
    if not partner.addresses.filter(is_primary=True).exists():
        return "location"
    return "review"


def _ensure_draft(partner: Partner) -> None:
    if partner.is_onboarded:
        raise ConflictError(
            "Your Partner profile is already submitted. Contact Click support to change it.", code="partner_locked"
        )


# --- status ---------------------------------------------------------------

def transition(partner: Partner, to_status: str, *, actor=None, note: str = "") -> None:
    if to_status not in TRANSITIONS.get(partner.status, set()):
        raise ConflictError(f"A partner cannot move from {partner.status} to {to_status}.", code="invalid_status_transition")
    PartnerStatusEvent.objects.create(partner=partner, from_status=partner.status, to_status=to_status, actor=actor, note=note)
    partner.status = to_status
    partner.save(update_fields=["status", "updated_at"])
    audit.info("partner.status", extra={"partner": partner.partner_code or str(partner.pk), "to": to_status})


# --- onboarding -----------------------------------------------------------

def choose_category(user, type_slug: str, category_slug: str) -> Partner:
    category = (
        PartnerCategory.objects.select_related("partner_type")
        .filter(slug=category_slug, partner_type__slug=type_slug, is_active=True, partner_type__is_active=True)
        .first()
    )
    if category is None:
        raise DomainError("Choose a partner category from the list.", code="invalid_category")

    with transaction.atomic():
        # Serialise onboarding per user so retries/double taps can't create two partners.
        User.objects.select_for_update().filter(pk=user.pk).first()
        partner = owned_partner(user, for_update=True)
        if partner:
            _ensure_draft(partner)
            if partner.category_id != category.id:
                partner.partner_type = category.partner_type
                partner.category = category
                partner.save(update_fields=["partner_type", "category", "updated_at"])
                # Category-specific answers don't carry over between categories.
                PartnerProfile.objects.filter(partner=partner).update(details={}, updated_at=timezone.now())
            return owned_partner(user)

        partner = Partner.objects.create(partner_type=category.partner_type, category=category)
        PartnerMembership.objects.create(partner=partner, user=user, role=PartnerMembership.Role.OWNER)
        PartnerProfile.objects.create(partner=partner)
        PartnerStatusEvent.objects.create(partner=partner, to_status=S.DRAFT, actor=user, note="Partner created")
    audit.info("partner.created", extra={"user_id": str(user.id), "category": category.slug})
    return owned_partner(user)


def save_profile(user, data: dict) -> Partner:
    with transaction.atomic():
        partner = require_owned_partner(user, for_update=True)
        _ensure_draft(partner)
        config = configuration_for(partner.category)
        details, errors = validate_details(config["fields"], data.get("details", {}))
        if errors:
            raise DomainError("Please check the highlighted fields.", code="validation_error", details={"details": errors})

        profile = partner.profile
        partner.business_name = data["business_name"]
        profile.contact_name = data["business_name"] if config["identity"]["individual"] else data.get("contact_name", "")
        if not profile.contact_name:
            raise DomainError(
                "Please check the highlighted fields.", code="validation_error",
                details={"contact_name": ["Enter the contact person's name."]},
            )
        profile.email = data.get("email", "")
        profile.description = data.get("description", "")
        profile.details = details
        partner.save(update_fields=["business_name", "updated_at"])
        profile.save()
    return owned_partner(user)


def save_location(user, data: dict) -> Partner:
    with transaction.atomic():
        partner = require_owned_partner(user, for_update=True)
        _ensure_draft(partner)
        address = primary_address(partner) or PartnerAddress(partner=partner, is_primary=True)
        for field, value in data.items():
            setattr(address, field, value)
        address.full_clean(exclude=["partner"])
        address.save()
    return owned_partner(user)


def submit(user) -> Partner:
    with transaction.atomic():
        partner = require_owned_partner(user, for_update=True)
        if partner.is_onboarded:
            return owned_partner(user)  # idempotent: a retry never mints a second Partner ID

        config = configuration_for(partner.category)
        missing: dict[str, list[str]] = {}
        if not partner.business_name:
            missing["profile"] = ["Complete your partner profile."]
        else:
            _, detail_errors = validate_details(config["fields"], partner.profile.details)
            if detail_errors:
                missing["profile"] = ["Some profile details are missing for your category."]
        if primary_address(partner) is None:
            missing["location"] = ["Add your operating location."]
        if missing:
            raise DomainError("Finish the remaining steps first.", code="onboarding_incomplete", details=missing)

        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s)", [PARTNER_CODE_SEQUENCE])
            number = cursor.fetchone()[0]
        partner.partner_code = f"{PARTNER_CODE_PREFIX}{number:06d}"
        partner.profile_completed_at = timezone.now()
        partner.save(update_fields=["partner_code", "profile_completed_at", "updated_at"])
        transition(partner, S.PROFILE_COMPLETED, actor=user, note="Profile completed")
        transition(partner, S.VERIFICATION_PENDING, actor=user, note="Submitted for verification")
        PartnerVerification.objects.create(partner=partner, submitted_at=timezone.now())
    audit.info("partner.onboarded", extra={"partner": partner.partner_code})
    return owned_partner(user)


# --- staff review (Django admin today, Business OS later) -------------------

def review_verification(partner: Partner, *, approve: bool, reviewer, note: str = "") -> None:
    with transaction.atomic():
        partner = Partner.objects.select_for_update().get(pk=partner.pk)
        verification = partner.verifications.filter(status=PartnerVerification.Status.PENDING).first()
        if verification is None or partner.status != S.VERIFICATION_PENDING:
            raise ConflictError("This partner has no pending verification.", code="no_pending_verification")
        verification.status = PartnerVerification.Status.APPROVED if approve else PartnerVerification.Status.REJECTED
        verification.reviewed_at = timezone.now()
        verification.reviewed_by = reviewer
        verification.reviewer_note = note
        verification.save()
        transition(partner, S.VERIFIED if approve else S.REJECTED, actor=reviewer, note=note or "Verification reviewed")
