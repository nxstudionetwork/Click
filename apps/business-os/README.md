# Click Business OS

Internal Click company operating system: React + TypeScript (Vite), on the shared `@click/api` (`osApi`) and
`@click/ui` packages and the backend's `/api/v1/os/*` surface.

**Foundation (built):** splash, multi-step sign-in (employee / administrator / partner / other; password + TOTP
two-step verification, invitations), session handling (separate OS session, idle + absolute expiry, immediate
revocation), first-login onboarding, permission-aware shell (sidebar, header, Ctrl/⌘+K search, notifications, Business
AI), Home command center (role-composed widgets), My Work, Approvals (inbox, requests, delegation), Tasks,
Notifications, Calendar, Profile, Settings (preferences, security & sessions, organization structure, users, roles &
scoped permissions, workflows, audit trail, system, integrations) and a registered landing page for every future
business module.

**Next:** each business module (Finance, People & HR, Procurement, Inventory, Partners, …) is built on this
foundation. See [docs/business-os.md](../../docs/business-os.md).

```bash
npm run dev -w @click/business-os   # http://localhost:5177, proxies /api to :4000 (CLICK_API_PROXY overrides)
npm run test -w @click/business-os
```

The browser never decides access: every request is authenticated and authorized by the API, and lists are filtered
by scope in the database.
