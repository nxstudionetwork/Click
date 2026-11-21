"""
Click's commercial relationship types.

Click is primarily a technology platform / mediator connecting customers with participating partners, merchants,
businesses and service providers. Click is NOT automatically the supplier of what is listed on the platform.

Every future record that moves money or creates a liability (contracts, invoices, commissions, settlements, taxes,
refunds, payouts, reporting) must carry one of these values instead of assuming "Click sold it". Partner,
Finance and Payments modules store it per relationship and per transaction; nothing may default to
CLICK_OWNED_INVENTORY silently.
"""

from django.db import models


class CommercialModel(models.TextChoices):
    MARKETPLACE = "marketplace", "Marketplace / mediator"
    COMMISSION_PARTNER = "commission_partner", "Commission-based partner"
    AGENCY = "agency", "Agency relationship"
    CLICK_OPERATED = "click_operated", "Click-operated service"
    CLICK_OWNED_INVENTORY = "click_owned_inventory", "Click-owned inventory"
    THIRD_PARTY_FULFILLMENT = "third_party_fulfillment", "Third-party fulfillment"
    OTHER_APPROVED = "other_approved", "Other approved commercial model"


# Who is the seller of record / service provider for each model. Click is principal only in these two.
CLICK_IS_PRINCIPAL = frozenset({CommercialModel.CLICK_OPERATED, CommercialModel.CLICK_OWNED_INVENTORY})


def click_is_principal(model: str) -> bool:
    return model in CLICK_IS_PRINCIPAL
