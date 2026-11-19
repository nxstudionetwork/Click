# Click Business OS — foundation

The internal operating system for running Click. This document describes the **foundation** every future module
(Finance, People & HR, Procurement, Partners, …) plugs into. Modules are built one by one on top of it; none of
them may add their own login, permission, notification, approval or audit system.

## Where things live

| Layer | Backend (`backend/apps`) | Frontend (`apps/business-os`) |
|---|---|---|
| Organization (company, business units, regions, states, cities, sites, departments, teams) | `organization` | Settings → Structure |
| People record (who someone is: employee ID, designation, department, location, manager) | `people` | Profile, `/people/:id` |
| Identity & access (OS accounts, sessions, MFA, roles, scoped permissions, approval authority, service accounts) | `access` | Login, Settings → Users / Roles / Security |
| Audit (append-only) | `audit` | Settings → Audit trail |
| Workflows (approval policies, levels, requests, delegation, escalation) and tasks | `workflows` | Approvals, Tasks, My Work, Settings → Workflows |
| Workspace (context, Home widgets, notifications, search, calendar, module registry pages, Business AI) | `workspace` | Shell, Home, Notifications, Search, Calendar, `/m/:module` |
| Shared contract | — | `packages/api/src/os.ts` (`osApi`) |

API surface: **`/api/v1/os/*`** (`backend/apps/workspace/urls.py`). Same error envelope, camelCase and pagination as
the rest of Click.

## Business model principle

Click is primarily a technology platform / mediator. It is **not** automatically the supplier of what is listed.
`apps/organization/commercial.py` defines the commercial relationship types (marketplace, commission partner,
agency, Click-operated, Click-owned inventory, third-party fulfillment, other approved). Every future record that
creates money movement or liability (contracts, invoices, commissions, settlements, taxes, refunds, payouts,
reporting) must store one of these — never assume "Click sold it". The Home business snapshot labels platform
collections as GMV, not Click revenue, for the same reason.

## Sign-in

`identify → password → (MFA) → session`, with an "How are you accessing?" step (Employee, Administrator,
Partner / Business, Other authorized account).

- Work email, employee ID or verified phone as identifier. Unknown identifiers get the same answer as known ones.
- Passwords use Django's validators; 5 failures lock the account for 15 minutes (security notification + audit).
- TOTP two-step verification (RFC 6238, secrets encrypted at rest, replay-protected) with 10 single-use recovery codes.
- **No admin backdoor.** "Administrator" is an ordinary account whose roles grant administration permissions; that
  path is refused for anyone without them.
- Partner and external accounts never get employee access; their scopes are clamped to their own partner business.
- Service accounts (`Authorization: ClickKey <prefix>.<secret>`, hashed) can't use interactive endpoints.
- Methods offered are configuration (`CLICK_OS_AUTH_METHODS`); OTP / SSO plug in at the identify step later.
- Invitations: an admin creates the account, the person sets their own password from a single-use 7-day link.

### Sessions

- Separate refresh cookie `click_os_refresh` (path `/api/v1/os/auth/`), so a customer or partner session never
  signs anyone into Business OS.
- Every access token carries `os_sid`; the server checks that session on **every request**, so logout,
  "sign out everywhere", password change, suspension and role removal take effect immediately.
- Idle timeout (`CLICK_OS_IDLE_MINUTES`, 60) and absolute maximum (`CLICK_OS_SESSION_MAX_HOURS`, 12).
- A sign-in from a device the account never used raises a security notification (suspicious-login signal).

## Permissions: MODULE → RESOURCE → ACTION → SCOPE

- The catalogue is code: `backend/apps/access/registry.py` (27 navigation workspaces, ~290 permissions, synced to
  the database after every migrate). The 50 business areas in `work_details/os/modules_os.txt` are grouped into
  those workspaces (`includes`) so the sidebar stays usable.
- A role grants each permission at a scope: `own`, `team`, `department`, `branch` (nearest site), `city`, `state`,
  `region`, `business_unit`, `organization`. Scopes resolve from the assignment's anchor (unit / department /
  team), falling back to the person's HR record. Unresolvable scopes grant nothing (fail closed).
- Roles can inherit from a parent role, be limited to an audience (employee / partner / external / service), and
  require MFA. Sensitive permissions (payroll, identity administration, sensitive audit) need MFA when
  `CLICK_OS_SENSITIVE_REQUIRES_MFA` is on (always outside development).
- Approval authority: per-role limits per approval type (expense, purchase, refund, discount, hiring, payment).
- Anti-escalation: nobody changes their own roles or status; you can only grant permissions you hold yourself
  (organization-wide grants need your own organization-wide grant); built-in roles are read-only templates.

Enforcement order: navigation hides → route guard blocks → **API refuses** → **queryset is filtered by scope**.
The frontend is never the security layer.

### Writing a module endpoint

```python
from apps.access.api import OSView

class InvoiceListView(OSView):
    permissions = {"GET": "finance.invoice.view", "POST": "finance.invoice.create"}

    def get(self, request):
        scope = self.authz.scope("finance.invoice.view")
        qs = scope.filter(Invoice.objects.all(), unit="org_unit", department="department", owner="created_by")
        return self.paginate(qs, InvoiceSerializer)
```

Then: `record(request, "finance.invoice.update", category="financial", resource=inv, old=..., new=...)` for audit,
`notify(user, "business", ...)` for notifications, `engine.submit(request, "finance.invoice", ...)` for approvals,
a provider in `workspace/search.py` for global search, and a widget in `workspace/widgets.py` for Home.

## Approvals

Policies (`finance.expense`, `procurement.request`, `workflows.general` are installed) → levels (approver
permission, minimum amount, enforce limit, escalate after N hours) → requests → steps. An approver needs the
permission, a scope covering the request's location/department, and an approval limit covering the amount; the
requester can never approve their own request. Delegation lets a colleague decide on someone's behalf (recorded).
Rejection needs a reason. `python manage.py os_escalate_approvals` (run every 15 min) reminds approvers of overdue
steps. All amounts are data, none are hard-coded.

## Home / Command Center

Composed from a widget registry + each role's `home_widgets` + the person's own hide/reorder preference, filtered
by permission. Each widget loads independently. Business figures (GMV, orders, partners, customers, support,
payments) come from the live platform tables; platform-wide numbers need organization-wide scope, otherwise the
widget says so instead of showing partial or unauthorized data.

## Business AI

`backend/apps/workspace/ai.py`. The AI can only call tools; each tool declares a permission and runs as the asking
user. The default provider answers deterministically from tool output (no invented figures). An LLM provider can
be plugged in via `CLICK_OS_AI_PROVIDER` and receives only the tools that user may call. Every question is audited.

## Running it

```bash
cd backend
python manage.py migrate
python manage.py seed_os_dev          # DEVELOPMENT ONLY: Click structure, employees, one persona per role
python manage.py runserver 4000
npm run dev -w @click/business-os      # http://localhost:5177 (proxies /api to :4000; CLICK_API_PROXY overrides)
```

Sign in with **Development personas** on the login screen (DEBUG only) or any persona email with the development
password printed by the seed. Personas: CEO, System Administrator, Finance Head, Finance Manager (South region),
HR Manager, Operations Manager, Partner Manager, Branch Manager (Hyderabad), two employees, Internal Auditor.

Production bootstrap (no default passwords):

```bash
python manage.py os_bootstrap --org-code click --org-name "Click" --admin-email you@company.com --admin-name "Your Name"
```

It installs the role templates and policies and prints a one-time invitation link for the first administrator.

## Not built yet (by design)

Business module screens (Finance ledger, HR attendance/payroll, Procurement, Inventory, …) show an honest
"coming in a later phase" page listing their planned areas and the permissions the person already holds. Email /
SMS / push delivery, SSO, phone-OTP sign-in for staff and meeting calendars are extension points with no provider
configured.
