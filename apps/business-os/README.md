# Click Business OS (Phase 6, not started)

Internal Click company operating system, for Click staff only.

**Belongs here:** customer/partner/business administration, partner approval, order and support operations
(working customer support tickets), finance, staff, roles and permissions, analytics, audit tools, platform
administration, AI business intelligence.

**Does not belong here:** customer screens (`apps/customer`) or partner self-service (`apps/partner`).

Uses the shared `@click/api` package and the backend's `/api/v1/os/*` surface (to be added), with staff
accounts and explicit Django permissions enforced on the server. Until then, Django admin (`/admin/`) is the
interim internal tool.
