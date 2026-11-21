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

`backend/apps/workspace/widgets.py` (registry), `home_views.py` (API), `pulse.py`, `alerts.py`, `announcements.py`.

- Widgets are registered with a permission and an audience; Home = the role's preset (`Role.home_config`) + the
  person's own layout and saved views (`account.preferences.home`), filtered by permission and scope on every load.
  Each widget is fetched on its own (`/os/home/widgets/<key>`), so one slow or failing source never blanks Home.
- Mandatory: open alerts and critical announcements (critical ones can't be dismissed; some need acknowledgement).
- Business pulse figures come from live platform tables. GMV is labelled *gross transaction value* — it is never
  presented as Click revenue. Platform-wide numbers need organization-wide scope; otherwise the widget says so.
- Alerts are detected from live data by `alerts.DETECTORS`, auto-resolve when the condition clears, and are shown
  only to people allowed to see the source data. Run `python manage.py os_detect_alerts` every few minutes
  (Home also triggers detection at most every 120 s).
- Modules plug in through registries instead of editing Home: `PRIORITY_SOURCES`, `MY_WORK_SOURCES`,
  `BRIEFING_SOURCES`, `TEAM_SOURCES`, `INSIGHT_SOURCES`, `calendar.SOURCES`, `search.PROVIDERS`, `ai.EXTRA_TOOLS`,
  `alerts.DETECTORS`, `documents.access.register`, and workflow hooks via `@on_decision(policy_key)`.

## IDs: the OS namespace is separate from the apps

| Record | Format | Where |
|---|---|---|
| Employee | `EMP-000001` (`CLICK_OS_EMPLOYEE_ID_PREFIX`) | Business OS only |
| Position / candidate | `POS-…` / `CAN-…` | Business OS only |
| Customer | `CL-CU-…` (older `CLK-CS-…` kept) | Customer app |
| Partner | `CLK-PT-…` | Partner app |
| Order | `CLK-…` | Customer & partner apps |
| Finance documents | `JV-`, `INV-`, `BILL-`, `CN-`, `DN-`, `PAY-`, `RCPT-`, `STL-`, `EXP-`, `BUD-`, `FA-`, `DSP-`, `AGR-` | Business OS (gap-free `NumberSeries`) |
| Procurement documents | `PR-`, `RFQ-`, `RFP-`, `RFI-`, `QT-`, `AWD-`, `PO-`, `GRN-`, `SRN-`, `CT-`, `SUP-`, `PEX-`, `RP-` | Business OS (same series) |

Employee IDs come from `people.models.next_id`, which skips values already taken, so explicit or imported IDs never
collide. Old `CLK-E-` employee numbers were migrated to `EMP-`. An OS session is also separate from customer and
partner sessions: staff sign in to Business OS with their own account and audience.

## People & HR (module 2)

`backend/apps/people/` (API at `/api/v1/os/people/*`), `apps/business-os/src/pages/people/` (UI at `/people`).

- Directory vs record: everyone with directory access sees names, roles, teams and work contact details; the
  employment record, personal details, compensation, cases and restricted documents need their own permissions.
  Personal and pay data never reach search, AI, notifications, analytics or exports that the reader can't see.
- New scope `reports`: managers see their reporting line (from `Employee.manager`); anyone with direct reports gets
  the implicit `people-manager` role.
- People 360 profile tabs are chosen by the server per viewer. Compensation and payroll need MFA outside
  development, and every view of pay, cases and restricted documents is audited.
- Everything that changes employment goes through the approval engine: leave (manager, plus HR from 6 days),
  attendance corrections, positions, offers (hiring limits apply), promotions, transfers, salary revisions and exits.
  Approved changes apply on the effective date and trigger an access review; completing an exit revokes OS access.
- Analytics are aggregates only; groups smaller than 3 are hidden. Anonymous surveys show results only once the
  minimum group has answered.
- Payroll: Business OS produces payroll *inputs* (attendance, paid/unpaid leave, current pay). It does not calculate
  pay; the payroll provider / Finance stays the record of payments.
- Documents use the central store (`apps/documents`): versioned, file type checked by content, access rules owned
  by the module.
- Jobs: `python manage.py os_people_jobs` daily (apply effective-dated changes, probation and document reminders).

## Identity & Access (module 3)

`backend/apps/access/` (`governance.py`, `governance_views.py`; API `/api/v1/os/access/*`), UI at `/access`.
It extends the foundation — accounts, sessions, scoped roles, approval limits, delegation, service accounts — and adds
no second permission system.

- **One grant path.** Admin assignment, access packages, approved access requests and emergency access all go
  through `governance.provision()`: anti-escalation (you grant only what you hold), segregation of duties, audit and
  notification are applied identically.
- **Access requests** use the approval engine (`access.request`: manager, then access administrator). The grant only
  happens if one of the approvers holds the permissions (usually the business owner at level 1); otherwise the request
  is "approved but not granted" with the reason.
- **Access reviews**: periodic, privileged-only and event-triggered (People & HR transfers create one automatically).
  The person's manager reviews; nobody certifies their own access; "remove" takes effect immediately.
- **Segregation of duties**: rules are data (`warning` / `exception` / `block`), checked on every grant. Exceptions
  need `access.sod.approve` and someone other than the person.
- **Emergency (break-glass) access**: only roles marked eligible, at most 8 hours, two-step required, security
  administrators notified, ends automatically, reviewed afterwards by someone else.
- **Analysis**: effective access (direct, inherited, automatic, temporary, delegated, MFA-blocked, conflicts),
  who-has-access, permission simulator (scope + approval limit), role comparison and matrix, role version history with
  diffs, privileged access, orphaned / unused access, an internal access-risk indicator (not a certification).
- Requesting access is everyday work: `access.request.*` never makes someone an administrator.
- **Not provided on purpose:** impersonation ("act as"). Use the permission simulator and effective-access view to
  debug access without ever acting as another person.
- Job: `python manage.py os_access_jobs` every 15 minutes (ends temporary / emergency access, warns 3 days before,
  expires accounts, lapses SoD exceptions).

## Finance (module 4)

`backend/apps/finance/` (API `/api/v1/os/finance/*`), UI at `/finance`. Finance owns financial consequences only;
customers, partners, orders, employees and identities stay in their own apps and are referenced.

- **GTV is not revenue.** Every captured platform payment becomes a `TransactionBreakdown` using the partner
  agreement in force at the time (snapshotted): gross → partner share, Click commission, platform fee, tax on Click's
  fees, gateway cost, who funded the discount. Click-operated / owned-inventory sales are revenue as principal. Wallet
  top-ups and gift cards are a liability. Rides, bookings and other services without a partner agreement yet are shown
  as "unclassified", never guessed into revenue.
- **Double entry** through `ledger.post()` only: balanced to the paisa, open period, valid account mapping (a missing
  mapping refuses to post), idempotent per source. Posted journals are never edited — reversals, credit / debit notes
  and corrective journals instead.
- **Periods**: open → soft-closed (adjustments only) → closed → locked. Closing checks the close checklist; reopening
  needs a reason and a second approver (`finance.period_reopen`).
- **Approvals** (central engine): manual journals, vendor bills, payments / payment runs, settlements, credit notes,
  budgets, partner commercial terms, period reopen. Preparers can't release their own payments or settlements.
- **Partner settlements**: unsettled sales and refunds (with the refund responsibility from the agreement) and
  adjustments → net payable per partner → approval → payment (Dr partner payable / Cr bank) → bank reconciliation.
  Partner statements reconcile opening + movements to closing.
- **AP / AR**: invoices, vendor bills (duplicate supplier-invoice detection, three-way match hook for Procurement),
  receipts, outgoing payments with duplicate-payment detection, payment runs, aging.
- **Budgets**: budget vs actual (posted ledger) vs committed (`BudgetCommitment`, reserved by Procurement) vs
  forecast (clearly labelled estimate). `services.check_budget()` / `reserve()` / `consume()` / `release()` are the
  integration points.
- **Also**: expense claims with explained policy checks, fixed assets with straight-line depreciation, bank accounts
  (numbers encrypted, masked, reveal audited, changes announced), statement import and matching, gateway exception
  detection, disputes, versioned tax rules (templates — review with a tax professional), reports (TB, P&L, balance sheet,
  cash flow, GL, aging, tax, cash position, forecast, platform), controls page.
- **Scope**: entity-wide figures (P&L, platform, settlements, banking) need organization-wide finance access; regional
  finance users see their region's documents. Money leaves the API as exact strings, never floats.
- Job: `python manage.py os_finance_jobs` every 15 minutes (brings captured / refunded payments into the ledger,
  detects gateway exceptions).

## Procurement (module 5)

`backend/apps/procurement/` (API `/api/v1/os/procurement/*`), UI at `/procurement`. Procurement owns how Click buys:
need → purchase request → budget check → approval → RFQ / RFP / RFI → quotes → evaluation and negotiation → award →
purchase order → goods / service receipt → supplier invoice (a Finance vendor bill) → three-way match → payment
(Finance). Every document links back to the one before it (`traceability` on the request drawer).

- **Suppliers are not partners.** One supplier master (`SUP-`) with onboarding, verification checks (legal name, tax
  registration, bank account are required before onboarding can be submitted), risk factors, preference
  (preferred / approved / conditional / restricted / blocked, permission-controlled and audited) and measured
  scorecards (blank until there is data). A marketplace partner is a supplier only when the relationship says so.
  Possible duplicates (name, GSTIN, PAN, bank) are shown for review and never merged automatically.
- **Bank detail changes** are a fraud route: requested with the evidence of independent verification, approved by
  someone else (`procurement.supplier_bank`), Finance alerted. Nothing changes before approval.
- **Requests**: templates, budget check against Finance (`check_budget` → `reserve`), emergency limit, single-source
  justification, budget-override reason. Approval via `procurement.request` (manager → finance ≥ 1,00,000 →
  executive ≥ 10,00,000).
- **Sourcing**: competitive quotes required above the policy threshold (default 1,00,000, minimum 3 quotes); awarding
  with fewer needs a reason and raises a `no_competitive_quotes` exception. Weighted scoring plus TCO; evaluators with
  a declared conflict for that supplier cannot score it. Negotiation creates a new quote revision — the original is
  preserved. **Savings are counted once, at award, before tax** (GST is recoverable input credit).
- **Orders**: approval (`procurement.order`), versioned amendments (`procurement.amendment`), the budget commitment
  moves from the request to the order. Blocked or unapproved suppliers can't be ordered from (configurable).
- **Receiving**: the buyer can't receive their own order; over-receipt is blocked; rejected quantities go to quality;
  CAPEX receipts create a draft fixed asset in Finance. Click-owned inventory is marked pending until the Inventory
  module exists.
- **Invoice**: recorded from the order as a Finance vendor bill (the quoted GST rate resolves to the active tax rule);
  the match (quantity received, price, tax, tolerance) runs through `finance.services.MATCHERS["procurement.order"]`.
  A bill with a match exception can't be submitted.
- **Controls**: exceptions (split purchases, duplicate suppliers, maverick spend, concentration, emergency, single
  source) are flags for review, never accusations. Conflict-of-interest declarations, policies and ethics pages,
  contracts with 90 / 60 / 30-day renewal alerts and renewal decisions, recurring purchases.
- **Analytics** (organization-wide only): committed vs actual vs managed vs unmanaged spend, by supplier / category /
  department / location / month / CAPEX-OPEX, concentration, cycle times, savings detail, CSV export.
- Job: `python manage.py os_procurement_jobs` daily (recurring purchase drafts a week ahead, exception detection).
  Contract expiry (90 / 60 / 30 / 7 days) is raised by the central alert detectors.
- Not yet: GRNI (goods received not invoiced) accrual at period end, and supplier self-service portal.

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
HR Manager, Operations Manager, Partner Manager, Branch Manager (Hyderabad), Recruiter, HR Business Partner
(South), employees (one on probation), Internal Auditor, Accountant, Treasury & Controller, Procurement Manager,
Buyer & Category Manager, Receiving & Quality (Hyderabad). Employee numbers run
EMP-000001 upwards.

Production bootstrap (no default passwords):

```bash
python manage.py os_bootstrap --org-code click --org-name "Click" --admin-email you@company.com --admin-name "Your Name"
```

It installs the role templates and policies and prints a one-time invitation link for the first administrator.

## Not built yet (by design)

Business module screens other than People & HR, Identity & Access, Finance and Procurement (Inventory, Sales, Operations, …) show an honest
"coming in a later phase" page listing their planned areas and the permissions the person already holds. Email /
SMS / push delivery, SSO, phone-OTP sign-in for staff, meeting calendars and the payroll provider
(`CLICK_PAYROLL_PROVIDER`) are extension points with no provider configured.
