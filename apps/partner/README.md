# Click Partner App (Phase 5, not started)

Partner-facing product for restaurants, retailers, merchants, drivers, delivery partners and service providers.

**Belongs here:** menu/product and inventory management, incoming orders, availability toggles, deliveries and rides
work, earnings, partner offers, business profile, partner analytics.

**Does not belong here:** customer screens (`apps/customer`) or internal Click operations (`apps/business-os`).

Uses the shared `@click/api` package and the backend's `/api/v1/partner/*` surface (to be added), with
membership-scoped permissions enforced on the server.
